"""Per-topic WebSocket broadcast hub.

Sessions subscribe to topics like `run:<run_id>` or `pipeline:<pipeline_id>`
and receive messages published to those topics. In-memory only — single-process.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class TopicHub:
    def __init__(self) -> None:
        self._subs: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str, ws: WebSocket) -> None:
        async with self._lock:
            self._subs[topic].add(ws)

    async def unsubscribe(self, topic: str, ws: WebSocket) -> None:
        async with self._lock:
            self._subs[topic].discard(ws)
            if not self._subs[topic]:
                self._subs.pop(topic, None)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        targets: list[WebSocket]
        async with self._lock:
            targets = list(self._subs.get(topic, set()))
        for ws in targets:
            try:
                await ws.send_json({"topic": topic, "payload": payload})
            except Exception:
                # client likely disconnected; clean up.
                await self.unsubscribe(topic, ws)


hub = TopicHub()
