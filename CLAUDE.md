# Ved

Personal AI operating layer (private JARVIS-style assistant), built in phases.
Full architecture and phase list: `docs/master-plan.md` — read it only when the
task needs long-term context, it is long.

## Status

**Phase 0 — architecture skeleton.** Installable PWA shell + connector layer.
No backend, no database, no MCP servers, no infra, no auth, no streaming.

Next up: FastAPI backend with `GET /health`, wired to the connector's existing
`health()` call. Remaining steps: `docs/pilot.md`.

## Layout

```
apps/web-client/   Next.js 16 (App Router) + TS PWA
  src/connector/   ONLY place that talks to the backend
  src/app/         manifest.ts, layout, placeholder page
mcp-servers/       Empty; one server per capability later
docs/              master-plan.md, README.md, pilot.md
```

Not created yet: `apps/backend/`, `infra/`, `esphome/`.

## Rules

- **No backend calls outside `src/connector/`.** It must stay free of React and
  Next imports so it can be lifted into a shared package for a future native
  wrapper. Rationale in `docs/pilot.md`.
- MCP tools are named `<domain>.<verb>` (`reminders.create`).
- The LLM never gets unrestricted system access; sensitive actions go through a
  permission layer.
- Don't build ahead of the current phase.
- ESPHome / home-automation files in this repo are managed separately — leave
  them alone unless asked.

## Commands

```bash
cd apps/web-client
npm run dev     # localhost:3000
npm run build   # includes the TS check
npm run lint
```

Next.js 16 differs from older versions — `apps/web-client/AGENTS.md` says to
check `node_modules/next/dist/docs/` before writing Next code. It is right.

## Keeping this file current

This file is loaded into every new chat, so it is the cheapest way to avoid
re-exploring the repo. **When a phase or milestone completes, update Status
(and Layout, if folders changed) in the same session that finished the work.**

Keep it short — status, layout, rules, commands. Details belong in `docs/`.
