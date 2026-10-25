"""GitHub REST via httpx (ADR-0011). The gate only reads labels, reviews, permissions and comments,
and upserts one comment. It never pushes, approves or merges (AGENTS.md invariant 14).

The token comes from the environment of the process (GitHub Actions' ephemeral GITHUB_TOKEN, or a
human's terminal). It is never written to a file, log, report or ledger (invariant 13).
"""

from __future__ import annotations

import time

import httpx

API = "https://api.github.com"
MARKER = "<!-- emissiongate-gate -->"
ACK_PERMISSIONS = frozenset({"admin", "maintain", "write"})
ACK_REVIEW_STATES = frozenset({"APPROVED", "COMMENTED"})


class GitHubError(RuntimeError):
    pass


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

    def comments(self, pr: int) -> list[dict]:
        return self._paged(f"/repos/{self.repo}/issues/{pr}/comments")

    def label_event(self, pr: int, label: str) -> dict | None:
        """The latest event that added `label` to the PR."""
        events = self._paged(f"/repos/{self.repo}/issues/{pr}/events")
        added = [
            e
            for e in events
            if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == label
        ]
        return added[-1] if added else None

    def reviews(self, pr: int) -> list[dict]:
        return self._paged(f"/repos/{self.repo}/pulls/{pr}/reviews")

    def permission(self, login: str) -> str:
        """The user's role on the repository; "none" if they are not a collaborator."""
        try:
            data = self._request(
                "GET", f"/repos/{self.repo}/collaborators/{login}/permission"
            ).json()
        except GitHubError as exc:
            if "HTTP 404" in str(exc):
                return "none"
            raise
        return str(data.get("role_name") or data.get("permission") or "none")

    def acceptance(self, pr: int, label: str, head_sha: str) -> tuple[str | None, str | None]:
        """(who accepted, their reason) for exactly `head_sha`, or (None, None).

        Bound to the head commit server-side (THREAT_MODEL B4): the label must be on the PR, the
        latest event that added it must be by a human (`User`), and that same person must have
        submitted a review whose `commit_id` is the head SHA, with the reason as its body, and hold
        write, maintain or admin permission. A new push changes the head SHA, so an acknowledgement
        never carries over, whatever the commit dates say; a bot label or someone else's unrelated
        review never completes one. API errors other than "not a collaborator" propagate, and the
        caller fails closed (invariant 14).
        """
        if label not in self.labels(pr):
            return None, None
        event = self.label_event(pr, label)
        actor = (event or {}).get("actor") or {}
        if actor.get("type") != "User" or not actor.get("login"):
            return None, None
        login = actor["login"]
        theirs = [
            r
            for r in self.reviews(pr)
            if r.get("commit_id") == head_sha
            and r.get("state") in ACK_REVIEW_STATES
            and (r.get("user") or {}).get("type") == "User"
            and (r.get("user") or {}).get("login") == login
            and (r.get("body") or "").strip()
        ]
        if not theirs or self.permission(login) not in ACK_PERMISSIONS:
            return None, None
        return login, theirs[-1]["body"].strip()  # the API lists reviews oldest first

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
