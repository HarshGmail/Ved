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

**Phase 0 — architecture skeleton only.** There is no backend, no database, no
MCP server, and no infrastructure yet. What exists is an installable PWA shell
with an isolated connector layer, ready for a backend to be pointed at it.

See [pilot.md](pilot.md) for what this first slice covers and what comes next.

## Repo layout

```
apps/
  web-client/    Next.js (App Router) + TypeScript PWA
                 src/connector/  — the only code that talks to the backend
mcp-servers/     One subfolder per MCP server (empty; see its README)
docs/            This documentation
```

Added in later phases:

- `infra/` — Docker Compose, deployment, reverse proxy, backups
- `esphome/` — home-automation device configs
- `apps/backend/` — the Python/FastAPI backend

## Running web-client locally

```bash
cd apps/web-client
npm install
npm run dev
```

The app serves at <http://localhost:3000>.

Copy `.env.example` to `.env.local` to point the connector somewhere other than
the default `http://localhost:8000`.

Other commands:

```bash
npm run build   # production build (also runs the TypeScript check)
npm run lint
```

### Testing PWA installability

Install prompts and service workers need a secure context. `localhost` counts as
one, so Chrome will offer to install from `npm run dev`. To test from a phone on
the same network, run `npx next dev --experimental-https` — plain HTTP over a LAN
IP will not register the service worker.
