import asyncio

from app.shared.application.ports import RealtimeEvent
from app.shared.infrastructure.realtime import QUEUE_SIZE, InMemoryRealtimeBroker


async def test_subscribers_only_receive_their_topic():
    broker = InMemoryRealtimeBroker()
    async with broker.subscribe("venue:1") as one, broker.subscribe("venue:2") as two:
        await broker.publish("venue:1", RealtimeEvent("queue_changed"))

        assert (await asyncio.wait_for(one.get(), 1)).kind == "queue_changed"
        assert two.empty()


async def test_every_subscriber_of_a_topic_gets_the_event():
    broker = InMemoryRealtimeBroker()
    async with broker.subscribe("venue:1") as a, broker.subscribe("venue:1") as b:
        await broker.publish("venue:1", RealtimeEvent("joined", {"ticket": 4}))

        assert (await a.get()).data == {"ticket": 4}
        assert (await b.get()).data == {"ticket": 4}


async def test_unsubscribing_cleans_up():
    broker = InMemoryRealtimeBroker()
    async with broker.subscribe("venue:1"):
        assert broker.subscriber_count("venue:1") == 1
    assert broker.subscriber_count("venue:1") == 0
    await broker.publish("venue:1", RealtimeEvent("nobody-listens"))  # no falla


async def test_a_slow_consumer_loses_the_oldest_events_but_keeps_the_latest():
    broker = InMemoryRealtimeBroker()
    async with broker.subscribe("venue:1") as slow:
        for i in range(QUEUE_SIZE + 5):
            await broker.publish("venue:1", RealtimeEvent("tick", {"n": i}))

        received = [slow.get_nowait().data["n"] for _ in range(slow.qsize())]
        assert len(received) == QUEUE_SIZE and received[-1] == QUEUE_SIZE + 4
