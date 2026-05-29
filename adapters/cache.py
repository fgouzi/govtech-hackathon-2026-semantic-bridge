import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

from core.logging import get_logger

log = get_logger(__name__)
_DEFAULT_TTL = 3600


class SQLiteCache:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        await self._db.commit()

    async def get(self, key: str) -> Any | None:
        if self._db is None:
            return None
        try:
            async with self._db.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                value_str, expires_at = row
                if time.time() > expires_at:
                    await self.delete(key)
                    return None
                return json.loads(value_str)
        except Exception as exc:
            log.warning("cache_get_error", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int = _DEFAULT_TTL) -> None:
        if self._db is None:
            return
        try:
            expires_at = time.time() + ttl_seconds
            await self._db.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), expires_at),
            )
            await self._db.commit()
        except Exception as exc:
            log.warning("cache_set_error", key=key, error=str(exc))

    async def delete(self, key: str) -> None:
        if self._db is None:
            return
        await self._db.execute("DELETE FROM cache WHERE key = ?", (key,))
        await self._db.commit()

    async def clear(self) -> None:
        if self._db is None:
            return
        await self._db.execute("DELETE FROM cache")
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
