import uuid

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ved_memory.config import settings
from ved_memory.server import parse_limit, parse_query, parse_user_id


def test_a_query_is_trimmed():
    assert parse_query("  home server ") == "home server"


def test_a_blank_query_is_rejected():
    with pytest.raises(ToolError, match="query"):
        parse_query("   ")


@pytest.mark.parametrize("limit", [0, -1, settings.search_max_limit + 1])
def test_a_limit_outside_the_range_is_rejected(limit):
    with pytest.raises(ToolError, match="limit"):
        parse_limit(limit)


@pytest.mark.parametrize("limit", [1, settings.search_max_limit])
def test_the_ends_of_the_range_are_accepted(limit):
    assert parse_limit(limit) == limit


def test_a_user_id_must_be_a_uuid():
    known = uuid.uuid4()

    assert parse_user_id(str(known)) == known
    with pytest.raises(ToolError, match="user_id must be a UUID"):
        parse_user_id("not-a-uuid")
