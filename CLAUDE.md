# Ved

Personal AI operating layer (private JARVIS-style assistant), built in phases.
Full architecture and phase list: `docs/master-plan.md` — read it only when the
task needs long-term context, it is long.

## Status

**Phase 1 complete — the first milestone works.** *"Ved, remind me at 8 PM to
call Mom"* typed into the PWA creates a real reminder. The full chain is live:
PWA → connector → `POST /agent/message` → agent loop → MCP stdio →
`reminders.create` → Postgres → phrased answer. Verified in a real browser and
in the container.

A **real local model** now drives it, via Ollama on the Mac — nothing leaves the
machine and there is no API key. Verified end to end in the browser and in the
container: relative times ("tomorrow at 7am") resolve correctly, and the model
recovers from its own bad tool arguments by reading the `ToolError` and retrying.

The `stub` provider stays as the CI fixture, so the agent-loop tests still run
with no model and no network.

**Phase 2 started — Ved remembers.** Conversations persist, and *"remind me at
8 PM to call Mom"* → *"actually make it 9 PM"* reschedules the right reminder
with no context restated (verified against qwen3.6:35b: it chained list →
complete → create on its own).

**Reminders now actually fire.** A background scheduler polls for due reminders
and sends a Web Push notification — your phone buzzes with Ved closed. Verified
end to end in a real browser: asked in the chat, notification arrived.

Not yet: semantic search (pgvector is installed but unused), auth, streaming.

Next up: finish Phase 2 — structured user memory, then embeddings for fuzzy
recall. The plan is explicit that not everything should be an embedding.

## Layout

```text
apps/web-client/   Next.js 16 (App Router) + TS PWA
  src/connector/   ONLY place that talks to the backend
  src/app/         manifest.ts, layout, page, backend-status, chat
                   favicon.ico / icon.png / apple-icon.png are Next file
                   conventions — they generate the <link> tags themselves
  assets/          ved-mark.png, the single source for every icon
  scripts/         generate-icons.py — never hand-edit generated icons
apps/backend/      FastAPI, uv-managed, Python 3.13
  src/ved_backend/ main.py (routes + lifespan), agent.py, memory.py,
                   scheduler.py, push.py, config.py, database.py,
                   models.py, schemas.py
  scripts/         generate_vapid_keys.py — writes to gitignored .env files
    llm/           LLMProvider protocol, openai_compatible.py (any /v1
                   endpoint — Ollama today, GPU box later), stub.py (CI)
    tools/         MCP client — toolbox.py, servers.py (NOT named mcp/)
  migrations/      Alembic (URL comes from settings, not alembic.ini)
  Dockerfile       uv-based image; build context is the REPO ROOT;
                   also installs mcp-servers/reminders so the container can run it
packages/ved-db/   Shared SQLAlchemy schema — the ONLY place tables are defined
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
- **Tables are defined once, in `packages/ved-db`.** Never redeclare a model in a
  service. Consumers depend on it via `[tool.uv.sources]` path + editable. Only
  the backend runs migrations; MCP servers read and write rows, never DDL.
- MCP tools are named `<domain>.<verb>` (`reminders.create`). MCP SDK is **v2** —
  `MCPServer`, not `FastMCP`; `Context` must come from `mcp.server.mcpserver.context`
  (bare, unsubscripted) or it leaks into the tool schema; lifespan state is at
  `ctx.request_context.lifespan_context`. Return Pydantic models, not `dict`, or
  there is no output schema. Raise `ToolError` for bad input — other exceptions
  are redacted to a generic message the model cannot act on.
- **No vendor SDK outside `src/ved_backend/llm/`.** Same rule as the connector —
  the LLM must stay replaceable. Add a provider by implementing `LLMProvider`
  and registering it in `build_provider`; the agent loop does not change. Never
  build a client at import time or the app cannot start without credentials.
- **Moving the model is a URL change, not a code change.** The provider targets
  the OpenAI `/v1` *shape*, not a vendor, so Ollama, LM Studio, llama.cpp, a LAN
  GPU box or a hosted gateway are all `VED_LLM_BASE_URL`. Only Anthropic needs
  its own module; its wire format genuinely differs.
- **The system prompt carries the current time and timezone.** A model has no
  clock — without it, it invents dates (it produced a 2025 timestamp before this
  was added). `agent.py` rebuilds the prompt per turn.
- Local models need `tools` in `ollama show <model>` capabilities, and
  `VED_LLM_TEMPERATURE=0.0` — sampling randomness corrupts tool arguments.
- Tool failures go back to the model as results with `is_error`, never raised —
  that is how it recovers from a bad argument. `VED_AGENT_MAX_TOOL_ROUNDS` caps
  a looping model.
- MCP servers start once in the FastAPI lifespan and stay open; a stdio server
  per request would cost hundreds of ms. A server that fails to start is logged
  and skipped, not fatal.
- **History replays prompts and final answers only, never tool calls.** Tool
  calls are stored for the transcript but not resent: the wire format requires
  every assistant `tool_calls` to be followed by matching `tool` results, so a
  trimmed window would be malformed. The answer already carries the fact.
- The **server** mints `conversation_id`, and only after the model answers — so
  a failed turn leaves no empty thread and a client typo cannot create one.
- **Reminders are claimed `FOR UPDATE SKIP LOCKED`** with `notified_at` stamped
  in the same transaction, so one fires exactly once even with two pollers.
- Push subscriptions answering 404/410 are **deleted, not retried** — browsers
  rotate endpoints and dead ones would otherwise accumulate forever.
- VAPID keys live only in gitignored `.env` files. Rotating them invalidates
  every subscription, so `generate_vapid_keys.py` refuses to overwrite.
- The LLM never gets unrestricted system access; sensitive actions go through a
  permission layer.
- Don't build ahead of the current phase.

## Commands

```bash
colima start                                     # Docker runtime (not Desktop)
cd infra && docker compose up -d                 # Postgres + backend
cd infra && docker compose logs -f db
cd infra && docker compose --profile tools up -d studio   # DB browser :5050

OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve   # the model
ollama list                                      # what is pulled

cd apps/backend && uv run pytest
cd apps/backend && uv run ruff check .
cd apps/backend && uv run alembic upgrade head

curl -X POST localhost:8000/agent/message \                # the whole loop
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Ved, remind me at 8 PM to call Mom"}'

cd mcp-servers/reminders && uv run ved-mcp-reminders
cd mcp-servers/reminders && uv run pytest   # needs VED_TEST_DATABASE_URL

cd apps/web-client && npm run dev      # :3000
cd apps/web-client && npm run build    # includes the TS check
cd apps/web-client && npm run lint
cd apps/web-client && uv run --with pillow python scripts/generate-icons.py
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
- The backend's MCP package is `tools/`, not `mcp/` — that would shadow the
  installed `mcp` SDK.
- `VED_TIMEZONE` (default `Asia/Kolkata`) is load-bearing: the reminders server
  rejects timestamps with no UTC offset, so it is what turns "8 PM" into
  `20:00+05:30`.

Next.js 16 differs from older versions — `apps/web-client/AGENTS.md` says to
check `node_modules/next/dist/docs/` before writing Next code. It is right.

## Keeping this file current

This file is loaded into every new chat, so it is the cheapest way to avoid
re-exploring the repo. **When a phase or milestone completes, update Status
(and Layout, if folders changed) in the same session that finished the work.**

Keep it short — status, layout, rules, commands. Details belong in `docs/`.
