"""Export a git ref of the infrastructure repo into a temporary directory (read-only git use).

The export is built from tree objects (`git ls-tree` + `git cat-file --batch`), not `git archive`,
so the pull request's own `.gitattributes` (`export-ignore`, `export-subst`) cannot change what is
planned (THREAT_MODEL B1). Symlinks and submodules are never written; they are returned as refusals.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

BLOB_MODES = {"100644", "100755"}


class GitError(RuntimeError):
    pass


@dataclass
class ExportedTree:
    sha: str
    files: list[str] = field(default_factory=list)  # posix paths relative to the export root
    refused: list[str] = field(default_factory=list)  # entries not exported, with the reason


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], input=stdin, capture_output=True, timeout=60, check=False
    )
    if proc.returncode != 0:
        raise GitError(proc.stderr.decode("utf-8", errors="replace").strip()[:500])
    return proc.stdout


def rev_parse(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()


def read_blob(repo: Path, sha: str, path: str) -> bytes | None:
    """Contents of `path` at commit `sha`, or None if the commit has no such file."""
    entries = _git(repo, "ls-tree", "-z", sha, "--", path).split(b"\0")
    entry = next((e for e in entries if e), None)
    if entry is None:
        return None
    mode, kind, obj = entry.split(b"\t", 1)[0].decode().split()
    if kind != "blob" or mode not in BLOB_MODES:
        return None
    return _git(repo, "cat-file", "blob", obj)


def _safe_rel(name: str) -> PurePosixPath | None:
    p = PurePosixPath(name)
    if p.is_absolute() or any(part in ("", ".", "..", ".git") for part in p.parts):
        return None
    return p


def export_tree(repo: Path, ref: str, dest: Path) -> ExportedTree:
    """Write the blobs of the tree at `ref` into `dest`; return the SHA, files and refusals."""
    sha = rev_parse(repo, ref)
    out = ExportedTree(sha)
    blobs: list[tuple[PurePosixPath, str]] = []
    for raw in _git(repo, "ls-tree", "-r", "-z", "--full-tree", sha).split(b"\0"):
        if not raw:
            continue
        meta, name_b = raw.split(b"\t", 1)
        mode, kind, obj = meta.decode().split()
        try:
            name = name_b.decode("utf-8")
        except UnicodeDecodeError:
            out.refused.append(f"{name_b!r}: path is not UTF-8")
            continue
        rel = _safe_rel(name)
        if rel is None:
            out.refused.append(f"{name}: unsafe path")
        elif mode == "120000":
            out.refused.append(f"{name}: symlink (never followed)")
        elif kind == "commit":
            out.refused.append(f"{name}: submodule (not exported)")
        elif kind == "blob" and mode in BLOB_MODES:
            blobs.append((rel, obj))
        else:
            out.refused.append(f"{name}: unsupported tree entry mode {mode}")
    dest.mkdir(parents=True, exist_ok=True)
    if blobs:
        batch = _git(
            repo, "cat-file", "--batch", stdin="".join(f"{o}\n" for _, o in blobs).encode()
        )
        pos = 0
        for rel, obj in blobs:
            header_end = batch.index(b"\n", pos)
            got, kind, size = batch[pos:header_end].decode().split()
            if got != obj or kind != "blob":
                raise GitError(f"cat-file returned {got} {kind} for {obj}")
            start = header_end + 1
            content = batch[start : start + int(size)]
            pos = start + int(size) + 1  # trailing newline after each object
            target = dest.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            out.files.append(rel.as_posix())
    written = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}
    if written != set(out.files):
        raise GitError("exported files do not match the commit's tree")
    return out
