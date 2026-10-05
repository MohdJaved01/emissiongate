"""OpenTofu, plan-only (AGENTS.md invariants 3, 7, 10).

Only `init`, `fmt`, `validate`, `plan`, `show` and `version` can run. `init` always uses
`-plugin-dir` (the local provider mirror, ADR-0014), so nothing downloads anything. A workspace
is a temporary copy of the estate, initialised once and reused for every candidate.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from emissiongate.contracts import PlanResult

ALLOWED_SUBCOMMANDS = frozenset({"init", "fmt", "validate", "plan", "show", "version"})
STDERR_TAIL_BYTES = 4096
SKIP_NAMES = {".terraform", ".terraform.lock.hcl", "terraform.tfstate", "plan.bin", ".git"}


class TofuError(RuntimeError):
    pass


class TofuNotFound(TofuError):
    pass


class ProviderMirrorMissing(TofuError):
    pass


@dataclass(frozen=True)
class TofuConfig:
    bin: str
    plugin_dir: Path
    timeout_s: int = 300
    # Shared TF_DATA_DIR: providers are installed from the mirror once per machine, not once per
    # workspace (each fresh copy of the 800 MB provider binary costs a cold start and a rescan).
    data_dir: Path | None = None


def resolve_bin(name: str) -> str | None:
    if Path(name).is_file():
        return str(Path(name))
    return shutil.which(name)


def check_ready(cfg: TofuConfig) -> str:
    """Return the tofu path, or raise a clear error that tells the human what to run."""
    path = resolve_bin(cfg.bin)
    if not path:
        raise TofuNotFound(f"OpenTofu binary {cfg.bin!r} not found. Install OpenTofu >= 1.8.")
    mirror = cfg.plugin_dir / "registry.opentofu.org" / "hashicorp" / "aws"
    if not mirror.is_dir():
        raise ProviderMirrorMissing(
            f"provider mirror missing at {cfg.plugin_dir}. A human runs `make providers` once "
            "(the only networked step, ADR-0014)."
        )
    return path


def tail(text: str, limit: int = STDERR_TAIL_BYTES) -> str:
    data = text.encode("utf-8", errors="replace")
    return data[-limit:].decode("utf-8", errors="replace")


def _env(data_dir: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"TF_IN_AUTOMATION": "1", "CHECKPOINT_DISABLE": "1", "TF_INPUT": "0"})
    if data_dir is not None:
        data_dir.mkdir(parents=True, exist_ok=True)
        env["TF_DATA_DIR"] = str(data_dir)
    # Never inherit cloud credentials: plans use the estate's dummy provider settings only.
    for key in list(env):
        if key.startswith("AWS_"):
            env.pop(key)
    return env


def copy_estate(src: Path, dest: Path) -> None:
    for item in src.iterdir():
        if item.name in SKIP_NAMES or item.name.endswith(".tfstate"):
            continue
        if item.is_dir():
            shutil.copytree(item, dest / item.name, ignore=shutil.ignore_patterns(*SKIP_NAMES))
        else:
            shutil.copy2(item, dest / item.name)


@dataclass
class CommandResult:
    args: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int

    @property
    def command(self) -> str:
        return "tofu " + " ".join(self.args)


class Workspace:
    """A temporary copy of an estate directory with providers initialised from the mirror."""

    def __init__(self, cfg: TofuConfig, estate_dir: Path) -> None:
        self.cfg = cfg
        self.estate_dir = estate_dir
        self.bin = check_ready(cfg)
        self._tmp = tempfile.TemporaryDirectory(prefix="eg-tofu-")
        self.dir = Path(self._tmp.name)
        copy_estate(estate_dir, self.dir)
        self.history: list[CommandResult] = []
        self._initialised = False

    def __enter__(self) -> Workspace:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._tmp.cleanup()

    def run(self, *args: str) -> CommandResult:
        if not args or args[0] not in ALLOWED_SUBCOMMANDS:
            raise TofuError(f"subcommand {args[:1]} is not allowed (plan-only module)")
        start = time.monotonic()
        try:
            proc = subprocess.run(
                [self.bin, *args],
                cwd=self.dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.cfg.timeout_s,
                env=_env(self.cfg.data_dir),
                check=False,
            )
            code, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            code, out, err = 124, "", f"timeout after {exc.timeout}s"
        result = CommandResult(list(args), code, out, err, int((time.monotonic() - start) * 1000))
        self.history.append(result)
        return result

    def init(self) -> CommandResult:
        result = self.run(
            "init",
            "-input=false",
            "-no-color",
            f"-plugin-dir={self.cfg.plugin_dir}",
        )
        if result.exit_code != 0:
            raise TofuError(f"tofu init failed: {tail(result.stderr or result.stdout, 800)}")
        self._initialised = True
        return result

    def _ensure_init(self) -> None:
        if not self._initialised:
            self.init()

    def check(self, files: dict[str, str] | None = None, attempt: int = 1) -> PlanResult:
        """Write `files`, then fmt -check, validate, plan; restore the originals afterwards."""
        self._ensure_init()
        originals: dict[Path, str | None] = {}
        for rel, text in (files or {}).items():
            path = self.dir / rel
            originals[path] = path.read_text(encoding="utf-8") if path.exists() else None
            path.write_text(text, encoding="utf-8", newline="\n")
        try:
            steps = [
                ("fmt", "-check", "-no-color"),
                ("validate", "-no-color"),
                ("plan", "-refresh=false", "-input=false", "-no-color", "-lock=false"),
            ]
            for step in steps:
                result = self.run(*step)
                if result.exit_code != 0:
                    detail = result.stderr or result.stdout
                    if step[0] == "fmt":
                        detail = "fmt -check failed for: " + (result.stdout.strip() or detail)
                    return PlanResult(
                        ok=False,
                        command=result.command,
                        exit_code=result.exit_code,
                        stderr_tail=tail(detail),
                        attempt=attempt,
                    )
            return PlanResult(
                ok=True, command=result.command, exit_code=0, stderr_tail="", attempt=attempt
            )
        finally:
            for path, text in originals.items():
                if text is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(text, encoding="utf-8", newline="\n")

    def plan_json(self) -> tuple[PlanResult, dict | None]:
        """Plan to a file and return `tofu show -json` of it (PR gate, M6.5)."""
        self._ensure_init()
        plan = self.run(
            "plan", "-refresh=false", "-input=false", "-no-color", "-lock=false", "-out=plan.bin"
        )
        if plan.exit_code != 0:
            return (
                PlanResult(
                    ok=False,
                    command=plan.command,
                    exit_code=plan.exit_code,
                    stderr_tail=tail(plan.stderr or plan.stdout),
                    attempt=1,
                ),
                None,
            )
        show = self.run("show", "-json", "plan.bin")
        ok = show.exit_code == 0
        return (
            PlanResult(
                ok=ok,
                command=show.command,
                exit_code=show.exit_code,
                stderr_tail="" if ok else tail(show.stderr),
                attempt=1,
            ),
            json.loads(show.stdout) if ok else None,
        )


def version(cfg: TofuConfig) -> str | None:
    path = resolve_bin(cfg.bin)
    if not path:
        return None
    proc = subprocess.run(
        [path, "version"], capture_output=True, text=True, timeout=30, check=False, env=_env()
    )
    first = proc.stdout.strip().splitlines()
    return first[0] if first else None
