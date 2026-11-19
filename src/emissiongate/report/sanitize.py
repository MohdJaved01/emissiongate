"""Untrusted text into Markdown (THREAT_MODEL B5). Rendering only; no numbers are made here.

Addresses, attribute values, OpenTofu errors, reasons and notes can come from a pull request. Before
they reach a comment they are collapsed to one line, capped, escaped for Markdown and HTML, and have
`@mentions`, autolinks and issue references broken with a zero-width space, so they render as plain
text and notify nobody. Code spans and fences are sized to their content so they cannot close early.
"""

from __future__ import annotations

import re

ZWSP = "​"
ELLIPSIS = "…"
_MD = re.compile(r"([\\`*_{}\[\]()#+!|~])")
_MENTION = re.compile(r"@(?=[A-Za-z0-9])")
_SCHEME = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*):(?=//)")
_WWW = re.compile(r"(?i)\bwww\.")
_ISSUE = re.compile(r"#(?=\d)")
_FORMATS = {
    "instance_type": re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\.[a-z0-9]+(?:-[a-z0-9]+)*"),
    "region": re.compile(r"[a-z]{2}(?:-[a-z]+)+-\d{1,2}"),
    "number": re.compile(r"\d{1,9}(?:\.\d{1,6})?"),
    "volume_type": re.compile(r"[a-z0-9]{2,12}"),
    "login": re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}"),
}
INVALID = "(invalid value)"


def _one_line(value: object, limit: int) -> str:
    s = " ".join(str(value).split())
    return s if len(s) <= limit else s[: limit - 1] + ELLIPSIS


def _neutralise(s: str) -> str:
    s = _MENTION.sub("@" + ZWSP, s)
    s = _SCHEME.sub(lambda m: m.group(1) + ZWSP + ":", s)
    s = _WWW.sub(lambda m: m.group(0)[:3] + ZWSP + ".", s)
    return _ISSUE.sub("#" + ZWSP, s)


def text(value: object, limit: int = 300) -> str:
    """Plain prose: one line, capped, inert in Markdown and HTML."""
    s = _one_line(value, limit)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _neutralise(_MD.sub(r"\\\1", s))


def code(value: object, limit: int = 200) -> str:
    """An inline code span that its content cannot close; `|` escaped for table cells."""
    s = _one_line(value, limit).replace("|", "\\|")
    run = max((len(m) for m in re.findall(r"`+", s)), default=0)
    ticks = "`" * (run + 1)
    pad = " " if s.startswith("`") or s.endswith("`") else ""
    return f"{ticks}{pad}{s}{pad}{ticks}"


def fence(value: str, lang: str = "", limit: int = 20000) -> str:
    """A fenced code block longer than any backtick run inside it."""
    body = value if len(value) <= limit else value[:limit] + f"\n{ELLIPSIS} (truncated)\n"
    if not body.endswith("\n"):
        body += "\n"
    run = max((len(m) for m in re.findall(r"`+", body)), default=0)
    ticks = "`" * max(3, run + 1)
    return f"{ticks}{lang}\n{body}{ticks}"


def checked(kind: str, value: object) -> str:
    """`value` if it has the expected format for `kind`, else a fixed placeholder."""
    s = str(value)
    return s if _FORMATS[kind].fullmatch(s) else INVALID
