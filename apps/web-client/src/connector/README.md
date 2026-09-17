# Connector

The only place in `web-client` that knows how to talk to the Ved backend.

Everything else in the app calls the backend **through this folder** — no `fetch`
to the API outside of here, no hardcoded URLs in components.

## Why it is isolated

The PWA is the first Ved client, not the last. A future native wrapper
(Capacitor / React Native) or a CLI should reuse this logic rather than
reimplement it. To keep that possible, this folder:

- has **no React imports** and no Next.js imports,
- depends only on platform primitives (`fetch`, `WebSocket`, `URL`),
- exports plain functions and types.

That means lifting it out into `packages/connector` later is a folder move plus
a package.json — not a rewrite.

## Layout

| File | Purpose |
| --- | --- |
| `config.ts` | Base URL, auth-token hook, timeout defaults |
| `http.ts` | Typed request function: URL building, auth headers, timeouts, error mapping |
| `stream.ts` | WebSocket wrapper — the seam for streaming chat/tool output |
| `errors.ts` | `HttpError` / `TimeoutError` / `NetworkError` |
| `types.ts` | Shared backend payload types |
| `index.ts` | Composes the above into a `connector` instance |

## Usage

```ts
import { connector } from "@/connector";

const status = await connector.health();
```

## Configuration

Base URL comes from `NEXT_PUBLIC_VED_API_URL`, defaulting to
`http://localhost:8000`. See `.env.example`.

## Current state

Phase 0 scaffold. The shape is real; the backend is not. `health()` is the only
declared endpoint and nothing serves it yet — it exists to prove the wiring once
the FastAPI backend lands.

Auth is a seam only: `getAuthToken` is unset, so no `Authorization` header is
sent yet. Streaming is likewise unused — `openStream` is the placeholder for
Phase 4.
