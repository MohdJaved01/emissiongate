#!/usr/bin/env bash
# Install script for a Codex cloud environment (Settings > Codex Cloud > Environments > Install script).
# Paste this file's contents, or `bash scripts/codex-cloud-install.sh` once the repo is cloned.
#
# Internet allowlist for the environment: the "Package managers" preset, plus
#   get.opentofu.org  packages.opentofu.org  registry.opentofu.org  github.com  objects.githubusercontent.com
# Cloud VMs have no local model server, so tasks there are limited to tests and offline mode.
set -euo pipefail

need_py="3.12"
have_py="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
if [ "$(printf '%s\n%s\n' "$need_py" "$have_py" | sort -V | head -1)" != "$need_py" ]; then
  echo "Python $need_py+ required, found $have_py. Select a 3.12 image or install it before this script." >&2
  exit 1
fi

python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[dev]"

if ! command -v tofu >/dev/null 2>&1; then
  # The deb method verifies packages against OpenTofu's signed apt repository. It needs root or sudo.
  curl --proto '=https' --tlsv1.2 -fsSL https://get.opentofu.org/install-opentofu.sh -o /tmp/install-opentofu.sh
  chmod +x /tmp/install-opentofu.sh
  if [ "$(id -u)" -eq 0 ]; then /tmp/install-opentofu.sh --install-method deb
  else sudo /tmp/install-opentofu.sh --install-method deb; fi
  rm -f /tmp/install-opentofu.sh
fi
tofu version

# Mirror providers while the network is available, so every later run is offline (ADR-0014).
make providers

test -f .env || cp .env.example .env
python3 scripts/check_agent_files.py
.venv/bin/pytest -q -m "not slow" || echo "Tests not green yet - expected before milestone M0 is done."
