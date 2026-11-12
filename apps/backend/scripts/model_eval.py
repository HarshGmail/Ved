import argparse
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx2

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_CASES = Path(__file__).with_name("model_eval_cases.json")
CHAT_COMPLETIONS_PATH = "/chat/completions"
REQUEST_TIMEOUT_SECONDS = 180.0
TEMPERATURE = 0
SSE_DATA_PREFIX = "data:"
SSE_DONE_SENTINEL = "[DONE]"
FIRST_TOKEN_FIELDS = ("content", "reasoning", "reasoning_content", "tool_calls")
P90 = 0.9


@dataclass(frozen=True)
class Case:
    prompt: str
    expect_tool: str | None
    expect_args: dict[str, Any]


@dataclass
class Outcome:
    prompt: str
    expected_tool: str | None
    actual_tool: str | None
    arguments: dict[str, Any]
    tool_correct: bool
    args_correct: bool
    seconds: float
    first_token_seconds: float | None
    error: str | None


def arguments_satisfy(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(
        name in actual and (value is None or actual[name] == value)
        for name, value in expected.items()
    )


def score_call(
    case: Case, call: tuple[str | None, dict[str, Any]]
) -> tuple[bool, bool]:
    actual_tool, actual_arguments = call
    tool_correct = actual_tool == case.expect_tool
    args_correct = tool_correct and arguments_satisfy(
        case.expect_args, actual_arguments
    )
    return tool_correct, args_correct


def parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_system_prompt(today: date) -> str:
    return (
        "You are Ved, a personal assistant. "
        f"Today is {today:%A, %Y-%m-%d}. "
        "When the user asks you to do something or look something up, call the "
        "matching tool. Otherwise answer directly without a tool."
    )


def request_body(model: str, system: str, prompt: str, tools: list[dict]) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "tools": tools,
        "temperature": TEMPERATURE,
        "stream": True,
    }


def read_stream(client: httpx2.Client, url: str, body: dict, started: float):
    first_token_seconds = None
    fragments: dict[int, dict[str, Any]] = {}
    with client.stream("POST", url, json=body) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith(SSE_DATA_PREFIX):
                continue
            data = line[len(SSE_DATA_PREFIX) :].strip()
            if data == SSE_DONE_SENTINEL:
                break
            choices = json.loads(data).get("choices") or [{}]
            delta = choices[0].get("delta") or {}
            if first_token_seconds is None and any(
                delta.get(field) for field in FIRST_TOKEN_FIELDS
            ):
                first_token_seconds = time.perf_counter() - started
            for call in delta.get("tool_calls") or []:
                accumulate_tool_call(fragments, call)
    return first_token_seconds, first_call(fragments)


def accumulate_tool_call(fragments: dict[int, dict[str, Any]], call: dict) -> None:
    entry = fragments.setdefault(call.get("index", 0), {"name": None, "arguments": ""})
    function = call.get("function") or {}
    if function.get("name"):
        entry["name"] = function["name"]
    arguments = function.get("arguments")
    if isinstance(arguments, dict):
        entry["arguments"] = arguments
    elif arguments:
        entry["arguments"] = f"{entry['arguments']}{arguments}"


def first_call(
    fragments: dict[int, dict[str, Any]],
) -> tuple[str | None, dict[str, Any]]:
    if not fragments:
        return None, {}
    entry = fragments[min(fragments)]
    return entry["name"], parse_arguments(entry["arguments"])


def run_case(
    client: httpx2.Client,
    url: str,
    model: str,
    system: str,
    tools: list[dict],
    case: Case,
) -> Outcome:
    started = time.perf_counter()
    body = request_body(model, system, case.prompt, tools)
    try:
        first_token_seconds, call = read_stream(client, url, body, started)
        error = None
    except (httpx2.HTTPError, json.JSONDecodeError) as failure:
        first_token_seconds, call, error = None, (None, {}), str(failure)
    seconds = time.perf_counter() - started
    tool_correct, args_correct = score_call(case, call)
    return Outcome(
        prompt=case.prompt,
        expected_tool=case.expect_tool,
        actual_tool=call[0],
        arguments=call[1],
        tool_correct=tool_correct,
        args_correct=args_correct,
        seconds=round(seconds, 3),
        first_token_seconds=None
        if first_token_seconds is None
        else round(first_token_seconds, 3),
        error=error,
    )


def evaluate_model(
    base_url: str,
    model: str,
    cases: list[Case],
    tools: list[dict],
    system: str,
    threads: int,
) -> list[Outcome]:
    url = f"{base_url.rstrip('/')}{CHAT_COMPLETIONS_PATH}"
    with (
        httpx2.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client,
        ThreadPoolExecutor(max_workers=threads) as pool,
    ):
        futures = [
            pool.submit(run_case, client, url, model, system, tools, case)
            for case in cases
        ]
        return [future.result() for future in futures]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def percent(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def summarise(outcomes: list[Outcome]) -> dict[str, Any]:
    seconds = [outcome.seconds for outcome in outcomes]
    first_tokens = [
        outcome.first_token_seconds
        for outcome in outcomes
        if outcome.first_token_seconds is not None
    ]
    return {
        "cases": len(outcomes),
        "tool_accuracy": percent(
            sum(outcome.tool_correct for outcome in outcomes), len(outcomes)
        ),
        "argument_accuracy": percent(
            sum(outcome.args_correct for outcome in outcomes), len(outcomes)
        ),
        "median_seconds": round(statistics.median(seconds), 2),
        "p90_seconds": round(percentile(seconds, P90), 2),
        "median_first_token_seconds": round(statistics.median(first_tokens), 2)
        if first_tokens
        else None,
    }


def print_summary(model: str, summary: dict[str, Any]) -> None:
    rows = [
        ("tool accuracy", f"{summary['tool_accuracy']}%"),
        ("argument accuracy", f"{summary['argument_accuracy']}%"),
        ("median seconds", f"{summary['median_seconds']}"),
        ("p90 seconds", f"{summary['p90_seconds']}"),
        ("median first token", _format_seconds(summary["median_first_token_seconds"])),
    ]
    print(f"\n{model} ({summary['cases']} cases)")
    for label, value in rows:
        print(f"  {label:<20} {value:>10}")


def _format_seconds(value: float | None) -> str:
    return "n/a" if value is None else f"{value}"


def load_cases(path: Path) -> tuple[list[dict], list[Case]]:
    document = json.loads(path.read_text())
    cases = [
        Case(
            prompt=entry["prompt"],
            expect_tool=entry["expect_tool"],
            expect_args=entry.get("expect_args", {}),
        )
        for entry in document["cases"]
    ]
    return document["tools"], cases


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score local models on Ved's tool calls."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tools, cases = load_cases(args.cases)
    system = build_system_prompt(date.today())
    report: dict[str, Any] = {
        "base_url": args.base_url,
        "generated_on": date.today().isoformat(),
        "models": [],
    }
    for model in args.model:
        outcomes = evaluate_model(
            args.base_url, model, cases, tools, system, args.threads
        )
        summary = summarise(outcomes)
        print_summary(model, summary)
        report["models"].append(
            {
                "model": model,
                "summary": summary,
                "cases": [asdict(outcome) for outcome in outcomes],
            }
        )
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
