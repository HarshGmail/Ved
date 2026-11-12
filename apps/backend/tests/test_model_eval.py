import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "model_eval.py"
spec = importlib.util.spec_from_file_location("model_eval", SCRIPT)
model_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model_eval)

REMINDER_CASE = model_eval.Case(
    prompt="remind me",
    expect_tool="create_reminder",
    expect_args={"kind": "birthday", "date": None},
)
NO_TOOL_CASE = model_eval.Case(prompt="hi", expect_tool=None, expect_args={})


@pytest.mark.parametrize(
    ("case", "call", "expected"),
    [
        (
            REMINDER_CASE,
            ("create_reminder", {"kind": "birthday", "date": "2026-03-14"}),
            (True, True),
        ),
        (
            REMINDER_CASE,
            ("create_reminder", {"kind": "reminder", "date": "2026-03-14"}),
            (True, False),
        ),
        (REMINDER_CASE, ("create_reminder", {"kind": "birthday"}), (True, False)),
        (REMINDER_CASE, ("web.search", {"query": "x"}), (False, False)),
        (REMINDER_CASE, (None, {}), (False, False)),
        (NO_TOOL_CASE, (None, {}), (True, True)),
        (NO_TOOL_CASE, ("web.search", {"query": "x"}), (False, False)),
    ],
)
def test_score_call_checks_the_tool_then_the_required_arguments(case, call, expected):
    assert model_eval.score_call(case, call) == expected


def test_parse_arguments_treats_malformed_json_as_no_arguments():
    assert model_eval.parse_arguments('{"query": "x"') == {}
    assert model_eval.parse_arguments('{"query": "x"}') == {"query": "x"}
