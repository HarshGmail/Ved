# MCP servers

Each subfolder is **one MCP server covering one capability**. Keeping them
separate means a capability can be developed, restarted, secured, or removed
without touching the others, and the backend can connect to whichever subset is
running.

| Server | Status |
| --- | --- |
| [reminders/](reminders/) | Working — `create`, `list`, `reschedule`, `complete` |
| [people/](people/) | Working — `remember`, `list`, `forget`; birthdays remind themselves |
| [memory/](memory/) | Working — `search` past conversations by meaning |
| [web/](web/) | Working — `search` (SearXNG) and `fetch`; returns untrusted content |

Planned (from the master plan): calendar, notes, photos, files, email, finance,
github, home, cameras, media.

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

## Conventions

- One capability per server; no cross-domain tools.
- Actions that are destructive or sensitive (unlocking a door, deleting photos,
  moving money) are gated by the permission layer — the LLM requests, the
  permission layer decides. The server should never assume a call is authorized
  because it arrived.
- Shell access is not an MCP tool.
- Return Pydantic models, not `dict`, so tools declare an output schema and the
  model receives structured content.
- Raise `ToolError` for bad arguments. The SDK passes its message to the caller
  but redacts every other exception, so a model can only self-correct from a
  `ToolError`.
- Require explicit UTC offsets on datetimes rather than guessing a timezone.
- Table schemas are owned by the backend's Alembic migrations; servers read and
  write rows but do not create tables.
