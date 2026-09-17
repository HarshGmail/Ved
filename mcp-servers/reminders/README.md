# reminders — MCP server

The first Ved MCP server. Creates and manages reminders, backed by the same
PostgreSQL database as the backend.

## Tools

| Tool | Arguments | Returns |
| --- | --- | --- |
| `reminders.create` | `text`, `due_at` | The created reminder |
| `reminders.list` | `include_completed=false`, `limit=20` | Reminders, soonest first |
| `reminders.complete` | `reminder_id` | The completed reminder |

All three return structured output with a declared schema, so a model gets typed
fields rather than having to parse prose.

## Running

```bash
uv sync
uv run ved-mcp-reminders          # stdio transport
```

Needs `VED_DATABASE_URL` pointing at a database with the `reminders` table —
start `infra/` and run the backend's Alembic migrations first. The table is
owned by the backend's migrations, not by this server.

```bash
uv run pytest                     # skips DB tests unless VED_TEST_DATABASE_URL is set
uv run ruff check .
```

Database-backed tests drop and recreate tables, so they need a **separate**
database:

```bash
docker compose -f ../../infra/compose.yaml exec db \
  psql -U ved -d postgres -c "CREATE DATABASE ved_test OWNER ved;"

VED_TEST_DATABASE_URL=postgresql+psycopg://ved:PASSWORD@localhost:5432/ved_test uv run pytest
```

## Design notes

**`due_at` must carry a UTC offset.** A naive `2026-09-17T20:00:00` is rejected
rather than assumed to be UTC or server-local. "Remind me at 8 PM" that fires at
1:30 AM is worse than an error the model can correct, and the error text tells it
exactly what to send.

**Validation failures raise `ToolError`.** The SDK returns a `ToolError`'s
message to the caller but redacts every other exception as a generic "Error
executing tool" — so a model can recover from a bad argument only if the error is
raised as `ToolError`. Unexpected crashes should stay generic; that is the point
of the distinction.

**Storage is separate from tool definitions.** `storage.py` takes a session and
knows nothing about MCP, so the query logic is testable without a protocol
client. The queries stay here rather than in `ved-db`: that package holds the
schema, not each service's business rules.

**`limit` is capped server-side** at `VED_MAX_LIST_LIMIT` (default 100). A model
asking for 10,000 reminders gets 100.

**Completion is idempotent.** Completing an already-completed reminder returns
the existing record rather than moving the timestamp — retries are safe.

**The schema comes from `packages/ved-db`.** This server does not define the
`Reminder` table; it imports it, as the backend does. The backend owns the
migrations that create it — this server only reads and writes rows, never runs
DDL.
