import asyncio
import json
import os
import time

import pytest
from pywebpush import WebPushException
from sqlalchemy import select
from ved_db import PushSubscription

from ved_backend.push import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TTL_SECONDS,
    Notification,
    PushNotConfiguredError,
    PushService,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

KEYS = {"p256dh": "key-material", "auth": "auth-secret"}


class Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def build(session_factory, *, configured: bool = True) -> PushService:
    return PushService(
        session_factory,
        public_key="public" if configured else None,
        private_key="private" if configured else None,
        subject="mailto:ved@example.com",
    )


def test_payload_carries_what_the_worker_needs():
    payload = json.loads(
        Notification(
            title="Ved", body="call Mom — 8:00 PM", tag="reminder"
        ).as_payload()
    )

    assert payload == {
        "title": "Ved",
        "body": "call Mom — 8:00 PM",
        "tag": "reminder",
        "url": "/",
    }


async def test_subscribing_stores_the_endpoint(session_factory, user):
    service = build(session_factory)

    await service.subscribe(user.id, "https://push.example/abc", KEYS, "iPhone")

    assert await service.subscription_count(user.id) == 1


async def test_resubscribing_the_same_endpoint_updates_rather_than_duplicates(
    session_factory,
    user,
):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/abc", KEYS, "iPhone")

    await service.subscribe(
        user.id, "https://push.example/abc", {"p256dh": "new", "auth": "new"}, "iPad"
    )

    assert await service.subscription_count(user.id) == 1
    async with session_factory() as session:
        stored = await session.scalar(select(PushSubscription))
        assert stored.label == "iPad"
        assert stored.keys["p256dh"] == "new"


async def test_unsubscribing_removes_it(session_factory, user):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/abc", KEYS, None)

    assert await service.unsubscribe(user.id, "https://push.example/abc") is True
    assert await service.subscription_count(user.id) == 0


async def test_unsubscribing_something_unknown_is_not_an_error(session_factory, user):
    service = build(session_factory)

    assert await service.unsubscribe(user.id, "https://push.example/nope") is False


async def test_sending_without_keys_is_refused(session_factory, user):
    service = build(session_factory, configured=False)

    with pytest.raises(PushNotConfiguredError):
        await service.send(user.id, Notification(title="Ved", body="hi", tag="t"))


async def test_sending_with_no_devices_reports_nothing_sent(session_factory, user):
    service = build(session_factory)

    report = await service.send(user.id, Notification(title="Ved", body="hi", tag="t"))

    assert report.sent == 0
    assert report.reached_anyone is False


async def test_a_successful_send_is_counted(session_factory, user, monkeypatch):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/abc", KEYS, None)
    monkeypatch.setattr(service, "_send_blocking", lambda row, payload: None)

    report = await service.send(user.id, Notification(title="Ved", body="hi", tag="t"))

    assert report.sent == 1
    assert report.reached_anyone is True


async def test_an_expired_endpoint_is_dropped(session_factory, user, monkeypatch):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/gone", KEYS, None)

    def gone(row, payload):
        raise WebPushException("gone", response=Response(410))

    monkeypatch.setattr(service, "_send_blocking", gone)

    report = await service.send(user.id, Notification(title="Ved", body="hi", tag="t"))

    assert report.expired == 1
    assert await service.subscription_count(user.id) == 0


async def test_a_transient_failure_keeps_the_subscription(
    session_factory, user, monkeypatch
):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/flaky", KEYS, None)

    def unavailable(row, payload):
        raise WebPushException("boom", response=Response(503))

    monkeypatch.setattr(service, "_send_blocking", unavailable)

    report = await service.send(user.id, Notification(title="Ved", body="hi", tag="t"))

    assert report.sent == 0
    assert report.expired == 0
    assert await service.subscription_count(user.id) == 1


async def test_one_dead_device_does_not_stop_the_others(
    session_factory, user, monkeypatch
):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/good", KEYS, None)
    await service.subscribe(user.id, "https://push.example/gone", KEYS, None)

    def selective(row, payload):
        if row.endpoint.endswith("gone"):
            raise WebPushException("gone", response=Response(404))

    monkeypatch.setattr(service, "_send_blocking", selective)

    report = await service.send(user.id, Notification(title="Ved", body="hi", tag="t"))

    assert report.sent == 1
    assert report.expired == 1
    assert await service.subscription_count(user.id) == 1


async def test_delivery_stamps_last_used(session_factory, user, monkeypatch):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/abc", KEYS, None)
    monkeypatch.setattr(service, "_send_blocking", lambda row, payload: None)

    await service.send(user.id, Notification(title="Ved", body="hi", tag="t"))

    async with session_factory() as session:
        stored = await session.scalar(select(PushSubscription))
        assert stored.last_used_at is not None


async def test_a_hanging_endpoint_does_not_stall_forever(
    session_factory, user, monkeypatch
):
    service = PushService(
        session_factory,
        public_key="public",
        private_key="private",
        subject="mailto:ved@example.com",
        timeout_seconds=0.05,
    )
    await service.subscribe(user.id, "https://push.example/slow", KEYS, None)

    def hang(row, payload):
        time.sleep(2)

    monkeypatch.setattr(service, "_send_blocking", hang)

    report = await asyncio.wait_for(
        service.send(user.id, Notification(title="Ved", body="hi", tag="t")), timeout=5
    )

    assert report.sent == 0
    assert await service.subscription_count(user.id) == 1


async def test_sends_carry_a_timeout_and_a_ttl(session_factory, user, monkeypatch):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/abc", KEYS, None)
    captured: dict = {}

    def capture(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("ved_backend.push.webpush", capture)
    await service.send(user.id, Notification(title="Ved", body="hi", tag="t"))

    assert captured["timeout"] == DEFAULT_TIMEOUT_SECONDS
    assert captured["ttl"] == DEFAULT_TTL_SECONDS
    assert captured["ttl"] > 0


async def test_a_send_reaches_only_the_target_users_devices(
    session_factory, user, other_user, monkeypatch
):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/mine", KEYS, None)
    await service.subscribe(other_user.id, "https://push.example/theirs", KEYS, None)
    reached: list[str] = []
    monkeypatch.setattr(
        service, "_send_blocking", lambda row, payload: reached.append(row.endpoint)
    )

    report = await service.send(user.id, Notification(title="Ved", body="hi", tag="t"))

    assert reached == ["https://push.example/mine"]
    assert report.sent == 1


async def test_subscription_counts_are_per_user(session_factory, user, other_user):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/one", KEYS, None)
    await service.subscribe(user.id, "https://push.example/two", KEYS, None)
    await service.subscribe(other_user.id, "https://push.example/three", KEYS, None)

    assert await service.subscription_count(user.id) == 2
    assert await service.subscription_count(other_user.id) == 1


async def test_unsubscribing_cannot_remove_another_users_device(
    session_factory, user, other_user
):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/mine", KEYS, None)

    assert (
        await service.unsubscribe(other_user.id, "https://push.example/mine") is False
    )
    assert await service.subscription_count(user.id) == 1


async def test_a_device_signing_in_as_someone_else_changes_owner(
    session_factory, user, other_user
):
    service = build(session_factory)
    await service.subscribe(user.id, "https://push.example/shared", KEYS, None)

    await service.subscribe(other_user.id, "https://push.example/shared", KEYS, None)

    assert await service.subscription_count(user.id) == 0
    assert await service.subscription_count(other_user.id) == 1
