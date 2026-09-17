# Ved

Personal AI operating layer (private JARVIS-style assistant), built in phases.
Full architecture and phase list: `docs/master-plan.md` — read it only when the
task needs long-term context, it is long.

## Status

**Phase 1 — first MCP server working.** PWA → connector → backend → Postgres is
live, and `mcp-servers/reminders/` serves `reminders.create/list/complete` over
stdio against the same database (verified with a real MCP client).

Not yet: MCP client in the backend, LLM, auth, streaming.

Next up: wire the MCP client + an LLM into the backend to close the master
plan's first milestone — *"Ved, remind me at 8 PM to call Mom."*

## Layout

```
apps/web-client/   Next.js 16 (App Router) + TS PWA
  src/connector/   ONLY place that talks to the backend
  src/app/         manifest.ts, layout, page, backend-status
apps/backend/      FastAPI, uv-managed, Python 3.13
  src/ved_backend/ main.py, config.py, database.py, models.py, schemas.py
  migrations/      Alembic (URL comes from settings, not alembic.ini)
  Dockerfile       uv-based image (needs BuildKit)
infra/             compose.yaml (pgvector + backend), db/init/
mcp-servers/
  reminders/       MCP server (SDK v2), stdio, own uv project
docs/              master-plan.md, README.md, pilot.md
```

Not created yet: `esphome/`.

Postgres uses the `pgvector/pgvector` image from the start so Phase 2 semantic
memory needs no migration.

## Rules

- **No backend calls outside `src/connector/`.** It must stay free of React and
  Next imports so it can be lifted into a shared package for a future native
  wrapper. Rationale in `docs/pilot.md`.
- MCP tools are named `<domain>.<verb>` (`reminders.create`). MCP SDK is **v2** —
  `MCPServer`, not `FastMCP`; `Context` must come from `mcp.server.mcpserver.context`
  (bare, unsubscripted) or it leaks into the tool schema; lifespan state is at
  `ctx.request_context.lifespan_context`. Return Pydantic models, not `dict`, or
  there is no output schema. Raise `ToolError` for bad input — other exceptions
  are redacted to a generic message the model cannot act on.
- The LLM never gets unrestricted system access; sensitive actions go through a
  permission layer.
- Don't build ahead of the current phase.

## Commands

```bash
colima start                                     # Docker runtime (not Desktop)
cd infra && docker compose up -d                 # Postgres + backend
cd infra && docker compose logs -f db

cd apps/backend && uv run pytest
cd apps/backend && uv run ruff check .
cd apps/backend && uv run alembic upgrade head

cd mcp-servers/reminders && uv run ved-mcp-reminders
cd mcp-servers/reminders && uv run pytest   # needs VED_TEST_DATABASE_URL

cd apps/web-client && npm run dev      # :3000
cd apps/web-client && npm run build    # includes the TS check
cd apps/web-client && npm run lint
```

Backend uses **uv** — `uv run` handles the venv, never `pip` or manual activate.

Gotchas already solved, don't rediscover them:

- Docker runs via **Colima**, not Desktop. Compose/buildx need symlinks into
  `~/.docker/cli-plugins/`; buildx is required for the Dockerfile's cache mounts.
- On the corporate network, TLS is intercepted — the Colima VM needs the FactSet
  CA installed or image pulls fail. Steps in `infra/README.md`.
- Postgres 18 wants the volume at `/var/lib/postgresql`, not `.../data`.
- New SQLAlchemy models must be imported in `models.py` or Alembic autogenerate
  silently produces an empty migration.

Next.js 16 differs from older versions — `apps/web-client/AGENTS.md` says to
check `node_modules/next/dist/docs/` before writing Next code. It is right.

## Keeping this file current

This file is loaded into every new chat, so it is the cheapest way to avoid
re-exploring the repo. **When a phase or milestone completes, update Status
(and Layout, if folders changed) in the same session that finished the work.**

Keep it short — status, layout, rules, commands. Details belong in `docs/`.
