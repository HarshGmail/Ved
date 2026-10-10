# Ved

Ved is a personal AI operating layer — a private, self-hosted assistant that will
eventually handle voice and text, search the web, act through MCP tools, keep
long-term memory, back up and search the family photo library, process camera
events, and control home devices. It is built in phases, one reliable capability
at a time, with no upfront hardware spend: the architecture comes first, existing
hardware carries the early phases, and GPUs and cameras are bought only once real
workloads justify them. Every layer is meant to be replaceable — the frontend,
the LLM, and the storage can each be swapped without rewriting the rest.

See [master-plan.md](master-plan.md) for the full long-term architecture and the
complete phase breakdown.

## Where we are

**Phase 2 in progress — memory and reminders.** Ved runs on a local model through
Ollama, remembers each conversation, and pushes reminders to your devices when
they come due, even with the app closed. *"Remind me at 8 PM to call Mom"*
followed by *"actually make it 9 PM"* reschedules the right reminder without the
context being restated.

Not yet: semantic search (pgvector is installed but unused), auth, streaming.

See [pilot.md](pilot.md) for how the first slice was built.

## Repo layout

```text
ved              Short commands for setup and running — ./ved help
apps/
  web-client/    Next.js (App Router) + TypeScript PWA
                 src/connector/  — the only code that talks to the backend
  backend/       Python/FastAPI (uv-managed), owns Alembic migrations
                 src/ved_backend/  — agent loop, memory, scheduler, push,
                                     llm/, tools/ (MCP client)
packages/
  ved-db/        Shared SQLAlchemy schema, imported by backend and MCP servers
infra/           Docker Compose — PostgreSQL (pgvector) + backend
mcp-servers/
  reminders/     First MCP server — create, list, reschedule, complete
  people/        People and birthdays — remember, list, forget
docs/            This documentation
```

Added in later phases:

- `esphome/` — home-automation device configs

## Running locally

Setup and day-to-day commands live in the root [README](../README.md). In short,
after `./ved setup`:

```bash
./ved db       # Postgres, in the background
./ved model    # terminal 1
./ved api      # terminal 2
./ved web      # terminal 3
```

The backend launches the reminders and people MCP servers itself as
subprocesses, so there is nothing extra to start for them.

### Icons

Every icon — favicon, PWA, Apple touch — is generated from
`apps/web-client/assets/ved-mark.png`. Change that file and re-run
`scripts/generate-icons.py`; the outputs are build artifacts, not to be edited
by hand. Details and the reasoning behind the variants are in
[../apps/web-client/scripts/README.md](../apps/web-client/scripts/README.md).

### Testing PWA installability

Install prompts and service workers need a secure context. `localhost` counts as
one, so Chrome will offer to install from `npm run dev`. To test from a phone on
the same network, run `npx next dev --experimental-https` — plain HTTP over a LAN
IP will not register the service worker.
