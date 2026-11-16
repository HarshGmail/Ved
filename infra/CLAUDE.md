# Infra

Docker Compose for Postgres (pgvector), SearXNG, the backend and a DB browser.
Day to day, use `./ved` from the repo root rather than calling compose directly.

## Rules

- **Every port binds to `127.0.0.1`.** Nothing here is meant to be reachable
  from the network; phone access goes through Tailscale serve, never Funnel.
- **SearXNG is optional**, behind the `search` compose profile. `./ved db`
  starts it only while `VED_SEARCH_PROVIDER` is `searxng`, and writes
  `SEARXNG_SECRET` into `infra/.env` first. `db` and `backend` start without it.
- **The backend container reads `infra/.env`**; `./ved api` reads
  `apps/backend/.env`. Run one or the other — both want port 8000.
- **Postgres 18 wants its volume at `/var/lib/postgresql`**, not `.../data`.
- **The voice service has no port.** `ved-voice` (apps/voice) listens on 8300
  inside the compose network, is capped at 1536 MB, and only the backend calls
  it. Its models are downloaded at image build, so the build needs network access.
- **`home` is attached only by `compose.server.yaml`**, used only by `./ved server`
  on the Linux server. The Mac never names it, so `./ved db` and `./ved api` are unchanged.

## The home server

Ubuntu, native Docker (no Colima). `./ved` detects the platform with
`is_macos`; keep both paths working and test Linux changes in an
`ubuntu:24.04` container. The board takes 16 GB at most, so the server sets
`VED_LLM_MODEL` to a small model. Setup steps: `docs/server.md`.

## Machine-specific: corporate networks

These only matter on a network that intercepts TLS (the work laptop). On a
personal machine they are no-ops and can be ignored.

- Docker image pulls fail until the Colima VM trusts the corporate CA. Steps in
  `README.md` here.
- SearXNG's own outbound requests need the same CA. `./ved db` copies the VM's
  certificates into `searxng/ca-certificates/` (gitignored), and does nothing
  when there are none.
- The voice image downloads its models with curl at build time. On a network
  that re-signs TLS, that step fails with a self-signed chain until the CA is
  trusted inside the image; the Colima VM steps above do not cover it.
- Docker runs through Colima, not Docker Desktop. Compose and buildx need
  symlinks into `~/.docker/cli-plugins/`; buildx is required for the backend
  image's cache mounts.
