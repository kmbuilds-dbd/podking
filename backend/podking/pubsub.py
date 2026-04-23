"""In-memory pub/sub for SSE job progress events."""
from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict

# job_id -> list of queues listening for events
_subscribers: dict[uuid.UUID, list[asyncio.Queue[dict[str, object]]]] = defaultdict(list)


def subscribe(job_id: uuid.UUID) -> asyncio.Queue[dict[str, object]]:
    q: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    _subscribers[job_id].append(q)
    return q


def unsubscribe(job_id: uuid.UUID, q: asyncio.Queue[dict[str, object]]) -> None:
    try:
        _subscribers[job_id].remove(q)
    except ValueError:
        pass
    if not _subscribers[job_id]:
        _subscribers.pop(job_id, None)


def publish(job_id: uuid.UUID, event: dict[str, object]) -> None:
    for q in list(_subscribers.get(job_id, [])):
        q.put_nowait(event)
