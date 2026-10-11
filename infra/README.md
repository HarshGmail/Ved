# infra

Docker Compose for running Ved's services together: PostgreSQL and the backend.

Verified working on the dev Mac with Colima.

## Browsing the database

```bash
docker compose --profile tools up -d studio   # http://localhost:5050
```

A web UI over the same Postgres — click through tables, browse rows, run SQL.
Useful for seeing what Ved actually stored rather than inferring it from logs.

It sits behind the `tools` profile so a plain `docker compose up -d` never
starts it: this is a developer convenience, not part of the running system. The
port is bound to `127.0.0.1` like everything else here, and it connects with the
same credentials the backend uses, so it is as privileged as the backend is.
Do not expose it beyond the loopback interface.

## Prerequisites on macOS

No Docker Desktop required. Colima provides the runtime:

```bash
brew install colima docker docker-compose docker-buildx
mkdir -p ~/.docker/cli-plugins
ln -sfn /opt/homebrew/opt/docker-compose/bin/docker-compose ~/.docker/cli-plugins/docker-compose
ln -sfn /opt/homebrew/lib/docker/cli-plugins/docker-buildx ~/.docker/cli-plugins/docker-buildx
colima start --cpu 2 --memory 4
```

Homebrew does not link the Compose and Buildx plugins into Docker's plugin
directory itself, hence the symlinks. Buildx is required — the backend image
uses BuildKit cache mounts, which the legacy builder cannot parse.

`colima stop` when finished; `colima start` again later. The VM persists.

### Behind a TLS-intercepting proxy

On a corporate network that re-signs TLS, image pulls fail inside the VM with
`x509: certificate signed by unknown authority` even though the host works
fine — the VM has its own trust store. Export the CA from the host keychain and
install it in the VM:

```bash
security find-certificate -a -p /Library/Keychains/System.keychain > /tmp/host-cas.pem
# extract the corporate CA chain from that file into /tmp/corp-ca.crt, then:
cat /tmp/corp-ca.crt | colima ssh -- sudo tee /usr/local/share/ca-certificates/corp.crt
colima ssh -- sudo update-ca-certificates
colima ssh -- sudo systemctl restart docker
```

SearXNG makes its own outbound HTTPS requests to search engines, so it needs
the same CA. `./ved db` copies every certificate from the VM's
`/usr/local/share/ca-certificates` into `infra/searxng/ca-certificates/`
(gitignored), which the container installs at startup. Verification stays on.

## Web search

`./ved db` starts SearXNG next to Postgres, on `127.0.0.1:8888` only. Ved's
`web` MCP server queries its JSON API; nothing else in the stack depends on it,
so if it's down only `web.search` fails, and it says so.

It needs `SEARXNG_SECRET` in `infra/.env`. The `ved` script generates one before
any `docker compose` call, because compose refuses to start any service,
Postgres included, while a required variable is missing.

google and brave often refuse automated queries; duckduckgo and wikipedia
usually carry the results. The engine list is in `infra/searxng/settings.yml`.

## First run

```bash
cd infra
cp .env.example .env
# set POSTGRES_PASSWORD in .env — compose refuses to start without it
docker compose up -d --build
```

Then:

```bash
docker compose ps           # both services healthy?
docker compose logs -f      # follow output
curl localhost:8000/health
docker compose down         # stop; add -v to also delete the database volume
```

The web client still runs outside Compose via `npm run dev` — it is a static
frontend and benefits from Next's fast refresh.

## Why these choices

**`pgvector/pgvector:pg18` instead of plain `postgres`.** Stock Postgres plus
the pgvector extension pre-built. Phase 2 needs vector search for semantic
memory; using this image from the start avoids a migration later and costs
nothing now. `db/init/01-extensions.sql` runs `CREATE EXTENSION vector` on first
boot.

**Ports bound to `127.0.0.1`.** `"127.0.0.1:5432:5432"` rather than `"5432:5432"`
means the database is reachable from the host but not from the rest of the
network. Docker publishes ports by punching through the host firewall, so the
shorter form would expose Postgres to anything on the LAN. This matters more
once the stack moves to the home server.

**No password default.** `POSTGRES_PASSWORD` uses `:?`, so Compose fails with a
clear message rather than starting with a guessable credential.

**Named volume mounted at `/var/lib/postgresql`, not `/data`.** Postgres 18
changed this: the image now stores data in a major-version subdirectory so
`pg_upgrade --link` can work across a mount boundary. Mounting the old
`/var/lib/postgresql/data` path makes the container refuse to start. The volume
survives `docker compose down`; only `down -v` destroys it.

**Healthcheck gating.** The backend waits for `pg_isready`, not just for the
container to exist, so it does not start against a database still initializing.

## Not covered yet

Production concerns, all later phases: reverse proxy and TLS, the public domain,
secrets beyond a local `.env` file, backups of the database volume, log
shipping, and resource limits. This file is for local development on the Mac.

The backend reads `VED_DATABASE_URL` and `/health` reports live database
connectivity, but no application tables exist yet — `migrations/versions/` is
empty until the first real model lands.
