"""Minimal HCL writing and block-scoped editing for the estate's known shape (SYNTHETIC_ESTATE §3).

Output is `tofu fmt`-clean by construction: consecutive attributes in a block align their `=`,
and a nested block or a blank line starts a new alignment group. Editing is limited to replacing
the value of an existing attribute inside one named block. Free-form HCL is never accepted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

INDENT = "  "


@dataclass(frozen=True)
class Attr:
    key: str
    value: str  # raw HCL expression, e.g. '"g5.2xlarge"', 'var.ami_arm64', '4'


@dataclass(frozen=True)
class Block:
    kind: str
    labels: tuple[str, ...] = ()
    body: tuple[Attr | Block | None, ...] = field(default_factory=tuple)  # None = blank line


def q(value: str) -> str:
    """Quote a string literal for HCL."""
    return json.dumps(value)


def qlist(values: list[str]) -> str:
    return "[" + ", ".join(q(v) for v in values) + "]"


def render(block: Block, depth: int = 0) -> str:
    pad = INDENT * depth
    head = " ".join([block.kind, *(q(label) for label in block.labels)])
    if not block.body:
        return f"{pad}{head} {{}}"
    lines = [f"{pad}{head} {{"]
    group: list[Attr] = []

    def flush() -> None:
        if not group:
            return
        width = max(len(a.key) for a in group)
        for a in group:
            lines.append(f"{pad}{INDENT}{a.key.ljust(width)} = {a.value}")
        group.clear()

    for item in block.body:
        if isinstance(item, Attr):
            group.append(item)
        elif item is None:
            flush()
            lines.append("")
        else:
            flush()
            lines.append(render(item, depth + 1))
    flush()
    lines.append(f"{pad}}}")
    return "\n".join(lines)


def render_file(blocks: list[Block], header: str | None = None) -> str:
    parts = [header.rstrip("\n")] if header else []
    parts.extend(render(b) for b in blocks)
    return "\n\n".join(parts) + "\n"


# ---- block-scoped editing ----------------------------------------------------------------------


def _block_head_pattern(kind: str, labels: tuple[str, ...]) -> re.Pattern[str]:
    parts = [re.escape(kind), *(re.escape(q(label)) for label in labels)]
    return re.compile(r"^(?P<indent>[ \t]*)" + r"\s+".join(parts) + r"\s*\{\s*$", re.M)


def find_block(text: str, kind: str, labels: tuple[str, ...]) -> tuple[int, int]:
    """Return (start, end) offsets of a top-level block, from its head to its closing brace."""
    match = _block_head_pattern(kind, labels).search(text)
    if not match:
        raise KeyError(f"block {kind} {labels} not found")
    depth = 0
    in_string = False
    i = match.end() - 1  # the opening brace
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return match.start(), i + 1
        i += 1
    raise ValueError(f"unbalanced braces in block {kind} {labels}")


def get_attribute(text: str, kind: str, labels: tuple[str, ...], key: str) -> str | None:
    start, end = find_block(text, kind, labels)
    body = text[start:end]
    match = re.search(rf"^[ \t]{{2}}{re.escape(key)}(?P<pad>\s*)=\s*(?P<value>.+)$", body, re.M)
    return match.group("value").strip() if match else None


def set_attribute(text: str, kind: str, labels: tuple[str, ...], key: str, value: str) -> str:
    """Replace the value of a top-level attribute inside one block; alignment is preserved."""
    start, end = find_block(text, kind, labels)
    body = text[start:end]
    pattern = re.compile(rf"^(?P<lead>[ \t]{{2}}{re.escape(key)}\s*=\s*)(?P<value>.+)$", re.M)
    new_body, n = pattern.subn(lambda m: m.group("lead") + value, body, count=1)
    if n != 1:
        raise KeyError(f"attribute {key} not found in {kind} {labels}")
    return text[:start] + new_body + text[end:]


def block_names(text: str, kind: str, resource_type: str | None = None) -> list[tuple[str, ...]]:
    """Labels of every top-level block of a kind (optionally one resource type)."""
    out: list[tuple[str, ...]] = []
    for match in re.finditer(rf'^{re.escape(kind)}((?:\s+"[^"]*")+)\s*\{{', text, re.M):
        labels = tuple(re.findall(r'"([^"]*)"', match.group(1)))
        if resource_type is None or (labels and labels[0] == resource_type):
            out.append(labels)
    return out
