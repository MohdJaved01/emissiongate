# Third-party components and declarations

Required by the hackathon rules: every pre-existing or open-source component is declared here.
Verify licences at build time — licences change.

## Data and methodology

| Component | Use | Licence | Version / reference |
|---|---|---|---|
| Cloud Carbon Footprint (Thoughtworks) | energy coefficients, PUE, replication factors, regional annual emission factors, instance → processor mapping, vendored in `factors/` | Apache-2.0 | commit `f584c549ee358d5980d36513267d007ecd3ee716` |
| UK Carbon Intensity API (National Energy System Operator) | live and forecast half-hourly grid intensity for London; snapshot in `fixtures/grid/` | CC BY 4.0 | api.carbonintensity.org.uk |
| Software Carbon Intensity specification | agent footprint formula | ISO/IEC 21031:2024 | referenced, not copied |
| GHG Protocol Scope 2 Guidance | location-based method | referenced | — |

## Models and runtime

| Component | Use | Licence |
|---|---|---|
| Ollama | local model server | MIT |
| OpenAI gpt-oss-20b (`gpt-oss:20b`) | default runtime model, both reasoning levels (ADR-0013) | Apache-2.0, plus the gpt-oss usage policy |
| Qwen 3.5 9B (`qwen3.5:9b`) | bake-off alternative | Apache-2.0 |
| Qwen 3.6 27B coding (`qwen3.6:27b-coding`) | bake-off alternative | Apache-2.0 |
| OpenTofu | `fmt`, `validate`, `plan` | MPL-2.0 |
| HashiCorp AWS provider (via OpenTofu registry) | provider schema for validation | MPL-2.0 |

## Python libraries

| Library | Licence |
|---|---|
| duckdb | MIT |
| pandas | BSD-3-Clause |
| pyarrow | Apache-2.0 |
| pydantic | MIT |
| PyYAML | MIT |
| typer | MIT |
| rich | MIT |
| httpx | BSD-3-Clause |
| Jinja2 | BSD-3-Clause |
| python-dotenv | BSD-3-Clause |
| codecarbon | MIT |
| pytest, pytest-cov (dev) | MIT |
| respx (dev) | BSD-3-Clause |
| ruff (dev) | MIT |

## Deliberately not used

Terraform ≥ 1.6 (BUSL-1.1), PyGithub (LGPL-3.0), Llama models (community licence), Codestral
(non-production licence), Electricity Maps API data (commercial; free tier too narrow). See `docs/adr/`.

## Related work (not used)

Carbonifer (carbon estimates from Terraform plans) and Infracost (cost estimates in pull requests) address
neighbouring problems. No code from either is used. Differences are listed in `docs/GATE.md §9`.

## Development tooling

Claude Code (Anthropic) wrote all code in this repository on build day (ADR-0016, ADR-0017); OpenAI
Codex built an earlier M0 prototype that is not in this repository. Every milestone was approved by a
human before it was committed; agent instructions are in `AGENTS.md`; the augmentation log records who
did what.

| Build-day tool | Use | Licence |
|---|---|---|
| uv | create the virtualenv and install the Python dependencies | MIT / Apache-2.0 |
| OpenTofu 1.13 (winget `OpenTofu.Tofu`) | local `fmt`/`validate`/`plan` | MPL-2.0 |
| Ollama 0.35 (winget `Ollama.Ollama`) | local model server for `gpt-oss:20b` | MIT |
