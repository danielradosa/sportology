import os
import asyncio
from typing import Set, Optional
from fastapi import WebSocket


def read_frontend_version(frontend_dist_path: str) -> Optional[str]:
    """Read frontend/dist/version.txt if present."""
    try:
        p = os.path.join(frontend_dist_path, "version.txt")
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except Exception:
        return None


class UpdateHub:
    def __init__(self) -> None:
        self.clients: Set[WebSocket] = set()
        self._last_version: Optional[str] = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        try:
            self.clients.remove(ws)
        except KeyError:
            pass

    async def send(self, ws: WebSocket, payload: dict) -> None:
        await ws.send_json(payload)

    async def broadcast(self, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def watch_frontend_version(self, frontend_dist_path: str, interval_s: float = 2.0) -> None:
        """Poll version.txt and broadcast when it changes."""
        self._last_version = read_frontend_version(frontend_dist_path)
        while True:
            await asyncio.sleep(interval_s)
            v = read_frontend_version(frontend_dist_path)
            if v and v != self._last_version:
                self._last_version = v
                await self.broadcast({"type": "deploy", "version": v})
