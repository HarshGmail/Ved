# Ved

Ved is a personal AI operating layer — a private, self-hosted assistant that will
eventually handle voice and text, search the web, act through MCP tools, keep
long-term memory, back up and search the family photo library, process camera
events, and control home devices. It is built in phases, one reliable capability
at a time, with no upfront hardware spend: the architecture comes first, existing
hardware carries the early phases, and GPUs and cameras are bought only once real
workloads justify them. Every layer is meant to be replaceable — the frontend,
the LLM, and the storage can each be swapped without rewriting the rest.

See [master-plan.md](master-plan.md) for the full long-term architecture and the
complete phase breakdown.

## Where we are

**Phase 1 — backend and database running.** The PWA calls the backend through
the connector and renders its health, including live database connectivity. No
application tables, no MCP server, no auth, and no LLM yet.

See [pilot.md](pilot.md) for what this slice covers and what comes next.

## Repo layout

```
apps/
  web-client/    Next.js (App Router) + TypeScript PWA
                 src/connector/  — the only code that talks to the backend
  backend/       Python/FastAPI (uv-managed)
                 src/ved_backend/  — app, config, schemas
infra/           Docker Compose — PostgreSQL (pgvector) + backend
mcp-servers/     One subfolder per MCP server (empty; see its README)
docs/            This documentation
```

Added in later phases:

- `esphome/` — home-automation device configs

## Running locally

Both apps, in two terminals. Start the backend first so the web client has
something to reach.

```bash
cd apps/backend
uv sync
uv run uvicorn ved_backend.main:app --reload    # localhost:8000
```

```bash
cd apps/web-client
npm install
npm run dev                                      # localhost:3000
```

Open <http://localhost:3000> — the page should show `backend ok — v0.1.0`. If the
backend is not running it shows `backend unreachable` instead, which is the
expected degraded state, not a crash.

Copy each app's `.env.example` to `.env.local` (web) or `.env` (backend) to
override defaults.

Other commands:

```bash
cd apps/web-client && npm run build   # production build, includes the TS check
cd apps/web-client && npm run lint

cd apps/backend && uv run pytest
cd apps/backend && uv run ruff check .
```

### Running via Docker

`infra/` has a working Compose stack for PostgreSQL (pgvector) plus the backend:

```bash
cd infra
cp .env.example .env   # set POSTGRES_PASSWORD
docker compose up -d --build
```

The dev Mac uses Colima rather than Docker Desktop — setup steps and the
corporate-proxy TLS workaround are in [../infra/README.md](../infra/README.md).

Run the web client with `npm run dev` either way; it is not containerized.

### Testing PWA installability

Install prompts and service workers need a secure context. `localhost` counts as
one, so Chrome will offer to install from `npm run dev`. To test from a phone on
the same network, run `npx next dev --experimental-https` — plain HTTP over a LAN
IP will not register the service worker.
