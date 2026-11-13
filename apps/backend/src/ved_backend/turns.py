import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable

from ved_backend.schemas import AgentEvent, AgentReply, StreamErrorEvent

logger = logging.getLogger(__name__)

TurnKey = tuple[uuid.UUID, uuid.UUID]
TurnItem = AgentEvent | AgentReply | StreamErrorEvent
TurnBody = Callable[[], AsyncIterator[TurnItem]]


class TurnRegistry:
    def __init__(self) -> None:
        self._locks: dict[TurnKey, asyncio.Lock] = {}
        self._answering_counts: dict[TurnKey, int] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def is_answering(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        return self._answering_counts.get((user_id, conversation_id), 0) > 0

    def start(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, body: TurnBody
    ) -> asyncio.Queue[TurnItem | None]:
        items: asyncio.Queue[TurnItem | None] = asyncio.Queue()
        key = (user_id, conversation_id)
        self._adjust_answering(key, 1)
        task = asyncio.create_task(self._run(key, body, items))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return items

    def _adjust_answering(self, key: TurnKey, delta: int) -> None:
        count = self._answering_counts.get(key, 0) + delta
        if count > 0:
            self._answering_counts[key] = count
        else:
            self._answering_counts.pop(key, None)

    async def _run(
        self,
        key: TurnKey,
        body: TurnBody,
        items: asyncio.Queue[TurnItem | None],
    ) -> None:
        try:
            async with self._locks.setdefault(key, asyncio.Lock()):
                async for item in body():
                    items.put_nowait(item)
        except Exception:
            logger.exception("Turn in conversation %s failed", key[1])
        finally:
            self._adjust_answering(key, -1)
            items.put_nowait(None)
