import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import PushSubscription

logger = logging.getLogger(__name__)

GONE_STATUSES = frozenset({404, 410})

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_TTL_SECONDS = 86400
DEADLINE_MULTIPLIER = 3


class PushNotConfiguredError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Push is not configured. Generate VAPID keys and set "
            "VED_VAPID_PUBLIC_KEY, VED_VAPID_PRIVATE_KEY and VED_VAPID_SUBJECT."
        )


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    tag: str
    url: str = "/"

    def as_payload(self) -> str:
        return json.dumps(
            {"title": self.title, "body": self.body, "tag": self.tag, "url": self.url}
        )


@dataclass(frozen=True)
class DeliveryReport:
    sent: int
    expired: int

    @property
    def reached_anyone(self) -> bool:
        return self.sent > 0


class PushService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        public_key: str | None,
        private_key: str | None,
        subject: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._public_key = public_key
        self._private_key = private_key
        self._subject = subject
        self._timeout_seconds = timeout_seconds
        self._ttl_seconds = ttl_seconds
        self._deadline_seconds = timeout_seconds * DEADLINE_MULTIPLIER

    @property
    def configured(self) -> bool:
        return bool(self._public_key and self._private_key)

    @property
    def public_key(self) -> str | None:
        return self._public_key

    async def subscribe(
        self, endpoint: str, keys: dict[str, Any], label: str | None
    ) -> uuid.UUID:
        async with self._session_factory() as session:
            statement = (
                insert(PushSubscription)
                .values(endpoint=endpoint, keys=keys, label=label)
                .on_conflict_do_update(
                    index_elements=[PushSubscription.endpoint],
                    set_={"keys": keys, "label": label},
                )
                .returning(PushSubscription.id)
            )
            subscription_id = await session.scalar(statement)
            await session.commit()
            return subscription_id

    async def unsubscribe(self, endpoint: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                delete(PushSubscription).where(PushSubscription.endpoint == endpoint)
            )
            await session.commit()
            return result.rowcount > 0

    async def subscription_count(self) -> int:
        async with self._session_factory() as session:
            return await session.scalar(
                select(func.count()).select_from(PushSubscription)
            )

    async def send(self, notification: Notification) -> DeliveryReport:
        if not self.configured:
            raise PushNotConfiguredError()

        async with self._session_factory() as session:
            subscriptions = list(await session.scalars(select(PushSubscription)))

        if not subscriptions:
            return DeliveryReport(sent=0, expired=0)

        payload = notification.as_payload()
        results = await asyncio.gather(
            *(self._deliver(row, payload) for row in subscriptions)
        )

        outcomes = list(zip(subscriptions, results, strict=True))
        expired = [row.endpoint for row, ok in outcomes if ok is None]
        delivered = [row.id for row, ok in outcomes if ok]
        await self._reconcile(delivered, expired)

        return DeliveryReport(sent=len(delivered), expired=len(expired))

    async def _deliver(self, row: PushSubscription, payload: str) -> bool | None:
        try:
            async with asyncio.timeout(self._deadline_seconds):
                await asyncio.to_thread(self._send_blocking, row, payload)
        except TimeoutError:
            logger.warning("Push to %s timed out", row.id)
            return False
        except WebPushException as error:
            status = getattr(error.response, "status_code", None)
            if status in GONE_STATUSES:
                logger.info("Push endpoint gone, dropping subscription %s", row.id)
                return None
            logger.warning("Push to %s failed: %s", row.id, error)
            return False
        except Exception:
            logger.exception("Push to %s raised", row.id)
            return False
        return True

    def _send_blocking(self, row: PushSubscription, payload: str) -> None:
        webpush(
            subscription_info={"endpoint": row.endpoint, "keys": row.keys},
            data=payload,
            vapid_private_key=self._private_key,
            vapid_claims={"sub": self._subject},
            ttl=self._ttl_seconds,
            timeout=self._timeout_seconds,
        )

    async def _reconcile(self, delivered: list[uuid.UUID], expired: list[str]) -> None:
        if not delivered and not expired:
            return
        async with self._session_factory() as session:
            if expired:
                await session.execute(
                    delete(PushSubscription).where(
                        PushSubscription.endpoint.in_(expired)
                    )
                )
            if delivered:
                await session.execute(
                    update(PushSubscription)
                    .where(PushSubscription.id.in_(delivered))
                    .values(last_used_at=func.now())
                )
            await session.commit()
