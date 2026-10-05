#!/usr/bin/env python3
"""Check that agent instruction files stay consistent (ADR-0012).

Dependency-free (stdlib only, Python 3.11+) so it runs in CI, inside the Codex sandbox, and before
`make setup`. Exit code 0 = consistent, 1 = problems found (listed on stderr).

Checks:
  - AGENTS.md exists, has the invariants and a `## Code Review Rules` section that cites every invariant,
    and root + nested AGENTS.md stay under Codex's 32 KiB project-instructions budget (24 KiB target).
  - CLAUDE.md imports AGENTS.md.
  - Every Codex skill in .agents/skills has valid frontmatter (name == folder, description), no
    Claude-only keys or $ARGUMENTS, and a well-formed agents/openai.yaml when present.
  - Every Codex skill has a Claude pointer in .claude/skills that points back to it (if .claude/ exists).
  - .codex/config.toml parses and keeps network off; .codex/agents/*.toml have the required keys, are
    read-only, and reference an existing docs/review/*.md file; the matching .claude/agents file points
    at the same review file.
  - .codex/rules and .claude/settings.json both forbid the dangerous commands.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARD_LIMIT = 32 * 1024  # Codex project_doc_max_bytes default
TARGET_LIMIT = 24 * 1024  # our own budget, leaves room for nested files
CLAUDE_ONLY_KEYS = {
    "disable-model-invocation",
    "argument-hint",
    "allowed-tools",
    "context",
    "arguments",
}
MUST_FORBID = ["tofu apply", "tofu destroy", "terraform", "aws", "make demo-live"]

problems: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        fail(f"{rel(path)}: missing YAML frontmatter")
        return {}, text
    try:
        head, body = text[4:].split("\n---\n", 1)
    except ValueError:
        fail(f"{rel(path)}: unterminated frontmatter")
        return {}, text
    meta: dict[str, str] = {}
    for line in head.splitlines():
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            fail(f"{rel(path)}: frontmatter line is not 'key: value': {line!r}")
            continue
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, body


def check_agents_md() -> None:
    agents = ROOT / "AGENTS.md"
    if not agents.exists():
        fail("AGENTS.md is missing")
        return
    text = agents.read_text(encoding="utf-8")
    size = len(text.encode("utf-8"))
    if size > TARGET_LIMIT:
        fail(
            f"AGENTS.md is {size} bytes; keep it under {TARGET_LIMIT} (Codex reads at most {HARD_LIMIT} combined)"
        )
    inv = re.search(r"## Non-negotiable invariants\n(.*?)\n## ", text, re.S)
    if not inv:
        fail("AGENTS.md: '## Non-negotiable invariants' section not found")
        return
    numbers = [int(n) for n in re.findall(r"^(\d+)\. \*\*", inv.group(1), re.M)]
    if numbers != list(range(1, len(numbers) + 1)):
        fail(f"AGENTS.md: invariants are not numbered 1..N consecutively: {numbers}")
    review = text.split("## Code Review Rules", 1)
    if len(review) < 2:
        fail(
            "AGENTS.md: '## Code Review Rules' section not found (Codex GitHub review looks for this heading)"
        )
    else:
        cited = {int(n) for n in re.findall(r"invariant (\d+)", review[1])}
        missing = sorted(set(numbers) - cited)
        if missing:
            fail(f"AGENTS.md: Code Review Rules do not cite invariant(s) {missing}")
    for nested in sorted((ROOT / "src").rglob("AGENTS.md")) if (ROOT / "src").exists() else []:
        combined = size + len(nested.read_bytes())
        if combined > HARD_LIMIT:
            fail(
                f"{rel(nested)}: root + nested AGENTS.md = {combined} bytes > {HARD_LIMIT}; Codex will truncate"
            )
        if "## Code Review Rules" not in nested.read_text(encoding="utf-8"):
            fail(f"{rel(nested)}: no '## Code Review Rules' section")
    claude = ROOT / "CLAUDE.md"
    if claude.exists() and "@AGENTS.md" not in claude.read_text(encoding="utf-8"):
        fail("CLAUDE.md does not import @AGENTS.md")


def check_skills() -> None:
    skills_dir = ROOT / ".agents" / "skills"
    if not skills_dir.exists():
        fail(".agents/skills is missing")
        return
    names = []
    for skill in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        md = skill / "SKILL.md"
        if not md.exists():
            fail(f"{rel(skill)}: SKILL.md missing")
            continue
        meta, body = frontmatter(md)
        names.append(skill.name)
        if meta.get("name") != skill.name:
            fail(f"{rel(md)}: name '{meta.get('name')}' must equal folder name '{skill.name}'")
        desc = meta.get("description", "")
        if not desc or len(desc) > 1024:
            fail(f"{rel(md)}: description must be 1-1024 characters")
        extra = CLAUDE_ONLY_KEYS & meta.keys()
        if extra:
            fail(
                f"{rel(md)}: Claude-only frontmatter keys {sorted(extra)} — keep them in the .claude pointer"
            )
        if "$ARGUMENTS" in body:
            fail(f"{rel(md)}: $ARGUMENTS is not supported by Codex skills; ask the user instead")
        yaml_file = skill / "agents" / "openai.yaml"
        if yaml_file.exists():
            y = yaml_file.read_text(encoding="utf-8")
            if "policy:" in y and not re.search(
                r"allow_implicit_invocation:\s*(true|false)\s*$", y, re.M
            ):
                fail(f"{rel(yaml_file)}: policy.allow_implicit_invocation must be true or false")
    claude_skills = ROOT / ".claude" / "skills"
    if (ROOT / ".claude").exists():
        for name in names:
            pointer = claude_skills / name / "SKILL.md"
            if not pointer.exists():
                fail(f"{rel(pointer)} missing — Claude Code users won't see skill '{name}'")
                continue
            if f".agents/skills/{name}/SKILL.md" not in pointer.read_text(encoding="utf-8"):
                fail(f"{rel(pointer)} does not point at .agents/skills/{name}/SKILL.md")
        if claude_skills.exists():
            for extra_dir in sorted(p.name for p in claude_skills.iterdir() if p.is_dir()):
                if extra_dir not in names:
                    fail(f".claude/skills/{extra_dir} has no canonical .agents/skills/{extra_dir}")


def check_codex() -> None:
    cfg = ROOT / ".codex" / "config.toml"
    if not cfg.exists():
        fail(".codex/config.toml is missing")
    else:
        try:
            data = tomllib.loads(cfg.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            fail(f".codex/config.toml does not parse: {exc}")
            data = {}
        if data.get("sandbox_workspace_write", {}).get("network_access", False) is not False:
            fail(".codex/config.toml: network_access must stay false (invariant 10)")
    for agent in sorted((ROOT / ".codex" / "agents").glob("*.toml")):
        try:
            a = tomllib.loads(agent.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            fail(f"{rel(agent)} does not parse: {exc}")
            continue
        for key in ("name", "description", "developer_instructions"):
            if not a.get(key):
                fail(f"{rel(agent)}: missing '{key}'")
        if a.get("name") != agent.stem:
            fail(f"{rel(agent)}: name '{a.get('name')}' must equal file stem '{agent.stem}'")
        if a.get("sandbox_mode") != "read-only":
            fail(f'{rel(agent)}: reviewer agents must use sandbox_mode = "read-only"')
        refs = re.findall(r"docs/review/[\w.-]+\.md", a.get("developer_instructions", ""))
        if not refs:
            fail(f"{rel(agent)}: developer_instructions must reference a docs/review/*.md file")
        for ref in refs:
            if not (ROOT / ref).exists():
                fail(f"{rel(agent)}: references missing file {ref}")
            claude_agent = ROOT / ".claude" / "agents" / (agent.stem.replace("_", "-") + ".md")
            if (ROOT / ".claude").exists():
                if not claude_agent.exists():
                    fail(
                        f"{rel(claude_agent)} missing — Claude Code users lose the '{agent.stem}' reviewer"
                    )
                elif ref not in claude_agent.read_text(encoding="utf-8"):
                    fail(f"{rel(claude_agent)} does not point at {ref}")
    rules = "\n".join(
        p.read_text(encoding="utf-8") for p in (ROOT / ".codex" / "rules").glob("*.rules")
    )
    if not rules:
        fail(".codex/rules/*.rules missing")
    else:
        forbidden_blocks = [b for b in rules.split("prefix_rule(") if 'decision = "forbidden"' in b]
        joined = " ".join(
            " ".join(re.findall(r'"([^"]+)"', b.split("justification")[0]))
            for b in forbidden_blocks
        )
        for cmd in MUST_FORBID:
            words = cmd.split()
            if not all(w in joined.split() for w in words):
                fail(f".codex/rules: no forbidden rule covers '{cmd}'")


def check_claude_settings() -> None:
    settings = ROOT / ".claude" / "settings.json"
    if not settings.exists():
        return
    try:
        deny = " ".join(json.loads(settings.read_text(encoding="utf-8"))["permissions"]["deny"])
    except (json.JSONDecodeError, KeyError) as exc:
        fail(f".claude/settings.json unreadable: {exc}")
        return
    for cmd in MUST_FORBID:
        if f"Bash({cmd}" not in deny:
            fail(f".claude/settings.json: deny list does not cover '{cmd}'")


def main() -> int:
    check_agents_md()
    check_skills()
    check_codex()
    check_claude_settings()
    if problems:
        print(f"agent-check: {len(problems)} problem(s)", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("agent-check: AGENTS.md, .agents/, .codex/ and .claude/ are consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
