@AGENTS.md

# Web client

Next.js 16 App Router + TypeScript PWA. Look topics up in
`../../docs/index.json` before searching.

## Rules

- **Next.js 16 differs from older versions.** Check `node_modules/next/dist/docs/`
  before writing Next code (see `AGENTS.md` above). It has been right every time.
- **`src/connector/` is the only code that talks to the backend.** It has no
  React or Next imports, so it can move into a shared package for a native
  wrapper later. Components call `connector.*`, never `fetch`.
- **Replies stream over SSE through `connector.streamMessage`**, which uses
  `fetch` because `EventSource` can't `POST`. `sse.ts` buffers events split
  across chunks. If streaming is unavailable the chat falls back to
  `sendMessage`.
- **The open conversation lives in the URL as `?c=<id>`**, written with
  `history.pushState`. `useSearchParams` needs a `<Suspense>` boundary.
- **Assistant replies render as markdown** through `markdown-reply.tsx`. Raw
  HTML is never rendered; links open with `rel="noopener noreferrer"`.
- **Every icon is generated from `assets/ved-mark.png`** by
  `scripts/generate-icons.py`. Never hand-edit the outputs.
- Push needs a secure context: `localhost` or real HTTPS. A `192.168.x.x`
  address is not enough.

## Commands

```bash
npm run dev          # ./ved web does this, on :3000
npm run lint
npm run build        # includes the type check
uv run --with pillow python scripts/generate-icons.py
```

There is no web test runner yet. Verify UI changes in a real browser.
