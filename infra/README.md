# infra

Docker Compose for running Ved's services together: PostgreSQL and the backend.

> **Not yet verified by running.** These files were written on a machine without
> a container runtime installed. The YAML and Dockerfile are reviewed but the
> stack has never been brought up — expect to fix something on the first
> `docker compose up`. Remove this note once it runs.

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

**Named volume for database data.** `db-data` survives `docker compose down`.
Only `down -v` destroys it.

**Healthcheck gating.** The backend waits for `pg_isready`, not just for the
container to exist, so it does not start against a database still initializing.

## Not covered yet

Production concerns, all later phases: reverse proxy and TLS, the public domain,
secrets beyond a local `.env` file, backups of the database volume, log
shipping, and resource limits. This file is for local development on the Mac.

The database is also **not yet wired to the backend** — `VED_DATABASE_URL` is
passed into the container, but nothing reads it. That is the next step in
`docs/pilot.md`.
