"""Async LangGraph checkpointer using only the core Redis command set.

This adapter intentionally avoids RedisJSON and RediSearch so it works with
Memurai and plain Redis installations. Values still use LangGraph's serializer;
Redis only stores opaque, base64-encoded envelopes.
"""
from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any
from urllib.parse import quote

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)


class AsyncBasicRedisSaver(BaseCheckpointSaver):
    """Durable async checkpointer backed by strings, hashes, and sorted sets."""

    def __init__(self, redis_client: Any, *, ttl_seconds: int = 86_400) -> None:
        super().__init__()
        self.redis = redis_client
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.prefix = "agent:langgraph"

    async def asetup(self) -> None:
        await self.redis.ping()

    @staticmethod
    def _part(value: str) -> str:
        return quote(value, safe="")

    def _index_key(self, thread_id: str, namespace: str) -> str:
        return f"{self.prefix}:index:{self._part(thread_id)}:{self._part(namespace)}"

    def _data_key(self, thread_id: str, namespace: str, checkpoint_id: str) -> str:
        return (
            f"{self.prefix}:data:{self._part(thread_id)}:"
            f"{self._part(namespace)}:{self._part(checkpoint_id)}"
        )

    def _writes_key(self, thread_id: str, namespace: str, checkpoint_id: str) -> str:
        return (
            f"{self.prefix}:writes:{self._part(thread_id)}:"
            f"{self._part(namespace)}:{self._part(checkpoint_id)}"
        )

    def _pack(self, value: Any) -> dict[str, str]:
        type_name, payload = self.serde.dumps_typed(value)
        return {
            "type": type_name,
            "data": base64.b64encode(payload).decode("ascii"),
        }

    def _unpack(self, value: dict[str, str]) -> Any:
        return self.serde.loads_typed(
            (value["type"], base64.b64decode(value["data"]))
        )

    @staticmethod
    def _config(thread_id: str, namespace: str, checkpoint_id: str) -> RunnableConfig:
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def _ids(
        self,
        thread_id: str,
        namespace: str,
        *,
        before_id: str | None = None,
        limit: int | None = None,
    ) -> list[str]:
        raw_ids = await self.redis.zrevrange(self._index_key(thread_id, namespace), 0, -1)
        ids = [item.decode() if isinstance(item, bytes) else str(item) for item in raw_ids]
        if before_id:
            ids = [checkpoint_id for checkpoint_id in ids if checkpoint_id < before_id]
        return ids if limit is None else ids[:limit]

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        configurable = config["configurable"]
        thread_id = str(configurable["thread_id"])
        namespace = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = get_checkpoint_id(config)
        if checkpoint_id is None:
            ids = await self._ids(thread_id, namespace, limit=1)
            if not ids:
                return None
            checkpoint_id = ids[0]

        raw = await self.redis.get(self._data_key(thread_id, namespace, checkpoint_id))
        if raw is None:
            return None
        envelope = json.loads(raw)

        pending_writes: list[tuple[str, str, Any]] = []
        writes = await self.redis.hvals(
            self._writes_key(thread_id, namespace, checkpoint_id)
        )
        decoded_writes = [json.loads(item) for item in writes]
        decoded_writes.sort(key=lambda item: (item["task_path"], item["task_id"], item["idx"]))
        for item in decoded_writes:
            pending_writes.append(
                (item["task_id"], item["channel"], self._unpack(item["value"]))
            )

        parent_id = envelope.get("parent_checkpoint_id")
        return CheckpointTuple(
            config=self._config(thread_id, namespace, checkpoint_id),
            checkpoint=self._unpack(envelope["checkpoint"]),
            metadata=self._unpack(envelope["metadata"]),
            parent_config=(
                self._config(thread_id, namespace, parent_id) if parent_id else None
            ),
            pending_writes=pending_writes,
        )

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        if config is None:
            raise ValueError("A thread_id is required when listing basic Redis checkpoints")
        configurable = config["configurable"]
        thread_id = str(configurable["thread_id"])
        namespace = str(configurable.get("checkpoint_ns", ""))
        before_id = get_checkpoint_id(before) if before else None
        yielded = 0
        for checkpoint_id in await self._ids(
            thread_id, namespace, before_id=before_id
        ):
            item = await self.aget_tuple(self._config(thread_id, namespace, checkpoint_id))
            if item is None:
                continue
            if filter and any(item.metadata.get(key) != value for key, value in filter.items()):
                continue
            yield item
            yielded += 1
            if limit is not None and yielded >= limit:
                break

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        configurable = config["configurable"]
        thread_id = str(configurable["thread_id"])
        namespace = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = checkpoint["id"]
        parent_id = configurable.get("checkpoint_id")
        envelope = {
            "checkpoint": self._pack(checkpoint),
            "metadata": self._pack(get_checkpoint_metadata(config, metadata)),
            "parent_checkpoint_id": parent_id,
        }
        index_key = self._index_key(thread_id, namespace)
        data_key = self._data_key(thread_id, namespace, checkpoint_id)
        sequence = await self.redis.incr(f"{self.prefix}:sequence")
        async with self.redis.pipeline(transaction=True) as pipeline:
            pipeline.set(data_key, json.dumps(envelope), ex=self.ttl_seconds)
            pipeline.zadd(index_key, {checkpoint_id: sequence})
            pipeline.expire(index_key, self.ttl_seconds)
            await pipeline.execute()
        return self._config(thread_id, namespace, checkpoint_id)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        configurable = config["configurable"]
        thread_id = str(configurable["thread_id"])
        namespace = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(configurable["checkpoint_id"])
        key = self._writes_key(thread_id, namespace, checkpoint_id)
        async with self.redis.pipeline(transaction=True) as pipeline:
            for idx, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                field = f"{self._part(task_id)}:{write_idx}"
                encoded = json.dumps(
                    {
                        "task_id": task_id,
                        "task_path": task_path,
                        "idx": write_idx,
                        "channel": channel,
                        "value": self._pack(value),
                    }
                )
                if write_idx >= 0:
                    pipeline.hsetnx(key, field, encoded)
                else:
                    pipeline.hset(key, field, encoded)
            pipeline.expire(key, self.ttl_seconds)
            await pipeline.execute()

    async def adelete_thread(self, thread_id: str) -> None:
        encoded_thread = self._part(thread_id)
        keys: list[Any] = []
        for kind in ("index", "data", "writes"):
            async for key in self.redis.scan_iter(
                match=f"{self.prefix}:{kind}:{encoded_thread}:*"
            ):
                keys.append(key)
        if keys:
            await self.redis.delete(*keys)

    # The backend always invokes LangGraph asynchronously. Explicit sync errors
    # prevent accidental event-loop blocking if this adapter is reused elsewhere.
    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        raise NotImplementedError("Use aget_tuple with AsyncBasicRedisSaver")

    def list(self, config: RunnableConfig | None, **kwargs: Any):
        raise NotImplementedError("Use alist with AsyncBasicRedisSaver")

    def put(self, *args: Any, **kwargs: Any) -> RunnableConfig:
        raise NotImplementedError("Use aput with AsyncBasicRedisSaver")

    def put_writes(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("Use aput_writes with AsyncBasicRedisSaver")

    def delete_thread(self, thread_id: str) -> None:
        raise NotImplementedError("Use adelete_thread with AsyncBasicRedisSaver")
