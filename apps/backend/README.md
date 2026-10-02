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
| GET | `/conversations` | Recent conversations, most recently used first |
| GET | `/conversations/{id}` | Full transcript, including the tool calls each turn made |

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

Omit `conversation_id` to start a thread; the reply carries the id the server
assigned. Send it back to continue, and Ved remembers:

```bash
curl -X POST localhost:8000/agent/message \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "actually make it 9 PM", "conversation_id": "<id>"}'
```

The server mints the id rather than accepting one from the client, so a typo
cannot silently create a thread. An unknown id is a `404`.

## Conversation memory

`memory.py` loads prior turns and saves each new one; `agent.py` stays unaware
of storage and simply accepts a `history` argument.

**Only user prompts and final answers are replayed** — never the intermediate
tool calls, though those are stored for the transcript. Two reasons. The
OpenAI wire format requires every assistant `tool_calls` to be followed by
matching `tool` results, so trimming a window mid-chain produces a malformed
request. And the answer already contains the fact that mattered ("Reminder set
for 8 PM"); replaying the raw JSON spends a local model's context on detail it
can re-fetch by calling the tool again.

`VED_CONVERSATION_HISTORY_LIMIT` caps how many messages are replayed. It is a
message count, not a token count — a crude bound that is honest about being
crude. Summarising older turns is the obvious next step when it starts to bite.

**A failed turn creates nothing.** The conversation row is written after the
model answers, so an unreachable model leaves no empty thread behind.

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

Selected by `VED_LLM_PROVIDER`:

- **`openai-compatible`** — any endpoint speaking the OpenAI chat-completions
  shape. Runs against a local model by default, so nothing leaves the machine.
- **`stub`** — a deterministic rule-based fake. No model, no network; this is
  what the agent-loop tests run against.

Swapping where the model runs is a URL change, not a code change. See
[`src/ved_backend/llm/README.md`](src/ved_backend/llm/README.md) for the
provider contract, the runtime table, and the tool-calling caveats.

### Running a local model

```bash
brew install ollama
OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve
ollama pull qwen3.6:35b
```

The model must support tool calling — check `ollama show <model>` lists `tools`
under Capabilities, or Ved will get prose where it expects a tool call.

If the endpoint is down, `/agent/message` returns `503` naming the cause rather
than a generic `500`. A local model that is not running is an expected state,
not a crash.

## Layout

```text
src/ved_backend/
  main.py      FastAPI app, middleware, routes, lifespan
  agent.py     The think → call tools → answer loop
  config.py    Settings via VED_-prefixed env vars
  database.py  Engine and session factory, built from ved-db helpers
  models.py    Re-exports ved-db models so Alembic autogenerate sees them
  memory.py    Conversation history — load, record, list, transcript
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
| `VED_LLM_PROVIDER` | `stub` | `stub` or `openai-compatible` |
| `VED_LLM_BASE_URL` | `http://localhost:11434/v1` | Where the model is served |
| `VED_LLM_MODEL` | `qwen3.6:35b` | Model name at that endpoint |
| `VED_LLM_API_KEY` | unset | Only for hosted endpoints |
| `VED_LLM_TEMPERATURE` | `0.0` | 0 keeps tool arguments deterministic |
| `VED_LLM_TIMEOUT_SECONDS` | `120.0` | A cold local model loads slowly |
| `VED_TIMEZONE` | `Asia/Kolkata` | Resolves "8 PM" to a real offset |
| `VED_AGENT_MAX_TOOL_ROUNDS` | `4` | Stops a model that loops on tool calls |
| `VED_CONVERSATION_HISTORY_LIMIT` | `20` | Messages replayed into each turn |
| `VED_CONVERSATION_LIST_LIMIT` | `50` | Conversations `/conversations` returns |
| `VED_REMINDERS_SERVER_DIR` | repo path | Where to launch the reminders MCP server |

`VED_TIMEZONE` is not cosmetic. The reminders server rejects timestamps without
a UTC offset, so this is what turns "8 PM" into `20:00+05:30` rather than a
guess.

## Current state

Phase 2 in progress. The full loop works and Ved now remembers: *"remind me at
8 PM to call Mom"* followed by *"actually make it 9 PM"* reschedules the right
reminder without the context being restated. No auth, no streaming, and no
semantic search yet.

When routes grow past a handful, split them out of `main.py` into an `api/`
package with routers.
