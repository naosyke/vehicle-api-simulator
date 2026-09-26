import asyncio


class WebSocketHub:
    """Fans out simulator events to connected WebSocket clients.

    publish() may be called from any thread (API endpoints run in a thread
    pool), so each subscriber's queue is fed through its own event loop.
    """

    def __init__(self, max_queue_size=100):
        self._max_queue_size = max_queue_size
        self._subscribers = {}

    def subscribe(self):
        queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers[queue] = asyncio.get_running_loop()
        return queue

    def unsubscribe(self, queue):
        self._subscribers.pop(queue, None)

    def publish(self, message):
        for queue, loop in list(self._subscribers.items()):
            try:
                loop.call_soon_threadsafe(self._put, queue, message)
            except RuntimeError:
                # The subscriber's event loop has already been closed.
                self.unsubscribe(queue)

    @staticmethod
    def _put(queue, message):
        # A slow client drops events instead of blocking the simulator.
        if not queue.full():
            queue.put_nowait(message)
