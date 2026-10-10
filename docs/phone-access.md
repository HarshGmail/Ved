# Using Ved from your phone

Ved runs on your Mac. Tailscale gives your phone a private, encrypted path to it,
and `tailscale serve` adds the HTTPS that push notifications and
add-to-home-screen require. Nothing is exposed to the public internet: this uses
`tailscale serve`, never Funnel, so only devices signed in to your tailnet can
reach Ved.

## One-time setup

1. Install Tailscale on the Mac and on the phone, and sign both in to the same
   account.
2. In the Tailscale admin console, open the DNS page, make sure MagicDNS is on,
   and choose Enable HTTPS under HTTPS Certificates. Tailscale publishes your
   machine names (not your tailnet's identity) in public certificate logs, so
   rename the Mac first if its name is sensitive.
3. Make sure Ved is running: `./ved db`, `./ved model`, `./ved api`, `./ved web`.

## Connect

```bash
./ved phone
```

It finds the Mac's `*.ts.net` hostname and serves:

| URL                          | Forwards to             |
| ---------------------------- | ----------------------- |
| `https://<host>`             | web client, `127.0.0.1:3000` |
| `https://<host>:8443`        | backend, `127.0.0.1:8000`    |

It also writes three values, keeping the rest of each file intact:

| File                        | Key                        | Value                      |
| --------------------------- | -------------------------- | -------------------------- |
| `apps/web-client/.env.local` | `NEXT_PUBLIC_VED_API_URL`  | `https://<host>:8443`      |
| `apps/web-client/.env.local` | `VED_TAILNET_HOST`         | `<host>`                   |
| `apps/backend/.env`          | `VED_CORS_ALLOW_ORIGINS`   | adds `https://<host>`      |

Restart `./ved api` and `./ved web` afterwards. The web client bakes
`NEXT_PUBLIC_VED_API_URL` in at start, and the backend reads CORS only at start.

The serve config is saved by Tailscale and survives reboots, but the env values
are what Ved reads, so run `./ved phone` again only if the hostname changes.

The Mac's own browser keeps working at `http://localhost:3000`: the backend still
allows that origin, and it now reaches the backend through the `:8443` URL.

## On the phone

1. Open `https://<host>` in Safari (iPhone) or Chrome (Android).
2. Install it.
   - iPhone: Share, then Add to Home Screen. Open Ved from that icon from now on.
     iOS only delivers Web Push to a PWA installed this way, not to a Safari tab.
   - Android: menu, then Install app.
3. In the installed app, enable reminders and allow notifications.
4. Ask for a reminder a minute away to confirm the push arrives with Ved closed.

## Turning it off

```bash
./ved phone off
```

This removes the serve config for ports 443 and 8443. The env values stay; local
use at `http://localhost:3000` is unaffected as long as the backend still allows
`http://localhost:3000` in CORS.

## Troubleshooting

**`Tailscale is not installed`**: install it, or open the app once so
`/Applications/Tailscale.app` exists. The script looks for `tailscale` on `PATH`
and in the app bundle.

**`not logged in or not running`**: sign in to Tailscale on the Mac and retry.

**`tailscale serve` asks to enable HTTPS**: it prints a link. Open it, or follow
step 2 above, then rerun `./ved phone`.

**Phone cannot load the page**: confirm Tailscale is connected on both devices,
`./ved status` shows web and backend up, and the Mac is awake. A sleeping Mac
drops off the tailnet. Check the mapping with `tailscale serve status`.

**Page loads but the chat says the backend is unreachable**: the web client was
started before `NEXT_PUBLIC_VED_API_URL` changed, or the backend before its CORS
change. Restart both. The browser console shows a CORS error if the origin is
missing from `VED_CORS_ALLOW_ORIGINS`.

**Page loads but looks broken or hot reload fails in dev**: the Next dev server
blocks unknown origins. `VED_TAILNET_HOST` in `apps/web-client/.env.local` feeds
`allowedDevOrigins`; check it holds the bare hostname, then restart `./ved web`.

**Reminders arrive on the Mac but not the phone**: on iPhone the app must be
opened from the home-screen icon, with notifications allowed in iOS Settings.
Enable reminders again in the app so the phone registers its own subscription.

**Certificate warnings**: HTTPS must be enabled for the tailnet (step 2) and
the URL must use the full `*.ts.net` name, not an IP address.

**Hostname changed** (machine renamed or tailnet renamed): run `./ved phone`
again and restart the api and web.
