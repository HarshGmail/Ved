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
| GET | `/health` | Liveness probe — `{"status": "ok", "version": "0.1.0"}` |

## Layout

```
src/ved_backend/
  main.py      FastAPI app, middleware, routes
  config.py    Settings via VED_-prefixed env vars
  schemas.py   Pydantic response models
tests/
```

## Configuration

Settings read `VED_`-prefixed env vars, or a local `.env`. See `.env.example`.
`VED_CORS_ALLOW_ORIGINS` defaults to `["http://localhost:3000"]` — the web
client's dev origin.

## Current state

Phase 1, first slice. `/health` exists so the web client's connector has a real
endpoint to reach; it verifies the request path end to end, nothing more.

No database, no auth, no LLM, no MCP client yet. When routes grow past a handful,
split them out of `main.py` into an `api/` package with routers.
