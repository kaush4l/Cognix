import asyncio
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class LogEvent:
    timestamp: float = 0.0
    agent: str = ''
    event_type: str = ''      # tool_call | tool_result | answer
    tool_name: str = ''
    input: str = ''
    output: str = ''
    status: str = ''           # running | success | error
    duration_ms: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp,
            'agent': self.agent,
            'event_type': self.event_type,
            'tool_name': self.tool_name,
            'input': self.input,
            'output': self.output,
            'status': self.status,
            'duration_ms': self.duration_ms,
        }


class EventBus:
    def __init__(self, maxlen: int = 500):
        self._history: deque[LogEvent] = deque(maxlen=maxlen)
        self._subscribers: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def emit(self, event: LogEvent) -> None:
        self._history.append(event)
        loop = self._loop
        stale = []
        for q in self._subscribers:
            try:
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(q.put_nowait, event)
                else:
                    q.put_nowait(event)
            except Exception:
                stale.append(q)
        for q in stale:
            self._subscribers.remove(q)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def recent(self, n: int = 50) -> list[LogEvent]:
        items = list(self._history)
        return items[-n:] if len(items) > n else items


event_bus = EventBus()
