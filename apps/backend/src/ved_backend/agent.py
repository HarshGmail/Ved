import logging
from collections.abc import Sequence

from ved_backend.llm.base import (
    LLMProvider,
    Message,
    ToolCall,
    ToolOutcome,
    ToolResultMessage,
    UserMessage,
)
from ved_backend.schemas import AgentReply, ToolInvocation
from ved_backend.tools.toolbox import MCPToolbox, ToolNotAvailableError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Ved, a personal assistant.

Use the available tools to act on the user's behalf rather than describing what
you would do. Times must be sent as ISO 8601 strings that include a UTC offset.
When a tool reports an error, read the message and correct the arguments."""

TOOL_LIMIT_MESSAGE = "I stopped after too many tool calls without reaching an answer."


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        toolbox: MCPToolbox,
        *,
        max_tool_rounds: int,
    ) -> None:
        self._provider = provider
        self._toolbox = toolbox
        self._max_tool_rounds = max_tool_rounds

    async def run(self, prompt: str) -> AgentReply:
        messages: list[Message] = [UserMessage(text=prompt)]
        invocations: list[ToolInvocation] = []

        for _ in range(self._max_tool_rounds):
            reply = await self._provider.complete(
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=self._toolbox.tools,
            )
            messages.append(reply)

            if not reply.tool_calls:
                return AgentReply(
                    text=reply.text,
                    model=self._provider.model,
                    tool_calls=invocations,
                )

            outcomes = await self._execute(reply.tool_calls, invocations)
            messages.append(ToolResultMessage(outcomes=outcomes))

        logger.warning("Agent hit the tool round limit for prompt %r", prompt)
        return AgentReply(
            text=TOOL_LIMIT_MESSAGE,
            model=self._provider.model,
            tool_calls=invocations,
        )

    async def _execute(
        self, calls: Sequence[ToolCall], invocations: list[ToolInvocation]
    ) -> list[ToolOutcome]:
        outcomes: list[ToolOutcome] = []
        for call in calls:
            content, is_error = await self._invoke(call)
            outcomes.append(
                ToolOutcome(call_id=call.id, content=content, is_error=is_error)
            )
            invocations.append(
                ToolInvocation(
                    name=call.name, arguments=call.arguments, failed=is_error
                )
            )
        return outcomes

    async def _invoke(self, call: ToolCall) -> tuple[str, bool]:
        try:
            return await self._toolbox.call(call.name, call.arguments)
        except ToolNotAvailableError as error:
            return str(error), True
        except Exception:
            logger.exception("Tool %s raised", call.name)
            return f"{call.name} failed unexpectedly", True
