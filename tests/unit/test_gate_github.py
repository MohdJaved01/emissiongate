"""Gate GitHub client: the sticky comment. No network.

Acknowledgement rules (invariant 14, THREAT_MODEL B4) are in tests/security/test_acknowledgement.py.
"""

import httpx
import pytest
import respx

from emissiongate.tools.github import MARKER, GitHub, GitHubError

REPO = "owner/emissiongate-demo-estate"
BASE = f"https://api.github.com/repos/{REPO}"


def _gh() -> GitHub:
    return GitHub("test-token-not-real", REPO)


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
