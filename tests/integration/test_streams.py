"""Los generadores SSE se prueban directamente: el transporte ASGI de httpx no entrega streams infinitos."""

import asyncio
import json
from contextlib import aclosing

from app.shared.infrastructure.tokens import SecretsTokenGenerator
from app.waitlist.dependencies import WaitlistServicesFactory
from app.waitlist.presentation.streams import diner_stream, host_stream
from tests.integration.test_api_diner import API, DINER, SLUG, host_headers, join

HEARTBEAT = 0.05


def services(db) -> WaitlistServicesFactory:
    return WaitlistServicesFactory(db.factory, db.clock, SecretsTokenGenerator(), db.broker)


async def next_message(stream) -> tuple[str, dict | None]:
    raw = await asyncio.wait_for(anext(stream), timeout=3)
    if raw.startswith(":"):
        return "heartbeat", None
    event, data = raw.strip().split("\n", 1)
    return event.removeprefix("event: "), json.loads(data.removeprefix("data: "))


async def test_diner_stream_sends_the_state_first_and_again_when_the_queue_changes(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)
    await join(client, name="Primero", phone="987000001")
    mine = (await join(client, name="Yo", phone="987000002")).json()["token"]

    async with aclosing(diner_stream(services(db), db.broker, SLUG, mine, HEARTBEAT)) as stream:
        event, state = await next_message(stream)
        assert (event, state["position"], state["status"]) == ("state", 2, "waiting")

        first_id = (await client.get(f"{API}/{SLUG}/host/queue", headers=headers)).json()["rows"][0]["id"]
        await client.post(f"{API}/{SLUG}/host/entries/{first_id}/call", headers=headers)

        event, state = await next_message(stream)
        assert (event, state["position"]) == ("state", 1)  # el de adelante fue llamado: avanzo
        assert set(state) == {
            "token", "ticket", "name", "party_size", "phone_display", "status", "position", "eta",
            "hold_ends_at", "on_the_way", "venue", "server_time",
        }  # fmt: skip


async def test_diner_stream_sends_heartbeats_and_refreshes_the_state_periodically(db, client):
    await db.create_venue()
    token = (await join(client)).json()["token"]

    async with aclosing(diner_stream(services(db), db.broker, SLUG, token, HEARTBEAT)) as stream:
        assert (await next_message(stream))[0] == "state"
        assert (await next_message(stream))[0] == "heartbeat"
        event, state = await next_message(stream)  # cada 2 latidos reenvía el estado completo
        assert (event, state["status"]) == ("state", "waiting")


async def test_diner_stream_shows_the_call_to_the_diner(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)
    token = (await join(client)).json()["token"]
    entry_id = (await client.get(f"{API}/{SLUG}/host/queue", headers=headers)).json()["rows"][0]["id"]

    async with aclosing(diner_stream(services(db), db.broker, SLUG, token, HEARTBEAT)) as stream:
        await next_message(stream)
        await client.post(f"{API}/{SLUG}/host/entries/{entry_id}/call", headers=headers)

        _, state = await next_message(stream)
        assert state["status"] == "called" and state["hold_ends_at"] is not None and state["position"] is None


async def test_the_stream_unsubscribes_when_the_client_disconnects(db, client):
    venue = await db.create_venue()
    token = (await join(client)).json()["token"]

    stream = diner_stream(services(db), db.broker, SLUG, token, HEARTBEAT)
    await next_message(stream)
    assert db.broker.subscriber_count(f"venue:{venue.id}") == 1

    await stream.aclose()

    assert db.broker.subscriber_count(f"venue:{venue.id}") == 0


async def test_host_stream_sends_the_queue_then_a_feed_message_and_the_new_queue_on_each_change(db, client):
    venue = await db.create_venue()

    async with aclosing(host_stream(services(db), db.broker, venue.id, HEARTBEAT)) as stream:
        event, queue = await next_message(stream)
        assert (event, queue["rows"]) == ("queue", [])

        await join(client, name="Carla", phone="987654321", party_size=3)

        event, feed = await next_message(stream)
        assert event == "feed"
        assert (feed["kind"], feed["ticket"], feed["name"], feed["party_size"]) == ("joined", 1, "Carla", 3)
        assert feed["phone_e164"] == "+51987654321" and feed["phone_display"] == "+51 987 654 321"
        event, queue = await next_message(stream)
        assert (event, len(queue["rows"]), queue["waiting"]) == ("queue", 1, 1)


async def test_host_stream_reports_what_the_diner_did(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)
    token = (await join(client)).json()["token"]
    entry_id = (await client.get(f"{API}/{SLUG}/host/queue", headers=headers)).json()["rows"][0]["id"]
    await client.post(f"{API}/{SLUG}/host/entries/{entry_id}/call", headers=headers)

    async with aclosing(host_stream(services(db), db.broker, venue.id, HEARTBEAT)) as stream:
        await next_message(stream)
        await client.post(f"{DINER}/entries/{token}/on-the-way")
        _, feed = await next_message(stream)
        _, queue = await next_message(stream)
        assert feed["kind"] == "on_the_way" and queue["rows"][0]["on_the_way"] is True

        await client.post(f"{DINER}/entries/{token}/cancel")
        _, feed = await next_message(stream)
        _, queue = await next_message(stream)
        assert feed["kind"] == "cancelled" and queue["rows"] == []


async def test_host_stream_reports_pause_and_schedule_changes(db, client):
    venue = await db.create_venue()
    headers = await host_headers(db, client, venue)

    async with aclosing(host_stream(services(db), db.broker, venue.id, HEARTBEAT)) as stream:
        await next_message(stream)
        await client.post(f"{API}/{SLUG}/host/pause", headers=headers)

        _, feed = await next_message(stream)
        _, queue = await next_message(stream)
        assert feed["kind"] == "paused" and queue["venue"]["list_status"]["kind"] == "paused"


async def test_host_stream_does_not_receive_events_from_another_venue(db, client):
    terraza = await db.create_venue()
    await db.create_venue(slug="cuatro-vientos", name="Cuatro Vientos")

    async with aclosing(host_stream(services(db), db.broker, terraza.id, HEARTBEAT)) as stream:
        await next_message(stream)
        await join(client, slug="cuatro-vientos")

        event, _ = await next_message(stream)
        assert event == "heartbeat"  # nada de otro local: solo llegó el latido


async def test_heartbeats_keep_the_host_stream_alive_and_refresh_it(db):
    venue = await db.create_venue()

    async with aclosing(host_stream(services(db), db.broker, venue.id, HEARTBEAT)) as stream:
        assert (await next_message(stream))[0] == "queue"
        assert (await next_message(stream))[0] == "heartbeat"
        assert (await next_message(stream))[0] == "queue"
