import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ved_people.server import parse_birthday, parse_notice_days
from ved_people.storage import Birthday


def test_full_date():
    assert parse_birthday("1965-10-25") == Birthday(month=10, day=25, year=1965)


def test_month_and_day_without_a_year():
    assert parse_birthday("10-25") == Birthday(month=10, day=25)
    assert parse_birthday("--10-25") == Birthday(month=10, day=25)


def test_leap_day_without_a_year_is_accepted():
    assert parse_birthday("02-29") == Birthday(month=2, day=29)


def test_leap_day_in_a_non_leap_year_is_rejected():
    with pytest.raises(ToolError, match="not a real date"):
        parse_birthday("1999-02-29")


def test_impossible_date_is_rejected():
    with pytest.raises(ToolError, match="not a real date"):
        parse_birthday("13-01")


def test_future_birth_year_is_rejected():
    with pytest.raises(ToolError, match="future"):
        parse_birthday("2999-01-01")


def test_prose_is_rejected_with_the_expected_format():
    with pytest.raises(ToolError, match="YYYY-MM-DD"):
        parse_birthday("25th October")


def test_notice_days_must_be_in_range():
    assert parse_notice_days(15) == 15
    with pytest.raises(ToolError, match="between 0 and"):
        parse_notice_days(-1)
    with pytest.raises(ToolError, match="between 0 and"):
        parse_notice_days(400)
