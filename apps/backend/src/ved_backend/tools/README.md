# MCP client

Connects to Ved's MCP servers and routes the model's tool calls to whichever
server owns each tool.

Named `tools/` rather than `mcp/` on purpose: a local package sharing a name
with the installed `mcp` SDK invites an import-shadowing bug that only shows up
at runtime.

## How it works

`MCPToolbox` opens every configured server once, during the FastAPI lifespan,
and keeps the connections open for the process. Each stdio server is a
subprocess, so spawning one per request would add hundreds of milliseconds to
every message for no benefit.

At startup it calls `list_tools()` on each server and builds a name → server
routing table. The tool list handed to the model is therefore whatever the
servers actually expose, not a hardcoded copy that can drift.

**A server that fails to start is logged and skipped.** One broken server should
not take down the whole assistant — the others still work, and `/agent/message`
only returns `503` when nothing connected at all.

## Tool results

`render_result` prefers `structured_content`, falling back to concatenated text
blocks. Since every Ved tool returns a Pydantic model, the model gets compact
JSON rather than prose it would have to parse.

`call()` returns `(content, is_error)` instead of raising on tool failure. The
agent feeds errors back to the model so it can correct a bad argument — see
`agent.py`.

## Adding a server

Add it to `configured_servers` in `servers.py`. Environment is built from
`get_default_environment()` — the SDK's allowlist of variables safe to inherit —
plus what the server needs, which is how `VED_DATABASE_URL` reaches the
reminders server without leaking the parent's whole environment.
