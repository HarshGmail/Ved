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

`/health` returns `status: "degraded"` and `database: "down"` when Postgres is
unreachable, rather than failing the request — the caller can tell the
difference between "backend is gone" and "backend is up but impaired".

## Layout

```
src/ved_backend/
  main.py      FastAPI app, middleware, routes
  config.py    Settings via VED_-prefixed env vars
  database.py  Async engine, session factory, declarative Base
  models.py    SQLAlchemy models (empty; imported by Alembic autogenerate)
  schemas.py   Pydantic response models
migrations/    Alembic — env.py reads the URL from settings
tests/
```

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
New models must be imported in `models.py` or autogenerate will not see them and
will silently generate an empty migration.

## Configuration

Settings read `VED_`-prefixed env vars, or a local `.env`. See `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VED_DATABASE_URL` | `postgresql+psycopg://ved:ved@localhost:5432/ved` | Database connection |
| `VED_CORS_ALLOW_ORIGINS` | `["http://localhost:3000"]` | JSON list of allowed origins |
| `VED_DATABASE_POOL_SIZE` | `5` | Connection pool size |

## Current state

Phase 1. `/health` and a working database connection — no application tables, no
auth, no LLM, no MCP client yet.

When routes grow past a handful, split them out of `main.py` into an `api/`
package with routers.
