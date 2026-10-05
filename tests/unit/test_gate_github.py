"""Gate GitHub client: acknowledgement rules (invariant 14) and the sticky comment. No network."""

from datetime import UTC, datetime

import httpx
import pytest
import respx

from emissiongate.tools.github import MARKER, GitHub, GitHubError

REPO = "owner/emissiongate-demo-estate"
HEAD_TIME = datetime(2026, 10, 5, 8, 0, tzinfo=UTC)  # head commit, before label and reason
BASE = f"https://api.github.com/repos/{REPO}"


def _gh() -> GitHub:
    return GitHub("test-token-not-real", REPO)


def _mock(labels, events, comments):
    respx.get(f"{BASE}/issues/7/labels").mock(return_value=httpx.Response(200, json=labels))
    respx.get(f"{BASE}/issues/7/events").mock(return_value=httpx.Response(200, json=events))
    respx.get(f"{BASE}/issues/7/comments").mock(return_value=httpx.Response(200, json=comments))


LABEL = [{"name": "eg/carbon-accepted"}]


def _event(actor_type: str = "User", at: str = "2026-10-05T10:00:00Z") -> dict:
    return {
        "event": "labeled",
        "label": {"name": "eg/carbon-accepted"},
        "actor": {"login": "alice", "type": actor_type},
        "created_at": at,
    }


def _comment(body: str, at: str, login: str = "alice", kind: str = "User") -> dict:
    return {"id": 1, "body": body, "created_at": at, "user": {"login": login, "type": kind}}


@respx.mock
def test_acceptance_needs_a_human_reason_after_the_label() -> None:
    _mock(
        LABEL,
        [_event()],
        [
            _comment("old remark", "2026-10-05T09:00:00Z"),
            _comment("Needed for the Q4 model launch; schedule follows.", "2026-10-05T10:01:00Z"),
        ],
    )
    who, why = _gh().acceptance(7, "eg/carbon-accepted", since=HEAD_TIME)
    assert who == "alice"
    assert why == "Needed for the Q4 model launch; schedule follows."


@respx.mock
def test_reason_may_come_before_the_label() -> None:
    _mock(LABEL, [_event()], [_comment("Approved by the ML lead.", "2026-10-05T09:00:00Z")])
    who, why = _gh().acceptance(7, "eg/carbon-accepted", since=HEAD_TIME)
    assert who == "alice" and why == "Approved by the ML lead."


@respx.mock
def test_acknowledgement_does_not_carry_over_to_a_new_push() -> None:
    _mock(LABEL, [_event(at="2026-10-05T10:00:00Z")], [_comment("ok", "2026-10-05T10:01:00Z")])
    newer_head = datetime(2026, 10, 5, 11, 0, tzinfo=UTC)
    assert _gh().acceptance(7, "eg/carbon-accepted", since=newer_head) == (None, None)


@respx.mock
def test_reason_older_than_the_head_is_not_a_reason() -> None:
    _mock(LABEL, [_event()], [_comment("old remark", "2026-10-05T07:00:00Z")])
    who, why = _gh().acceptance(7, "eg/carbon-accepted", since=HEAD_TIME)
    assert who == "alice" and why is None


@respx.mock
def test_bot_label_is_not_an_acknowledgement() -> None:
    _mock(LABEL, [_event("Bot")], [_comment("ok", "2026-10-05T10:01:00Z")])
    assert _gh().acceptance(7, "eg/carbon-accepted") == (None, None)


@respx.mock
def test_no_label_no_acceptance() -> None:
    _mock([], [], [])
    assert _gh().acceptance(7, "eg/carbon-accepted") == (None, None)


@respx.mock
def test_upsert_patches_the_sticky_comment() -> None:
    respx.get(f"{BASE}/issues/7/comments").mock(
        return_value=httpx.Response(
            200, json=[{"id": 42, "body": f"{MARKER}\nold", "user": {"login": "bot"}}]
        )
    )
    patch = respx.patch(f"{BASE}/issues/comments/42").mock(
        return_value=httpx.Response(200, json={"html_url": "https://example.invalid/c/42"})
    )
    url = _gh().upsert_comment(7, f"{MARKER}\nnew")
    assert patch.called and url.endswith("/42")


@respx.mock
def test_upsert_posts_when_no_sticky_comment() -> None:
    respx.get(f"{BASE}/issues/7/comments").mock(return_value=httpx.Response(200, json=[]))
    post = respx.post(f"{BASE}/issues/7/comments").mock(
        return_value=httpx.Response(201, json={"html_url": "https://example.invalid/c/1"})
    )
    _gh().upsert_comment(7, f"{MARKER}\nnew")
    assert post.called


def test_comment_without_marker_is_refused() -> None:
    with pytest.raises(GitHubError):
        _gh().upsert_comment(7, "no marker")


def test_missing_token_fails_loudly() -> None:
    with pytest.raises(GitHubError):
        GitHub("", REPO)
