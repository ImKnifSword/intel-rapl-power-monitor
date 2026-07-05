# intel-rapl-power-monitor

## Created
2026-07-05 via Discord

## Spec (Source of Truth)
This section defines WHAT the project should do. All development decisions must align with this spec.
agy MUST read this section before starting any task and MUST NOT implement anything that contradicts it.
Hermes updates this section when the user requests new features or changes via Discord BEFORE invoking agy.

- Goal: Build a lightweight, minimalist, energy-efficient Intel RAPL power monitor web dashboard for local-network access.
- Key Features:
  - [x] Read Intel RAPL power from `/sys/class/powercap/intel-rapl:0` with package-0 and DRAM domains.
  - [x] Expose data via FastAPI web server with polling every 1s.
  - [x] Responsive local web UI showing current watts, 5-minute line history, and cumulative Wh/kWh.
  - [x] Systemd service unit for autostart on boot.
- Out of Scope:
  - No external internet dependencies.
  - No heavy databases; keep only in-memory recent history.
  - No authentication/authz; intended for trusted LAN use only.

## Tech Stack
- Language: Python 3.11
- Framework: FastAPI + Uvicorn
- Frontend: vanilla HTML/CSS/JS with Chart.js
- Testing: pytest (`pytest tests/`)
- Linting: ruff (`ruff check .`)

## Key Structure
- power_monitor/ - backend RAPL reader and FastAPI app
- templates/ - HTML templates
- static/ - JS/CSS assets
- tests/ - tests
- scripts/systemd/ - systemd unit example
- AGENTS.md - project spec and workflow

## Architectural Decisions
- 2026-07-05: Use RAPL energy counter delta sampling instead of averaging long windows for smoother readings.

## Change Log
Every time agy modifies the project, it MUST append an entry here before finishing:
- Format: `<YYYY-MM-DD> [<type>]: <short description of what changed and why>`
- Types: `feat` / `fix` / `refactor` / `test` / `chore`
- Example: `2026-07-05 [feat]: added /login endpoint with JWT auth - required by Spec feature 2`

## Session Log
- 2026-07-05: Created brand-new power monitor project from Discord request, verified RAPL domains package-0 and dram, delegated implementation to agy.
- 2026-07-05: Completed initial implementation in `/home/veno/Projects/intel-rapl-power-monitor`: FastAPI endpoints `/`, `/healthz`, `/api/power`, `/api/summary`; background 1s RAPL sampler; responsive Chart.js dashboard; pytest suite passing; README with run/verification/chmod/systemd steps; created PR #1 against ImKnifSword/intel-rapl-power-monitor.
