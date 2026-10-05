"""Export a git ref of the infrastructure repo into a temporary directory (read-only git use)."""

from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path


class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, timeout=60, check=False
    )
    if proc.returncode != 0:
        raise GitError(proc.stderr.decode("utf-8", errors="replace").strip()[:500])
    return proc.stdout


def rev_parse(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()


def commit_time(repo: Path, sha: str) -> str:
    """Committer date (ISO 8601) of a commit: acknowledgements must be newer than the head."""
    return _git(repo, "show", "-s", "--format=%cI", sha).decode().strip()


def export_tree(repo: Path, ref: str, dest: Path) -> str:
    """Write the tree at `ref` into `dest`; return the commit SHA."""
    sha = rev_parse(repo, ref)
    data = _git(repo, "archive", "--format=tar", sha)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")
    return sha
