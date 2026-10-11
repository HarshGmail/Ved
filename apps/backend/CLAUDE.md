# Backend

FastAPI, Python 3.13, managed by **uv** — `uv run` handles the venv; never
`pip` or manual activation. Code is in `src/ved_backend/`. Look topics up in
`../../docs/index.json` before searching.

## Rules

- **No vendor SDK outside `llm/`.** A new provider implements both `complete()`
  and `stream()` and registers in `build_provider`; the agent loop doesn't
  change. Never build a client at import time. Moving the model is a URL change
  (`VED_LLM_BASE_URL`): the provider speaks the OpenAI `/v1` shape.
- **The system prompt carries the current time and timezone**, rebuilt every
  turn. A model has no clock and invents dates otherwise. `VED_TIMEZONE` is what
  turns "8 PM" into `20:00+05:30`.
- **One agent loop, `Agent._events`, serves both endpoints**, so their
  guarantees can't drift. Tool failures go back to the model as `is_error`
  results, never raised. `VED_AGENT_MAX_TOOL_ROUNDS` caps a looping model.
- **Tool calls in a round run concurrently**; results go back in call order.
  Each call is shielded from client disconnects.
- **A streamed turn is recorded only on its final answer.** The server mints
  `conversation_id`, and only after the model answers, so a failed turn leaves no
  empty thread.
- **History replays prompts and final answers, never tool calls** — a trimmed
  window of tool calls would be malformed on the wire.
- **Order conversation messages by `sequence`, never `created_at`.** Both
  messages in a turn share a transaction timestamp; small test tables hide the
  tie.
- **Reasoning text is never forwarded or stored**, only the fact that the model
  is thinking. A new tool domain gets a phrase in `ACKNOWLEDGEMENTS`.
- **Reminders are claimed `FOR UPDATE SKIP LOCKED`** with `notified_at` stamped
  in the same transaction. If nothing was reachable the stamp is cleared and it
  retries until `give_up_after`.
- **Birthday reminders and check-ins come from the scheduler and templates,
  never the model.** A check-in is created in the claim transaction and linked
  via `reminders.conversation_id`, so a retry reuses it.
- **Embedding never blocks or fails a turn or an upload.** Indexers run in the
  background; the scheduler tick retries failures. The vector dimension is
  coupled to the column, `VED_EMBEDDING_DIMENSIONS` and the model.
- **Uploaded files are stored by SHA-256, never by their filename.** The type
  is sniffed from the bytes, the size cap is enforced while streaming, and a
  document is `indexed` only when every chunk has a vector.
- Push sends carry a socket timeout, an asyncio deadline and a 24h TTL.
  Subscriptions answering 404/410 are deleted, not retried. VAPID keys live only
  in gitignored `.env`; `generate_vapid_keys.py` refuses to overwrite them.
- MCP servers start once in the lifespan and stay open; one that fails to start
  is logged and skipped. The package is `tools/`, not `mcp/` (that would shadow
  the SDK).

## Database

Tables come from `packages/ved-db`. This app owns the Alembic migrations in
`migrations/`; the URL comes from settings, not `alembic.ini`.

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head      # ./ved migrate does this
uv run alembic check             # models and database agree?
```

A new model must be re-exported from `models.py`, or autogenerate silently
writes an empty migration. Autogenerate also misses sequences and the
`vector` extension; read every generated migration and round-trip it with
`downgrade -1` then `upgrade head`.

## Tests

`uv run pytest` — database tests skip unless `VED_TEST_DATABASE_URL` is set.
Schema setup goes only through `ved_db.testing`, which enables pgvector and
refuses any database without `test` in its name. `llm/stub.py` is the
deterministic provider the agent tests run against, with no model or network.
