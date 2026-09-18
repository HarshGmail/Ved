# Pilot — the first software slice

The home-automation side of this project started with a single pilot device
rather than a whole house. This is the same idea for the software side: one
small slice, built properly, that everything later plugs into.

## Goal

Get `apps/web-client` running as an installable PWA with a working connector
abstraction. That is the whole goal.

Concretely, done means:

- The app runs with `npm run dev` and builds cleanly.
- It is installable — valid manifest, icons, registered service worker, and it
  survives being added to a home screen on desktop, Android, and iOS.
- All backend-bound code lives behind `src/connector/`, with a typed request
  function, a seam for auth headers, and a seam for WebSocket streaming.

There is no real UI beyond a placeholder page, and no real backend. That is
intentional — this slice is about the shape, not the features.

## Why the connector is isolated

The PWA is the first Ved client, but the master plan already anticipates others:
a Capacitor or React Native wrapper if the PWA hits a native ceiling, and
eventually voice endpoints, TV displays, and a phone photo uploader. Each of
those needs to talk to the same backend.

If backend calls were scattered through React components, every new client would
mean reimplementing URL building, auth, error handling, and reconnect logic —
and the copies would drift. So `src/connector/` is deliberately framework-free:

- no React and no Next.js imports,
- only platform primitives (`fetch`, `WebSocket`, `URL`),
- plain exported functions and types.

The payoff is that lifting it into `packages/connector` later is a folder move
and a `package.json`, not a rewrite. The discipline that keeps this true is a
simple rule: **nothing outside `src/connector/` calls the backend directly.**

This also maps onto design principles 2 and 16 in the master plan — keep the
frontend replaceable, and build modularly so the system can grow for years.

## Not in scope yet

Everything below is a later phase. None of it should be started as part of this
slice:

| Not yet | Phase |
| --- | --- |
| Python/FastAPI backend | 1 |
| Agent orchestrator, LLM integration | 1 |
| MCP client and MCP servers | 1 |
| PostgreSQL, pgvector, memory | 2 |
| Authentication and the permission model | 1–2 |
| Photo upload and storage | 3 |
| Web search, streaming responses, TTS | 4 |
| Voice and wake word | 5 |
| Home automation via MCP | 6 |
| Cameras and vision | 7 |
| `infra/` — Docker, reverse proxy, domain, remote access | 1+ |

The connector has placeholders for auth and streaming so those phases have an
obvious place to land. They are seams, not implementations: `getAuthToken` is
unset and sends no header, and `openStream` is unused.

## Next steps

- [x] Stand up the FastAPI backend in `apps/backend/` with a single `GET /health`
      endpoint.
- [x] Wire the connector's existing `health()` call to it and surface the result
      on the placeholder page — the first real end-to-end round trip.
- [x] Add `infra/` with a Docker Compose file for the backend and PostgreSQL.
- [x] Wire the backend to PostgreSQL — connection pool, Alembic migrations, and
      a `/health` that reports database connectivity.
- [x] Build the first MCP server (`mcp-servers/reminders/`) with
      `reminders.create`, `reminders.list` and `reminders.complete`.
- [x] Add the MCP client and LLM call to the backend, then close the loop from
      the master plan's first milestone: *"Ved, remind me at 8 PM to call Mom."*

The round trip is verified end to end: with both servers running the page
renders `backend ok — v0.1.0` from a real cross-origin browser fetch, and with
the backend stopped it degrades to `backend unreachable` without crashing.

## The first milestone, closed

Typing *"Ved, remind me at 8 PM to call Mom"* into the page now returns
*"Reminder set: call Mom — Sat 19 Sep, 8:00 PM"*, with a row in Postgres to
match. That is the master plan's Phase 1 target — `User → Ved → MCP tool →
result → response` — working in a real browser and in the container.

The provider driving it is a **stub**: a deterministic rule-based fake, not a
language model. That was a deliberate sequencing choice. The hard, reusable part
of this step is the agent loop and the MCP client, and neither needs a real
model to be built or proven. Doing it this way meant no API key was required to
reach the milestone, and it left behind a test double that keeps the loop
testable in CI with no network and no flakiness.

What a real model replaces is one file behind `LLMProvider`. The loop, the tool
routing, the error handling and the round limit all stay. The tradeoff is
honest, though: the stub understands reminder phrasing and nothing else, so Ved
is not yet conversational — it is mechanically correct.

## After the pilot

- [ ] Swap in a real LLM provider (Anthropic, or a local model once a GPU box
      exists) — one new module, registered in `build_provider`.
- [ ] Persist conversations so Ved has history rather than a fresh start each
      request. That is Phase 2, and it is where the privacy question about
      hosted models becomes real.
