import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ved_reminders.server import parse_due_at


def test_accepts_offset_aware_datetime():
    parsed = parse_due_at("2026-09-17T20:00:00+05:30")

    assert parsed.tzinfo is not None
    assert parsed.hour == 20


def test_rejects_naive_datetime():
    with pytest.raises(ToolError, match="UTC offset"):
        parse_due_at("2026-09-17T20:00:00")


def test_rejects_unparseable_value():
    with pytest.raises(ToolError, match="ISO 8601"):
        parse_due_at("tomorrow at 8")
