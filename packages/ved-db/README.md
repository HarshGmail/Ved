# ved-db

The single definition of Ved's database schema. Every process that touches
PostgreSQL imports its models from here.

## Why it exists

SQLAlchemy models are a Python description of a table; PostgreSQL holds the
actual table. When the backend and an MCP server each carried their own copy of
`Reminder`, one table had two descriptions that could silently disagree — a
column added in one place breaks the other at runtime, when a tool call fails,
rather than at deploy time.

One definition, imported by both, makes that impossible.

## Layout

```
src/ved_db/
  models.py   Declarative Base and table models
  engine.py   Async engine and session-factory helpers
```

## Usage

```python
from ved_db import Reminder, create_engine, create_session_factory

engine = create_engine(database_url)
session_factory = create_session_factory(engine)
```

Consumers depend on it as a local path:

```toml
dependencies = ["ved-db"]

[tool.uv.sources]
ved-db = { path = "../../packages/ved-db", editable = true }
```

## Ownership

This package defines the schema. The **backend owns the migrations** that apply
it — `apps/backend/migrations/` autogenerates against `ved_db.models.Base`.

Adding a table:

1. Add the model here.
2. Export it from `__init__.py`.
3. Import it in `apps/backend/src/ved_backend/models.py` so autogenerate sees it.
4. Generate and apply the migration from `apps/backend`.

Nothing else creates tables. An MCP server reads and writes rows; it never runs
DDL.

## Deliberately not here

Query logic. This package holds the schema and connection plumbing only — each
service keeps its own queries (the reminders server's live in its `storage.py`),
so services do not accumulate each other's business rules.
