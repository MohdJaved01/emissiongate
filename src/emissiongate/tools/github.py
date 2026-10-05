"""GitHub REST via httpx (ADR-0011). The gate only reads labels/events/comments and upserts one
comment. It never pushes, approves or merges (AGENTS.md invariant 14).

The token comes from the environment of the process (GitHub Actions' ephemeral GITHUB_TOKEN, or a
human's terminal). It is never written to a file, log, report or ledger (invariant 13).
"""

from __future__ import annotations

import time
from datetime import datetime

import httpx

API = "https://api.github.com"
MARKER = "<!-- emissiongate-gate -->"


class GitHubError(RuntimeError):
    pass


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class GitHub:
    def __init__(self, token: str, repo: str, client: httpx.Client | None = None) -> None:
        if not token:
            raise GitHubError("GITHUB_TOKEN is not set in this process's environment")
        self.repo = repo
        self._client = client or httpx.Client(
            base_url=API,
            timeout=15.0,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "emissiongate-gate",
            },
        )

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(3):  # 1 try + 2 retries (GATE §5)
            try:
                resp = self._client.request(method, path, **kwargs)  # type: ignore[arg-type]
                if resp.status_code >= 500:
                    raise GitHubError(f"{method} {path}: HTTP {resp.status_code}")
                if resp.status_code >= 400:
                    raise GitHubError(f"{method} {path}: HTTP {resp.status_code} {resp.text[:200]}")
                return resp
            except (httpx.HTTPError, GitHubError) as exc:
                last = exc
                if isinstance(exc, GitHubError) and "HTTP 4" in str(exc):
                    break
                time.sleep(1.5 * (attempt + 1))
        raise GitHubError(str(last))

    def _paged(self, path: str) -> list[dict]:
        out: list[dict] = []
        for page in range(1, 11):
            items = self._request("GET", path, params={"per_page": 100, "page": page}).json()
            out.extend(items)
            if len(items) < 100:
                break
        return out

    # ---- reads ---------------------------------------------------------------------------------

    def labels(self, pr: int) -> list[str]:
        return [x["name"] for x in self._paged(f"/repos/{self.repo}/issues/{pr}/labels")]

    def label_event(self, pr: int, label: str) -> dict | None:
        events = self._paged(f"/repos/{self.repo}/issues/{pr}/events")
        added = [e for e in events if e.get("event") == "labeled" and e["label"]["name"] == label]
        return added[-1] if added else None

    def comments(self, pr: int) -> list[dict]:
        return self._paged(f"/repos/{self.repo}/issues/{pr}/comments")

    def acceptance(
        self, pr: int, label: str, since: datetime | None = None
    ) -> tuple[str | None, str | None]:
        """(who added the label, their reason) for the current head; either may be None.

        Only a human (`User`) acknowledges (invariant 14). The label and the reason comment may
        come in either order but must both be newer than `since` (the head commit), so an
        acknowledgement never carries over to a later push.
        """
        if label not in self.labels(pr):
            return None, None
        event = self.label_event(pr, label)
        if event is None or (event.get("actor") or {}).get("type") != "User":
            return None, None
        if since is not None and _ts(event["created_at"]) < since:
            return None, None
        actor = event["actor"]["login"]
        theirs = [
            c
            for c in self.comments(pr)
            if c["user"]["login"] == actor
            and c["user"].get("type") == "User"
            and (since is None or _ts(c["created_at"]) >= since)
            and MARKER not in (c.get("body") or "")
            and (c.get("body") or "").strip()
        ]
        reason = theirs[-1]["body"].strip() if theirs else None
        return actor, reason

    # ---- the only write ------------------------------------------------------------------------

    def upsert_comment(self, pr: int, body: str) -> str:
        if MARKER not in body:
            raise GitHubError("gate comment must carry the sticky marker")
        for c in self.comments(pr):
            if MARKER in (c.get("body") or ""):
                resp = self._request(
                    "PATCH", f"/repos/{self.repo}/issues/comments/{c['id']}", json={"body": body}
                )
                return str(resp.json()["html_url"])
        path = f"/repos/{self.repo}/issues/{pr}/comments"
        resp = self._request("POST", path, json={"body": body})
        return str(resp.json()["html_url"])
