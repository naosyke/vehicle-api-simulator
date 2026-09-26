import asyncio
import threading

from app.websocket_hub import WebSocketHub


def test_publish_from_another_thread():
    async def scenario():
        hub = WebSocketHub()
        queue = hub.subscribe()

        thread = threading.Thread(target=hub.publish, args=({"type": "door_opened"},))
        thread.start()
        thread.join()

        return await asyncio.wait_for(queue.get(), 1.0)

    assert asyncio.run(scenario()) == {"type": "door_opened"}


def test_full_queue_drops_messages():
    async def scenario():
        hub = WebSocketHub(max_queue_size=2)
        queue = hub.subscribe()
        for i in range(5):
            hub.publish(i)
        await asyncio.sleep(0)
        return [queue.get_nowait() for _ in range(queue.qsize())]

    assert asyncio.run(scenario()) == [0, 1]


def test_unsubscribed_queue_gets_nothing():
    async def scenario():
        hub = WebSocketHub()
        queue = hub.subscribe()
        hub.unsubscribe(queue)
        hub.publish("event")
        await asyncio.sleep(0)
        return queue.empty()

    assert asyncio.run(scenario())
