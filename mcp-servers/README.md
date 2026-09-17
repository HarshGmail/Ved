# MCP servers

Empty for now — no server implementations exist yet.

Each subfolder here will eventually be **one MCP server covering one
capability**. Keeping them separate means a capability can be developed,
restarted, secured, or removed without touching the others, and the backend can
connect to whichever subset is running.

Planned servers (from the master plan): reminders, calendar, notes, photos,
files, email, finance, github, home, cameras, media.

## Naming convention

Tools are named `<domain>.<verb>`, where the domain matches the server folder:

```
reminders.create      reminders.list      reminders.complete
calendar.list_events  calendar.create_event
photos.search         photos.find_person
home.turn_light_on    home.get_status
camera.who_is_at_door
```

The domain is singular-or-plural to match how it reads naturally, but stays
consistent within a server. The verb says what the tool does, not how it is
implemented.

## Conventions once servers land

- One capability per server; no cross-domain tools.
- Actions that are destructive or sensitive (unlocking a door, deleting photos,
  moving money) are gated by the permission layer — the LLM requests, the
  permission layer decides. The server should never assume a call is authorized
  because it arrived.
- Shell access is not an MCP tool.

The first server to build is `reminders/`, per [../docs/pilot.md](../docs/pilot.md).
