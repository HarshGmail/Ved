# LLM providers

Everything the agent needs from a model lives behind `LLMProvider` in
`base.py`. Nothing outside this package imports a vendor SDK, for the same
reason nothing outside `src/connector/` in the web client talks to the backend:
the master plan's fourth principle is *keep the LLM replaceable*, and Phase 8
replaces it with a local model on a GPU box.

## The contract

`complete(system, messages, tools)` returns an `AssistantMessage` that either
carries `text` or one or more `tool_calls` — never a half-parsed string the
caller has to interpret. Tool schemas arrive as `ToolSpec`, already translated
from MCP, so a provider only has to map them into its own wire format.

The message types are deliberately provider-neutral. Anthropic, OpenAI and
Ollama all disagree about how tool calls and tool results are represented; that
disagreement belongs inside each implementation, not in `agent.py`.

## Providers

| `VED_LLM_PROVIDER` | Class | Needs credentials |
| --- | --- | --- |
| `stub` (default) | `StubProvider` | No |

## Why a stub exists

`StubProvider` is a deterministic rule-based fake: it matches keywords, resolves
"at 8 PM" against `VED_TIMEZONE`, and emits a real tool call. It is not trying
to be a language model.

It earns its place twice. It proved the MCP loop end to end before any API key
existed, and it stays useful afterwards as the test double that lets the agent's
behaviour — retries, tool-error handling, the round limit — be tested in CI with
no network, no credentials, and no flakiness. Those tests are in
`tests/test_agent.py` and would be impossible to write against a real model.

Its limits are the point: it understands `at <hour>[:<minute>] [am|pm]` and
little else, so anything beyond the reminders vocabulary falls through to a
canned reply.

## Adding a real provider

1. Implement the protocol in a new module here.
2. Register it in `build_provider`.
3. Read the key from settings — never construct a client at import time, or the
   app cannot start without credentials.

The agent loop does not change. That is the whole design.
