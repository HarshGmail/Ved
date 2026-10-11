import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ved_web.config import settings
from ved_web.server import QUERY_MAX_CHARACTERS, parse_limit, parse_query


def test_query_whitespace_is_collapsed():
    assert parse_query("  today's   top\nnews ") == "today's top news"


def test_an_empty_query_is_rejected():
    with pytest.raises(ToolError, match="query must not be empty"):
        parse_query("   ")


def test_an_overlong_query_is_rejected():
    with pytest.raises(ToolError, match=f"at most {QUERY_MAX_CHARACTERS}"):
        parse_query("a" * (QUERY_MAX_CHARACTERS + 1))


def test_a_large_limit_is_capped_rather_than_refused():
    assert parse_limit(500) == settings.search_max_limit


def test_a_limit_below_one_is_rejected():
    with pytest.raises(ToolError, match="limit must be at least 1, got 0"):
        parse_limit(0)
