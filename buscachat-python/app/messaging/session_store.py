import json
import threading
from functools import lru_cache
from typing import Any, Protocol

from app.config import Settings


class ConversationStateStore(Protocol):
    def get_state(self, chat_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def set_state(self, chat_id: str, data: dict[str, Any] | None) -> None:
        raise NotImplementedError

    def save_embedding(self, chat_id: str, embedding: list[float] | None) -> None:
        raise NotImplementedError


class InMemoryConversationStateStore:
    def __init__(self) -> None:
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get_state(self, chat_id: str) -> dict[str, Any]:
        with self._lock:
            if chat_id not in self._state:
                self._state[chat_id] = {"paso": "menu"}
            return self._state[chat_id]

    def set_state(self, chat_id: str, data: dict[str, Any] | None) -> None:
        with self._lock:
            if data is None:
                self._state.pop(chat_id, None)
            else:
                self._state[chat_id] = data

    def save_embedding(self, chat_id: str, embedding: list[float] | None) -> None:
        with self._lock:
            state = self._state.get(chat_id, {})
            if embedding:
                state["_embedding"] = list(embedding)
            else:
                state.pop("_embedding", None)
            self._state[chat_id] = state


class RedisConversationStateStore:
    def __init__(
        self,
        *,
        url: str,
        key_prefix: str,
        ttl_seconds: int | None = None,
    ) -> None:
        from redis import Redis

        self._redis = Redis.from_url(url, decode_responses=True)
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds if ttl_seconds and ttl_seconds > 0 else None

    def _key(self, chat_id: str) -> str:
        return f"{self._key_prefix}{chat_id}"

    def get_state(self, chat_id: str) -> dict[str, Any]:
        raw = self._redis.get(self._key(chat_id))
        if raw:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = None
            if isinstance(value, dict):
                return value

        state = {"paso": "menu"}
        self.set_state(chat_id, state)
        return state

    def set_state(self, chat_id: str, data: dict[str, Any] | None) -> None:
        key = self._key(chat_id)
        if data is None:
            self._redis.delete(key)
            return

        raw = json.dumps(data, ensure_ascii=False)
        if self._ttl_seconds:
            self._redis.set(key, raw, ex=self._ttl_seconds)
        else:
            self._redis.set(key, raw)

    def save_embedding(self, chat_id: str, embedding: list[float] | None) -> None:
        state = self.get_state(chat_id)
        if embedding:
            state["_embedding"] = list(embedding)
        else:
            state.pop("_embedding", None)
        self.set_state(chat_id, state)


_default_store = InMemoryConversationStateStore()


def get_default_conversation_state_store() -> ConversationStateStore:
    return _default_store


@lru_cache
def _cached_store(
    store_name: str,
    redis_url: str,
    redis_key_prefix: str,
    ttl_seconds: int | None,
) -> ConversationStateStore:
    if store_name == "redis":
        return RedisConversationStateStore(
            url=redis_url,
            key_prefix=redis_key_prefix,
            ttl_seconds=ttl_seconds,
        )
    return _default_store


def get_conversation_state_store(settings: Settings) -> ConversationStateStore:
    return _cached_store(
        settings.conversation_state_store.strip().lower(),
        settings.redis_url,
        settings.redis_key_prefix,
        settings.conversation_state_ttl_seconds,
    )
