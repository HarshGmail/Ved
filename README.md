# Ved

A private, self-hosted personal AI assistant. You chat with it in a PWA, it acts
through MCP tools, it remembers the conversation, and it pushes reminders to
your devices. The model runs locally, so nothing leaves your machine.

Architecture, status and phase plan: [docs/README.md](docs/README.md).

## Quick start

After the one-time setup below, starting Ved is four commands:

```bash
./ved db       # Postgres, in the background
./ved model    # terminal 1: the local model
./ved api      # terminal 2: the backend
./ved web      # terminal 3: the web client
```

Then open <http://localhost:3000>. Each service gets its own terminal so you can
see its logs. `./ved help` lists every command, and `./ved status` shows what's
running.

## What runs where

| Piece | Command | Port |
| --- | --- | --- |
| PostgreSQL + pgvector | `./ved db` (Docker) | 5432 |
| SearXNG (web search) | `./ved db` (Docker) | 8888 |
| Local LLM (Ollama) | `./ved model` | 11434 |
| Backend (FastAPI) | `./ved api` | 8000 |
| Reminders MCP server | started by the backend | — |
| People MCP server | started by the backend | — |
| Memory MCP server | started by the backend | — |
| Web MCP server | started by the backend | — |
| Web client (Next.js PWA) | `./ved web` | 3000 |
| DB browser (optional) | `./ved studio` (Docker) | 5050 |

## First-time setup

Written for macOS on Apple silicon. Run everything from the repo root.

### 1. Install the tools

```bash
brew install uv node ollama colima docker docker-compose docker-buildx

mkdir -p ~/.docker/cli-plugins
ln -sfn /opt/homebrew/opt/docker-compose/bin/docker-compose ~/.docker/cli-plugins/docker-compose
ln -sfn /opt/homebrew/lib/docker/cli-plugins/docker-buildx ~/.docker/cli-plugins/docker-buildx
```

Colima stands in for Docker Desktop. Homebrew doesn't link the Compose and Buildx
plugins where Docker looks for them, hence the symlinks.

On a corporate network that intercepts TLS, image pulls fail until the Colima VM
trusts your company's CA. The fix is in [infra/README.md](infra/README.md).

### 2. Run setup

```bash
./ved setup
```

The first run creates three gitignored env files and stops, asking for a
password. Set it in two places:

- `infra/.env`: `POSTGRES_PASSWORD=<choose one>`
- `apps/backend/.env`: put the **same password** into `VED_DATABASE_URL`, in
  place of the second `ved` in `ved:ved@`

Then run `./ved setup` again. This time it installs dependencies, generates the
push-notification keys, starts Postgres, creates the tables and installs the web
client. It's safe to re-run, because existing env files and keys are kept.

The password is baked into the database volume the first time Postgres starts.
Changing it later means `docker compose down -v` in `infra/`, which deletes all
data.

### 3. Download the models

```bash
./ved model                    # in one terminal, leave it running
ollama pull qwen3.6:35b        # in another: the chat model, a 22GB download
ollama pull nomic-embed-text   # the embedding model for search, small
```

For a quicker start, `ollama pull granite4.1:3b` (2GB) also works as the chat
model: set `VED_LLM_MODEL=granite4.1:3b` in `apps/backend/.env`.

Without the embedding model, chat still works, but Ved can't search past
conversations.

Setup is done. Start Ved with the [quick start](#quick-start) commands.

## Using it as an app

1. **Install it.** In Chrome, click the install icon at the right of the address
   bar. Ved opens in its own window and appears in the Dock.
2. **Turn on reminders.** Click **Enable reminders**, allow notifications, then
   **Send test**.
3. **Try it.** Ask *"remind me in 2 minutes to stretch"* and close the window.
   The notification arrives anyway.

Other things it understands:

- *"Mom's birthday is March 4th, remind me 15 days before."* Every year from
  then on, you get a reminder 15 days ahead and another on the day.
- *"What did I decide about the home server?"* It searches past conversations
  by meaning, so the wording doesn't have to match.
- *"What's the latest Python release?"* It searches the web through your own
  SearXNG instance, reads the relevant page and answers from it.

The first message after a pause can take a minute or two while the model loads
into memory. Later messages are much faster.

If the test notification never shows, check **System Settings → Notifications →
Google Chrome**. macOS can mute it.

`localhost` counts as a secure context, so installing and push both work here.
Opening it from another device needs HTTPS. A plain `192.168.x.x` address isn't
enough.

## Using it from your phone

`./ved phone` serves Ved privately to your own devices over Tailscale, with real
HTTPS, so install-to-home-screen and notifications work on the phone too.
Nothing is exposed to the public internet. Setup steps, including installing
Tailscale on both devices: [docs/phone-access.md](docs/phone-access.md).

## Commands

| Command | What it does |
| --- | --- |
| `./ved setup` | One-time setup, safe to re-run |
| `./ved db` | Start Colima and Postgres |
| `./ved model` | Start Ollama; does nothing if it's already running |
| `./ved api` | Start the backend, reloading on code changes |
| `./ved web` | Start the web client |
| `./ved status` | Show which services are up |
| `./ved migrate` | Apply new database migrations, after pulling changes |
| `./ved studio` | Start the DB browser at <http://localhost:5050> |
| `./ved phone` | Serve Ved to your phone over Tailscale |
| `./ved phone off` | Stop serving it to your phone |
| `./ved stop` | Stop the Docker backend if it's holding port 8000 |
| `./ved down` | Stop all containers and Colima, freeing about 4GB |

To stop the services in terminals, press Ctrl+C in each one. Your data stays in
the Docker volume.

**Running the backend in Docker instead.** `cd infra && docker compose up -d
--build` starts a containerized backend on port 8000. Don't also run `./ved
api`, or the two fight over the port. The container reads `infra/.env`, so copy
the `VED_VAPID_*` lines from `apps/backend/.env` into it, or push stays off.

## Tests

The database tests drop every table, so they need their own database. Create it
once:

```bash
cd infra
docker compose exec db psql -U ved -d postgres -c "CREATE DATABASE ved_test OWNER ved;"
```

Then:

```bash
export VED_TEST_DATABASE_URL=postgresql+psycopg://ved:PASSWORD@localhost:5432/ved_test

cd apps/backend && uv run pytest && uv run ruff check .
cd mcp-servers/reminders && uv run pytest
cd mcp-servers/people && uv run pytest
cd mcp-servers/memory && uv run pytest
cd apps/web-client && npm run lint && npm run build
```

Without `VED_TEST_DATABASE_URL` the database tests are skipped, not failed. The
fixture refuses any database whose name doesn't contain `test`, so it can't wipe
your real data by mistake. CI runs all of this on every push.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `backend unreachable` | `./ved api` isn't running |
| `db down` in the status line | Postgres isn't up: `./ved db` |
| `The model did not answer in time` | Model still loading or too slow. Retry, or raise `VED_LLM_TIMEOUT_SECONDS` |
| `Could not reach the model` | `./ved model` isn't running |
| `Push keys are not set up` | Setup didn't finish, or `./ved web` was started before it. Restart `./ved web` |
| `relation "..." does not exist` | Migrations not applied: `./ved migrate` |
| Ved can't find something from a past chat | Embedding model missing: `ollama pull nomic-embed-text`. Older messages are embedded in the background once it's there |
| Phone can't connect | See troubleshooting in [docs/phone-access.md](docs/phone-access.md) |
| `port 8000 is taken` | The Docker backend is running: `./ved stop` |
| Image pulls fail with `x509` | Corporate TLS interception, see [infra/README.md](infra/README.md) |
