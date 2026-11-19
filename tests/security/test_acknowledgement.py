"""E1 acknowledgement: bound to the head SHA, given by a human with write access. No network."""

from __future__ import annotations

import httpx
import pytest
import respx

from emissiongate.tools.github import GitHub, GitHubError

REPO = "owner/emissiongate-demo-estate"
BASE = f"https://api.github.com/repos/{REPO}"
HEAD = "a" * 40
OLD = "b" * 40
LABEL = [{"name": "eg/carbon-accepted"}]
REASON = "Needed for the Q4 model launch; schedule follows."


def _gh() -> GitHub:
    return GitHub("test-token-not-real", REPO)


def _review(
    body: str = REASON,
    commit: str = HEAD,
    login: str = "alice",
    kind: str = "User",
    state: str = "COMMENTED",
) -> dict:
    return {
        "id": 1,
        "body": body,
        "commit_id": commit,
        "state": state,
        "user": {"login": login, "type": kind},
    }


def _event(login: str = "alice", kind: str = "User") -> dict:
    return {
        "event": "labeled",
        "label": {"name": "eg/carbon-accepted"},
        "actor": {"login": login, "type": kind},
    }


def _mock(
    labels: list,
    reviews: list,
    perms: dict[str, str] | None = None,
    events: list | None = None,
) -> None:
    respx.get(f"{BASE}/issues/7/labels").mock(return_value=httpx.Response(200, json=labels))
    respx.get(f"{BASE}/issues/7/events").mock(
        return_value=httpx.Response(200, json=[_event()] if events is None else events)
    )
    respx.get(f"{BASE}/pulls/7/reviews").mock(return_value=httpx.Response(200, json=reviews))
    for login, role in (perms or {"alice": "write"}).items():
        respx.get(f"{BASE}/collaborators/{login}/permission").mock(
            return_value=httpx.Response(
                200, json={"permission": role, "role_name": role, "user": {"login": login}}
            )
        )


@respx.mock
def test_review_on_the_head_commit_by_a_writer_accepts() -> None:
    _mock(LABEL, [_review()])
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == ("alice", REASON)


@respx.mock
def test_a_review_on_an_older_commit_does_not_carry_over() -> None:
    """Backdating the new commit's committer date no longer matters: only the SHA does."""
    _mock(LABEL, [_review(commit=OLD)])
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == (None, None)


@respx.mock
@pytest.mark.parametrize("role", ["read", "triage", "none"])
def test_reviewer_without_write_access_cannot_accept(role: str) -> None:
    _mock(LABEL, [_review(login="mallory")], {"mallory": role}, [_event("mallory")])
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == (None, None)


@respx.mock
@pytest.mark.parametrize("role", ["maintain", "admin"])
def test_maintain_and_admin_can_accept(role: str) -> None:
    _mock(LABEL, [_review(login="m")], {"m": role}, [_event("m")])
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == ("m", REASON)


@respx.mock
def test_non_collaborator_is_refused_not_an_error() -> None:
    _mock(LABEL, [_review(login="stranger")], {}, [_event("stranger")])
    respx.get(f"{BASE}/collaborators/stranger/permission").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == (None, None)


@respx.mock
def test_bot_review_is_not_an_acknowledgement() -> None:
    _mock(LABEL, [_review(kind="Bot", login="ci-bot")], {"ci-bot": "write"}, [_event("ci-bot")])
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == (None, None)


@respx.mock
@pytest.mark.parametrize("state", ["DISMISSED", "PENDING"])
def test_dismissed_or_pending_reviews_do_not_count(state: str) -> None:
    _mock(LABEL, [_review(state=state)])
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == (None, None)


@respx.mock
def test_a_review_without_a_reason_does_not_accept() -> None:
    _mock(LABEL, [_review(body="   ")])
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == (None, None)


@respx.mock
def test_no_label_no_acceptance() -> None:
    _mock([], [_review()])
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == (None, None)


@respx.mock
def test_permission_api_failure_fails_closed() -> None:
    _mock(LABEL, [_review()], {})
    respx.get(f"{BASE}/collaborators/alice/permission").mock(
        return_value=httpx.Response(403, json={"message": "Resource not accessible"})
    )
    with pytest.raises(GitHubError):
        _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD)


@respx.mock
def test_label_added_by_a_bot_is_not_an_acknowledgement() -> None:
    """An auto-labeler must not turn an unrelated review into an acceptance."""
    _mock(LABEL, [_review(body="fix the typo")], events=[_event("labeler", kind="Bot")])
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == (None, None)


@respx.mock
def test_label_and_reason_must_come_from_the_same_person() -> None:
    """A triage-role author adds the label; a writer's unrelated review must not complete it."""
    _mock(
        LABEL,
        [_review(login="alice", body="nit: rename")],
        {"alice": "write", "author": "triage"},
        [_event("author")],
    )
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == (None, None)


@respx.mock
def test_the_latest_label_event_decides() -> None:
    """Re-labelled by someone else: the earlier labeller's review no longer counts."""
    _mock(LABEL, [_review(login="alice")], {"alice": "write"}, [_event("alice"), _event("bob")])
    assert _gh().acceptance(7, "eg/carbon-accepted", head_sha=HEAD) == (None, None)
