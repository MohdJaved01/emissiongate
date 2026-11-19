"""E1 faithful tree export: the gate plans exactly the commit's tree, nothing more or less."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from emissiongate.tools import gitrefs


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-b", "main", "-q")
    _git(r, "config", "user.email", "test@example.invalid")
    _git(r, "config", "user.name", "sec-test")
    _git(r, "config", "core.symlinks", "true")
    return r


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_gitattributes_cannot_hide_or_rewrite_files(repo: Path, tmp_path: Path) -> None:
    # `git archive` would drop gpu_fleet.tf (export-ignore) and expand $Format$ (export-subst),
    # so the gate would plan a different configuration from the one being merged.
    (repo / ".gitattributes").write_text("gpu_fleet.tf export-ignore\nsubst.tf export-subst\n")
    (repo / "gpu_fleet.tf").write_text('resource "aws_instance" "gpu" {}\n')
    (repo / "subst.tf").write_text("# $Format:%H$\n")
    (repo / "modules" / "m").mkdir(parents=True)
    (repo / "modules" / "m" / "main.tf").write_text("# module\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "c")
    out = gitrefs.export_tree(repo, "HEAD", tmp_path / "out")
    assert out.refused == []
    assert _files(tmp_path / "out") == {
        ".gitattributes",
        "gpu_fleet.tf",
        "subst.tf",
        "modules/m/main.tf",
    }
    assert (tmp_path / "out" / "subst.tf").read_text() == "# $Format:%H$\n"
    assert out.sha == gitrefs.rev_parse(repo, "HEAD")


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_symlinks_are_refused_not_followed(repo: Path, tmp_path: Path) -> None:
    (repo / "main.tf").write_text("# ok\n")
    (repo / "leak.tf").symlink_to("/proc/self/environ")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "c")
    out = gitrefs.export_tree(repo, "HEAD", tmp_path / "out")
    assert any("leak.tf" in r and "symlink" in r for r in out.refused)
    assert not (tmp_path / "out" / "leak.tf").exists()


def test_symlink_entries_are_refused_on_any_platform(repo: Path, tmp_path: Path) -> None:
    """Write a symlink entry straight into the index, so the test runs without OS symlinks."""
    (repo / "main.tf").write_text("# ok\n")
    blob = (
        subprocess.run(
            ["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
            input=b"/proc/self/environ",
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )
    _git(repo, "add", "main.tf")
    _git(repo, "update-index", "--add", "--cacheinfo", f"120000,{blob},leak.tf")
    _git(repo, "commit", "-q", "-m", "c")
    out = gitrefs.export_tree(repo, "HEAD", tmp_path / "out")
    assert any("leak.tf" in r and "symlink" in r for r in out.refused)
    assert _files(tmp_path / "out") == {"main.tf"}


def test_submodules_are_refused(repo: Path, tmp_path: Path) -> None:
    (repo / "main.tf").write_text("# ok\n")
    _git(repo, "add", "main.tf")
    _git(
        repo,
        "update-index",
        "--add",
        "--cacheinfo",
        "160000,1111111111111111111111111111111111111111,vendor",
    )
    _git(repo, "commit", "-q", "-m", "c")
    out = gitrefs.export_tree(repo, "HEAD", tmp_path / "out")
    assert any("vendor" in r and "submodule" in r for r in out.refused)
