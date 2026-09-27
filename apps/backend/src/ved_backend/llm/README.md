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
| `stub` | `StubProvider` | No |
| `openai-compatible` | `OpenAICompatibleProvider` | Only for hosted endpoints |

## Why "openai-compatible" and not "ollama"

The provider targets the OpenAI chat-completions *shape*, not a vendor. Nearly
every local runtime and most hosted gateways speak it, so changing where the
model runs is a URL change with no new code:

| Runtime | `VED_LLM_BASE_URL` |
| --- | --- |
| Ollama | `http://localhost:11434/v1` |
| LM Studio | `http://localhost:1234/v1` |
| llama.cpp / vLLM | whatever it serves on |
| A GPU box on the LAN | `http://gpu.local:11434/v1` |
| OpenRouter, Together, Groq | their URL plus `VED_LLM_API_KEY` |

That last row is the Phase 8 path: when the GPU server exists, Ved points at it
by editing one variable. An `ollama.py` would have made every one of these a new
module.

Anthropic will still need its own provider — its wire format genuinely differs,
and pretending otherwise through a translation shim costs more than it saves.
That is one module, not one per runtime.

## Local models and tool calling

The model must be trained for tool use, or it will answer in prose and never
call anything. `ollama show <model>` must list `tools` under Capabilities.

Two settings that matter more than they look:

- **`VED_LLM_TEMPERATURE=0.0`.** Tool arguments are structured data, not prose.
  Sampling randomness here produces malformed JSON and invented field names.
- **Ollama's KV cache quantization.** `q8_0` is fine; `q4` measurably degrades
  tool-call accuracy. The `OLLAMA_KV_CACHE_TYPE` in the run command is not
  arbitrary.

Small models drop or malform tool calls more often than hosted ones. The agent
loop already absorbs this — a malformed argument blob parses to `{}` rather than
crashing, and the tool's own validation error goes back to the model — but a
weak model will use more rounds to get there.

## Failure is a 503, not a 500

`OpenAICompatibleProvider` raises `LLMRequestError` when the endpoint is
unreachable or answers with an error status, and `main.py` turns that into a
`503` naming the cause. A local model that is not running is an expected
operating state — the same category as Postgres being down — not a bug in Ved.

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
