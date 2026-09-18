# Ved backend

Python/FastAPI. Will eventually host agent orchestration, LLM calls, the MCP
client, memory, and the event bus. Right now it serves one endpoint.

## Running

```bash
cd apps/backend
uv sync
uv run uvicorn ved_backend.main:app --reload
```

Serves at <http://localhost:8000>; interactive docs at `/docs`.

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

`uv sync` creates the venv and installs from `uv.lock` — no manual venv
activation needed, `uv run` handles it.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness probe, including live database connectivity |
| POST | `/agent/message` | Send a prompt; Ved answers, calling MCP tools as needed |

`/health` returns `status: "degraded"` and `database: "down"` when Postgres is
unreachable, rather than failing the request — the caller can tell the
difference between "backend is gone" and "backend is up but impaired".

`/agent/message` returns `503` when no MCP server connected at startup, since
Ved can answer but cannot act. The reply names the `model` that produced it and
lists every `tool_calls` entry with a `failed` flag, so a client can show what
actually happened rather than trusting the prose.

```bash
curl -X POST localhost:8000/agent/message \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Ved, remind me at 8 PM to call Mom"}'
```

## Agent loop

`agent.py` runs the standard cycle: ask the model, run any tools it asked for,
feed the results back, repeat until it answers in prose or hits
`VED_AGENT_MAX_TOOL_ROUNDS`.

Two decisions worth knowing:

**Tool failures are data, not exceptions.** A failed tool call goes back to the
model as a result with `is_error` set, so it can read "due_at must include a UTC
offset" and retry with a corrected argument. Raising would throw away a turn the
model could have recovered from.

**The round limit is a real cap, not a safety net.** A model that keeps calling
tools without answering is stopped and says so, rather than looping until the
request times out.

MCP servers are started once in the FastAPI lifespan and held open, not spawned
per request — see `tools/`. A server that fails to start is logged and skipped;
the rest still work.

## LLM providers

Selected by `VED_LLM_PROVIDER`, default `stub` — a deterministic rule-based fake
that needs no API key and makes the agent loop testable without a network. See
[`src/ved_backend/llm/README.md`](src/ved_backend/llm/README.md) for the
provider contract and how to add a real one.

## Layout

```text
src/ved_backend/
  main.py      FastAPI app, middleware, routes, lifespan
  agent.py     The think → call tools → answer loop
  config.py    Settings via VED_-prefixed env vars
  database.py  Engine and session factory, built from ved-db helpers
  models.py    Re-exports ved-db models so Alembic autogenerate sees them
  schemas.py   Pydantic request and response models
  llm/         Provider interface and implementations
  tools/       MCP client — connects to servers, routes tool calls
migrations/    Alembic — env.py reads the URL from settings
tests/
```

`tools/` is not named `mcp/`: a local package sharing a name with the installed
`mcp` SDK is a shadowing bug waiting to happen.

## Database

Async SQLAlchemy over psycopg 3, against PostgreSQL with pgvector. Start it with
the Compose stack in `infra/`.

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
uv run alembic downgrade -1
```

Alembic takes its URL from `VED_DATABASE_URL` via `migrations/env.py`, not from
`alembic.ini`, so migrations and the app can never target different databases.

Table definitions live in [`packages/ved-db`](../../packages/ved-db), shared with
the MCP servers. This app owns the migrations that apply them. A new model must
be re-exported from `models.py` or autogenerate will not see it and will silently
produce an empty migration.

`uv run alembic check` reports whether the models and the live database agree —
useful after changing either.

## Configuration

Settings read `VED_`-prefixed env vars, or a local `.env`. See `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VED_DATABASE_URL` | `postgresql+psycopg://ved:ved@localhost:5432/ved` | Database connection |
| `VED_CORS_ALLOW_ORIGINS` | `["http://localhost:3000"]` | JSON list of allowed origins |
| `VED_DATABASE_POOL_SIZE` | `5` | Connection pool size |
| `VED_LLM_PROVIDER` | `stub` | Which LLM provider to use |
| `VED_TIMEZONE` | `Asia/Kolkata` | Resolves "8 PM" to a real offset |
| `VED_AGENT_MAX_TOOL_ROUNDS` | `4` | Stops a model that loops on tool calls |
| `VED_REMINDERS_SERVER_DIR` | repo path | Where to launch the reminders MCP server |

`VED_TIMEZONE` is not cosmetic. The reminders server rejects timestamps without
a UTC offset, so this is what turns "8 PM" into `20:00+05:30` rather than a
guess.

## Current state

Phase 1 complete. The full loop works: prompt → provider → MCP tool → database →
answer, verified in a browser and in the container. No auth, no streaming, and
no conversation history — every request starts fresh.

When routes grow past a handful, split them out of `main.py` into an `api/`
package with routers.
