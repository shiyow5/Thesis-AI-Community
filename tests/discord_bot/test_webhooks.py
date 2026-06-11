"""PersonaWebhookPoster と chunk_content のテスト。"""

import httpx
import pytest
import respx

from thesis_ai.discord_bot.webhooks import (
    DISCORD_CONTENT_LIMIT,
    PersonaWebhookPoster,
    WebhookError,
    chunk_content,
)
from thesis_ai.personas import PROFESSOR

WEBHOOK_URL = "https://discord.com/api/webhooks/1/abc"


def _poster(client: httpx.AsyncClient, **kwargs: object) -> PersonaWebhookPoster:
    return PersonaWebhookPoster(
        client,
        {PROFESSOR.webhook_env: WEBHOOK_URL},
        min_interval=0.0,
        sleep=_noop_sleep,
        **kwargs,  # type: ignore[arg-type]
    )


async def _noop_sleep(_seconds: float) -> None:
    return None


def test_chunk_content_short_single() -> None:
    assert chunk_content("hello") == ["hello"]


def test_chunk_content_empty() -> None:
    assert chunk_content("   ") == []


def test_chunk_content_splits_on_newline() -> None:
    block = "a" * 1500 + "\n" + "b" * 1500
    chunks = chunk_content(block)

    assert len(chunks) == 2
    assert all(len(c) <= DISCORD_CONTENT_LIMIT for c in chunks)


def test_chunk_content_hard_split_without_newline() -> None:
    chunks = chunk_content("x" * 4500)

    assert len(chunks) == 3
    assert all(len(c) <= DISCORD_CONTENT_LIMIT for c in chunks)


@respx.mock
async def test_post_sends_username_and_content() -> None:
    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(204))

    async with httpx.AsyncClient() as client:
        await _poster(client).post(PROFESSOR, "こんにちは")

    assert route.called
    body = route.calls.last.request.read()
    assert b'"username"' in body
    assert route.calls.last.request.url.params["wait"] == "true"


@respx.mock
async def test_post_includes_thread_id() -> None:
    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(204))

    async with httpx.AsyncClient() as client:
        await _poster(client).post(PROFESSOR, "hi", thread_id="999")

    assert route.calls.last.request.url.params["thread_id"] == "999"


@respx.mock
async def test_post_long_content_sends_multiple_requests() -> None:
    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(204))

    async with httpx.AsyncClient() as client:
        await _poster(client).post(PROFESSOR, "y" * 4500)

    assert route.call_count == 3


@respx.mock
async def test_post_retries_on_429_then_succeeds() -> None:
    route = respx.post(WEBHOOK_URL).mock(
        side_effect=[
            httpx.Response(429, json={"retry_after": 0.01}),
            httpx.Response(204),
        ]
    )

    async with httpx.AsyncClient() as client:
        await _poster(client).post(PROFESSOR, "hi")

    assert route.call_count == 2


@respx.mock
async def test_post_raises_after_retry_budget() -> None:
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(429, json={"retry_after": 0.0}))

    async with httpx.AsyncClient() as client:
        with pytest.raises(WebhookError):
            await _poster(client, max_retries=1).post(PROFESSOR, "hi")


@respx.mock
async def test_post_raises_on_server_error() -> None:
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(WebhookError):
            await _poster(client).post(PROFESSOR, "hi")


async def test_post_unknown_webhook_raises() -> None:
    async with httpx.AsyncClient() as client:
        poster = PersonaWebhookPoster(client, {}, min_interval=0.0, sleep=_noop_sleep)
        with pytest.raises(WebhookError, match="not configured"):
            await poster.post(PROFESSOR, "hi")
