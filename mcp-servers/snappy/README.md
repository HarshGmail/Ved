# snappy — MCP server

Lets Ved find the user's photos in snappy: by what is in them, by person, by
album or by when they were taken. Read-only.

## Tools

| Tool | Arguments | Returns |
| --- | --- | --- |
| `search_photos` | `query`, `limit=12` | Photos matching the query, best first |
| `list_people` | — | Named people in the photos, up to 50 |
| `photos_of_person` | `name`, `limit=24` | Photos of one person, newest first |
| `list_albums` | — | Albums with their photo counts, up to 50 |
| `album_photos` | `album_name`, `limit=24` | Photos in one album, newest first |
| `recent_photos` | `days=7`, `limit=24` | Photos taken lately, newest first |
| `photo_details` | `photo_id` | When, where, camera and people for one photo |

Every photo carries a `link` to open it in snappy. Limits are capped at 50.

## Authentication

This server holds no key of its own. Each request must send the person's
snappy API key as `Authorization: Bearer <key>`; a request without one gets a
401 before any tool runs. The key is forwarded to snappy as `x-api-key`. Ved
stores each person's key encrypted on the Connections page.

## Settings

| Variable | Default |
| --- | --- |
| `SNAPPY_API_URL` | `https://photos.my-finances.site/api` |
| `SNAPPY_PUBLIC_URL` | `https://photos.my-finances.site` |
| `SNAPPY_REQUEST_TIMEOUT_SECONDS` | `15` |

## Running

```bash
uv sync
uv run ved-mcp-snappy       # listens on 0.0.0.0:8200, path /mcp
uv run pytest
uv run ruff check .
```

In Docker it is the `mcp-snappy` service in `infra/compose.yaml`, container
`ved-mcp-snappy`, with no published port. The backend reaches it at
`http://ved-mcp-snappy:8200/mcp`, the Snappy preset on the Connections page.
