# ved-db

The only place database tables are defined. The backend and every MCP server
import these models through `[tool.uv.sources]` (path, editable).

## Rules

- **Never redeclare a model in a service.** Add it here.
- **A new model must also be re-exported** from `src/ved_db/__init__.py` and
  from `apps/backend/src/ved_backend/models.py`, or Alembic autogenerate writes
  an empty migration. The migration itself lives in `apps/backend/migrations/`.
- **Conversation messages order by `sequence`**, a database sequence, never by
  `created_at`.
- **Vectors are `vector(768)`** to match `nomic-embed-text` and
  `VED_EMBEDDING_DIMENSIONS`. Changing the model means a migration and a
  re-embed.
- **`testing.py` is the only database test fixture.** It creates required
  extensions before `create_all` and refuses a database without `test` in its
  name. Every suite uses it; never hand-copy schema setup into a suite.
