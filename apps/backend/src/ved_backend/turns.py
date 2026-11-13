import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable

from ved_backend.schemas import AgentEvent, AgentReply, StreamErrorEvent

logger = logging.getLogger(__name__)

TurnItem = AgentEvent | AgentReply | StreamErrorEvent
TurnBody = Callable[[], AsyncIterator[TurnItem]]


class TurnRegistry:
    def __init__(self) -> None:
        self._locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._answering_counts: dict[uuid.UUID, int] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def is_answering(self, conversation_id: uuid.UUID) -> bool:
        return self._answering_counts.get(conversation_id, 0) > 0

    def start(
        self, conversation_id: uuid.UUID, body: TurnBody
    ) -> asyncio.Queue[TurnItem | None]:
        items: asyncio.Queue[TurnItem | None] = asyncio.Queue()
        self._adjust_answering(conversation_id, 1)
        task = asyncio.create_task(self._run(conversation_id, body, items))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return items

    def _adjust_answering(self, conversation_id: uuid.UUID, delta: int) -> None:
        count = self._answering_counts.get(conversation_id, 0) + delta
        if count > 0:
            self._answering_counts[conversation_id] = count
        else:
            self._answering_counts.pop(conversation_id, None)

    async def _run(
        self,
        conversation_id: uuid.UUID,
        body: TurnBody,
        items: asyncio.Queue[TurnItem | None],
    ) -> None:
        try:
            async with self._locks.setdefault(conversation_id, asyncio.Lock()):
                async for item in body():
                    items.put_nowait(item)
        except Exception:
            logger.exception("Turn in conversation %s failed", conversation_id)
        finally:
            self._adjust_answering(conversation_id, -1)
            items.put_nowait(None)
