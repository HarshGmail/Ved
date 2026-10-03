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

Database-backed tests drop and recreate every table, so they need their own
database and are skipped without one:

```bash
VED_TEST_DATABASE_URL=postgresql+psycopg://ved:PASSWORD@localhost:5432/ved_test \
  uv run pytest
```

The fixture refuses any database whose name does not contain `test`. Pointing
it at the real database would otherwise wipe it.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness probe, including live database connectivity |
| POST | `/agent/message` | Send a prompt; Ved answers, calling MCP tools as needed |
| GET | `/conversations` | Recent conversations, most recently used first |
| GET | `/conversations/{id}` | Full transcript, including the tool calls each turn made |
| GET | `/push/status` | Whether push is configured, and how many devices subscribed |
| POST | `/push/subscribe` | Register a browser's push subscription |
| POST | `/push/unsubscribe` | Drop one by endpoint |
| POST | `/push/test` | Send a test notification to every subscribed device |

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

**Order comes from a `sequence` column, not `created_at`.** Both messages in a
turn are written in one transaction, so `now()` gives them an identical
timestamp and the tie breaks arbitrarily — on a table with real statistics
Postgres returned the answer before the prompt every time, silently destroying
the follow-up behaviour. Small test tables hid it by happening to come back in
insert order.

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

## Reminders actually firing

Storing a reminder is not reminding anyone. `scheduler.py` runs a background
task in the FastAPI lifespan that polls for reminders now due, claims them, and
pushes a notification.

**Claiming is the important part.** `claim_due_reminders` selects
`FOR UPDATE SKIP LOCKED` and stamps `notified_at` in the same transaction, so a
reminder fires exactly once even if two backend processes poll simultaneously.
Without that, a restart mid-send would notify twice.

**A reminder nothing received is released, not lost.** Claiming marks it sent
up front to avoid double-delivery, but if no device was reachable the stamp is
cleared so the next tick retries. After `give_up_after` (24h) it stops retrying
and logs an error — otherwise an undeliverable reminder would be announced
forever.

The scheduler only runs while the backend does. That is honest about what this
is: good enough on a machine that stays on, which is what the i7 home server is
for. It is not a durable job queue, and does not pretend to be.

`VED_SCHEDULER_POLL_SECONDS` (default 30) trades latency for query volume. A
reminder can fire up to that late.

### Push notifications

Web Push via VAPID — the browser holds a subscription, the backend signs a
message, and the push service (FCM, Mozilla, Apple) delivers it even with Ved
closed.

```bash
uv run python scripts/generate_vapid_keys.py
```

That writes the keypair into `apps/backend/.env` and the public half into
`apps/web-client/.env.local`, both gitignored. **The private key never leaves
this machine**, and rotating it invalidates every existing subscription, so the
script refuses to overwrite silently.

Two behaviours worth knowing:

- **Expired subscriptions are pruned automatically.** A push service answering
  `404` or `410` means that browser's subscription is dead; it is deleted rather
  than retried forever. Browsers rotate endpoints, so this is routine.
- **One dead device does not block the others.** Sends run concurrently and each
  outcome is handled independently, under both a socket timeout and an asyncio
  deadline. A push endpoint that accepts a connection then never answers would
  otherwise stall the scheduler and stop every later reminder.
- **Messages carry a 24-hour TTL.** With the default of zero, a push service may
  discard the message outright if the phone is asleep at that instant.

Without keys configured, due reminders are logged and nothing is sent — the
scheduler still marks them fired, so it is visible but silent.

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
  scheduler.py Polls for due reminders and announces them
  push.py      Web Push delivery and subscription storage
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
| `VED_SCHEDULER_POLL_SECONDS` | `30` | How often due reminders are checked |
| `VED_VAPID_PUBLIC_KEY` | unset | Generated by `scripts/generate_vapid_keys.py` |
| `VED_VAPID_PRIVATE_KEY` | unset | Never commit this |
| `VED_VAPID_SUBJECT` | `mailto:ved@example.com` | Contact the push service can use |
| `VED_REMINDERS_SERVER_DIR` | repo path | Where to launch the reminders MCP server |

`VED_TIMEZONE` is not cosmetic. The reminders server rejects timestamps without
a UTC offset, so this is what turns "8 PM" into `20:00+05:30` rather than a
guess.

## Current state

Phase 2 in progress. Ved remembers across turns, and reminders now actually
fire — a due reminder pushes a notification to subscribed devices with the app
closed. No auth, no streaming, and no semantic search yet.

When routes grow past a handful, split them out of `main.py` into an `api/`
package with routers.
