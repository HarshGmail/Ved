# people — MCP server

Ved's first piece of structured user memory: the people in your life and their
birthdays. Backed by the `people` table in the shared database.

## Tools

| Tool | Arguments | Returns |
| --- | --- | --- |
| `people.remember` | `name`, `relation?`, `birthday?`, `birthday_notice_days?` | The saved person |
| `people.list` | — | Everyone, soonest birthday first |
| `people.forget` | `name` | Who was removed |

`people.remember` creates someone or updates them, and changes only the fields
it is given. Names match regardless of case, so "mom" updates "Mom".

## Birthdays become reminders on their own

This server only stores facts. It never creates reminders. The backend's
scheduler reads `people` on every tick and writes ordinary `reminders` rows for
each upcoming birthday: one on the day, and one `birthday_notice_days` earlier
when that is above zero. Both arrive at `VED_BIRTHDAY_REMINDER_TIME` (09:00) and
go through the same push delivery as any other reminder. After a birthday
passes, the next tick plans next year's, so nothing has to be set up again.

So the tool descriptions tell the model **not** to also call
`reminders.create` for a birthday, or the user would be reminded twice.

## Running

```bash
uv sync
uv run ved-mcp-people             # stdio transport
uv run pytest                     # DB tests skip unless VED_TEST_DATABASE_URL is set
uv run ruff check .
```

The backend starts this server itself. It needs `VED_DATABASE_URL`, and
`VED_TIMEZONE` so that "days until birthday" counts from your today, not UTC's.

## Design notes

**A birthday is month and day, with an optional year.** People often know a
friend's birthday but not their age. `MM-DD` is accepted, and the record shows
`--MM-DD` (the ISO form for "no year"). The age only appears when a year is
known.

**Repeating a date without a year keeps the year already stored.** Local models
tend to resend a birthday as `10-25` when only changing the notice. Treating
that as "year unknown" would silently erase it. A *different* date with no year
does drop the old year, since the old year no longer applies.

**Feb 29 birthdays fall on Feb 28 in other years.** That rule lives in
`ved_db.birthday_in`, so the server and the scheduler cannot disagree on it.

**Changing a birthday or its notice deletes the reminders not yet sent.** The
scheduler replans them on its next tick from the new values. Reminders already
sent stay, so the history is kept and nothing fires twice. Forgetting a person
cascades to all their reminders.

**Each planned reminder is unique per (person, birthday, lead days).** The
scheduler inserts with `ON CONFLICT DO NOTHING`, so planning every 30 seconds is
cheap and can never create duplicates, even with two schedulers running.
