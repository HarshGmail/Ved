# Ved

Personal AI operating layer (private JARVIS-style assistant), built in phases.
Full architecture and phase list: `docs/master-plan.md` — read it only when the
task needs long-term context, it is long.

## Status

**Phase 1 — first round trip working.** The PWA calls the backend through the
connector and renders `backend ok — v0.1.0` on the home page.

`infra/` has Docker Compose (Postgres + backend) but it is **unverified** — no
container runtime on this Mac yet, so it has never been brought up.

No database wiring, no MCP servers, no auth, no LLM, no streaming.

Next up: install Docker Desktop and bring the stack up, then wire the backend to
Postgres. Remaining steps: `docs/pilot.md`.

## Layout

```
apps/web-client/   Next.js 16 (App Router) + TS PWA
  src/connector/   ONLY place that talks to the backend
  src/app/         manifest.ts, layout, page, backend-status
apps/backend/      FastAPI, uv-managed, Python 3.13
  src/ved_backend/ main.py (app + routes), config.py, schemas.py
  Dockerfile       uv-based image
infra/             compose.yaml (pgvector + backend), db/init/
mcp-servers/       Empty; one server per capability later
docs/              master-plan.md, README.md, pilot.md
```

Not created yet: `esphome/`.

Postgres uses the `pgvector/pgvector` image from the start so Phase 2 semantic
memory needs no migration.

## Rules

- **No backend calls outside `src/connector/`.** It must stay free of React and
  Next imports so it can be lifted into a shared package for a future native
  wrapper. Rationale in `docs/pilot.md`.
- MCP tools are named `<domain>.<verb>` (`reminders.create`).
- The LLM never gets unrestricted system access; sensitive actions go through a
  permission layer.
- Don't build ahead of the current phase.

## Commands

```bash
cd apps/backend && uv run uvicorn ved_backend.main:app --reload   # :8000
cd apps/backend && uv run pytest
cd apps/backend && uv run ruff check .

cd apps/web-client && npm run dev      # :3000
cd apps/web-client && npm run build    # includes the TS check
cd apps/web-client && npm run lint
```

Backend uses **uv** — `uv run` handles the venv, never `pip` or manual activate.

Next.js 16 differs from older versions — `apps/web-client/AGENTS.md` says to
check `node_modules/next/dist/docs/` before writing Next code. It is right.

## Keeping this file current

This file is loaded into every new chat, so it is the cheapest way to avoid
re-exploring the repo. **When a phase or milestone completes, update Status
(and Layout, if folders changed) in the same session that finished the work.**

Keep it short — status, layout, rules, commands. Details belong in `docs/`.
