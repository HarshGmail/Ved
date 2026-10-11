# MCP servers

One server per capability, each its own uv project, run over stdio by the
backend. Look topics up in `../docs/index.json` before searching.

| Server | Tools |
| --- | --- |
| `reminders/` | `reminders.create`, `.list`, `.reschedule`, `.complete` |
| `people/` | `people.remember`, `.list`, `.forget` |
| `memory/` | `memory.search`, `documents.search`, `documents.list` |
| `web/` | `web.search` (swappable provider), `web.fetch` |

## Rules

- **Tools are named `<domain>.<verb>`.**
- **MCP SDK is v2**: `MCPServer`, not `FastMCP`. `Context` must be imported
  bare from `mcp.server.mcpserver.context`, or it leaks into the tool schema.
  Lifespan state is at `ctx.request_context.lifespan_context`.
- **Return Pydantic models, not `dict`**, or the tool has no output schema.
- **Raise `ToolError` for bad input.** Other exceptions reach the model as a
  generic message it cannot act on.
- **Servers read and write rows; they never run DDL.** Tables come from
  `packages/ved-db`; the backend owns migrations.
- **Prefer `reminders.reschedule` over complete-then-create.** The old chain
  marked reminders done that the user never finished.
- **Content from outside is untrusted.** `web.*` and `documents.*` results carry
  `untrusted: true`.
- **`web.fetch` checks addresses at connect time**, through
  `PublicOnlyTransport`: it refuses non-public addresses, connects to the exact
  address it checked, and re-checks every redirect. Never route around it.
- **A search provider lives only in `web/src/ved_web/search/providers/`**;
  `server.py` never names one. Adding one is a file, an entry in `PROVIDERS`,
  its tests and its settings; see `web/README.md`.

## Adding a server

A new server also needs: a Dockerfile stage in `apps/backend/Dockerfile`, a
`configured_servers` entry in `apps/backend/src/ved_backend/tools/servers.py`,
its directory setting in the backend's `config.py`, a CI job in
`.github/workflows/ci.yml`, and a `uv sync` line in `./ved setup`. Copy
`people/` as the template.

## Tests

`uv run ruff check . && uv run pytest` in each server. Database tests need
`VED_TEST_DATABASE_URL` and set up schema only through `ved_db.testing`.
