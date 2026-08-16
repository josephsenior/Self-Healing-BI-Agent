"""Application-scoped Redis runtime with an in-memory development fallback."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger("agent_state")


class AgentStateRuntime:
    """Own the Redis pool/checkpointer lifecycle; never store run state on this object."""

    def __init__(
        self,
        redis_url: str,
        *,
        required: bool = False,
        checkpoint_ttl_minutes: int = 1440,
    ) -> None:
        self.redis_url = redis_url
        self.required = required
        self.checkpoint_ttl_minutes = checkpoint_ttl_minutes
        self.client: Any | None = None
        self.checkpointer: Any = InMemorySaver()
        self.backend = "memory"
        self.checkpointer_implementation = "memory"
        self.last_error: str | None = None
        self._local_locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        """Connect once per backend process and initialize Redis indexes."""
        if not self.redis_url:
            if self.required:
                raise RuntimeError("REDIS_URL is required")
            return

        try:
            from redis.asyncio import Redis
            from langgraph.checkpoint.redis.aio import AsyncRedisSaver
            from .basic_redis_checkpointer import AsyncBasicRedisSaver

            client = Redis.from_url(
                self.redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
            )
            self.client = client
            await client.ping()
            try:
                saver = AsyncRedisSaver(
                    redis_client=client,
                    ttl={
                        "default_ttl": self.checkpoint_ttl_minutes,
                        "refresh_on_read": True,
                    },
                )
                await saver.asetup()
                implementation = "redis-search"
            except Exception as module_exc:
                logger.info(
                    "Redis Search/JSON unavailable; using core-command checkpointer: %s",
                    module_exc,
                )
                saver = AsyncBasicRedisSaver(
                    client,
                    ttl_seconds=self.checkpoint_ttl_minutes * 60,
                )
                await saver.asetup()
                implementation = "redis-basic"
            self.checkpointer = saver
            self.backend = "redis"
            self.checkpointer_implementation = implementation
            self.last_error = None
            logger.info("LangGraph checkpoints connected using %s.", implementation)
        except Exception as exc:
            self.last_error = str(exc)
            if self.client is not None:
                await self.client.aclose()
                self.client = None
            self.checkpointer = InMemorySaver()
            self.backend = "memory"
            self.checkpointer_implementation = "memory"
            if self.required:
                raise RuntimeError(f"Redis initialization failed: {exc}") from exc
            logger.warning(
                "Redis unavailable; using non-durable in-memory checkpoints: %s",
                exc,
            )

    async def close(self) -> None:
        """Close the application-scoped pool explicitly."""
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    def health(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "durable": self.backend == "redis",
            "checkpointer": self.checkpointer_implementation,
            "error": self.last_error,
        }

    @asynccontextmanager
    async def run_lock(
        self,
        thread_id: str,
        *,
        timeout_seconds: int = 900,
        wait_seconds: int = 5,
    ) -> AsyncIterator[None]:
        """Prevent two workers from mutating the same conversation concurrently."""
        key = f"agent:lock:thread:{thread_id}"
        if self.client is None:
            lock = self._local_locks.setdefault(key, asyncio.Lock())
            try:
                await asyncio.wait_for(lock.acquire(), timeout=wait_seconds)
            except TimeoutError as exc:
                raise RuntimeError(f"thread {thread_id!r} is already running") from exc
            try:
                yield
            finally:
                lock.release()
            return

        lock = self.client.lock(
            key,
            timeout=timeout_seconds,
            blocking_timeout=wait_seconds,
        )
        acquired = await lock.acquire()
        if not acquired:
            raise RuntimeError(f"thread {thread_id!r} is already running")
        try:
            yield
        finally:
            try:
                await lock.release()
            except Exception:
                logger.warning("Redis lock %s expired before release.", key)
