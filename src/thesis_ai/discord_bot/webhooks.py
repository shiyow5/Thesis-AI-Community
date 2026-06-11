"""ペルソナごとの Discord Webhook 投稿。

Webhook は bot トークン不要で、投稿ごとに ``username`` / ``avatar_url`` を上書きできる。
これを使い、1 チャンネル内で複数ペルソナを別アバターとして発言させる。

実装は httpx で直接 POST する（discord.py 非依存・テスト容易）。レート制御として
投稿間に最小間隔を空け、429 は ``retry_after`` に従ってリトライする。
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx

from thesis_ai.personas import Persona

DISCORD_CONTENT_LIMIT = 2000

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]


class WebhookError(Exception):
    """Webhook 投稿の失敗。"""


def chunk_content(content: str, limit: int = DISCORD_CONTENT_LIMIT) -> list[str]:
    """Discord の文字数上限に収まるよう本文を分割する。改行境界を優先する。"""
    text = content.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        split_at = window.rfind("\n")
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return [c for c in chunks if c]


def _retry_after_seconds(resp: httpx.Response) -> float:
    """429 レスポンスから待機秒数を取り出す。"""
    try:
        body = resp.json()
        if isinstance(body, dict) and "retry_after" in body:
            return float(body["retry_after"])
    except (ValueError, TypeError):
        pass
    header = resp.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    return 1.0


class PersonaWebhookPoster:
    """ペルソナの発言を Webhook 経由でチャンネル / スレッドに投稿する。"""

    def __init__(
        self,
        client: httpx.AsyncClient,
        webhook_urls: dict[str, str],
        *,
        avatars: dict[str, str] | None = None,
        min_interval: float = 1.5,
        max_retries: int = 3,
        sleep: Sleeper | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._client = client
        self._urls = webhook_urls
        self._avatars = avatars or {}
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._sleep = sleep or asyncio.sleep
        self._clock = clock or time.monotonic
        self._last_post = 0.0

    async def _respect_interval(self) -> None:
        wait = self._min_interval - (self._clock() - self._last_post)
        if wait > 0:
            await self._sleep(wait)
        self._last_post = self._clock()

    async def post(self, persona: Persona, content: str, *, thread_id: str | None = None) -> None:
        """ペルソナの発言を投稿する。長文は複数メッセージに分割する。"""
        url = self._urls.get(persona.webhook_env)
        if not url:
            raise WebhookError(f"webhook URL not configured for {persona.webhook_env}")

        for chunk in chunk_content(content):
            await self._respect_interval()
            await self._post_chunk(url, persona, chunk, thread_id)

    async def _post_chunk(
        self, url: str, persona: Persona, content: str, thread_id: str | None
    ) -> None:
        payload: dict[str, str] = {"content": content, "username": persona.display_name}
        avatar = self._avatars.get(persona.key)
        if avatar:
            payload["avatar_url"] = avatar
        params = {"wait": "true"}
        if thread_id:
            params["thread_id"] = thread_id

        for _ in range(self._max_retries + 1):
            resp = await self._client.post(url, params=params, json=payload)
            if resp.status_code == 429:
                await self._sleep(_retry_after_seconds(resp))
                continue
            if resp.is_error:
                raise WebhookError(f"webhook post failed: {resp.status_code}")
            return
        raise WebhookError("webhook post failed: rate limited after retries")
