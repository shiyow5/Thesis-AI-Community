"""config.Settings のロード挙動テスト。"""

import pytest
from pydantic import ValidationError

from thesis_ai.config import Settings


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]  # .env を無視してテスト隔離


def test_loads_required_values_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    settings = Settings(_env_file=None)  # env から供給

    assert settings.gemini_api_key == "test-key"
    assert settings.discord_bot_token == "test-token"


def test_missing_required_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_webhook_map_returns_only_configured() -> None:
    settings = _settings(
        gemini_api_key="k",
        discord_bot_token="t",
        webhook_professor="https://example/p",
        webhook_expert="https://example/e",
    )

    mapping = settings.webhook_map()

    assert mapping == {
        "WEBHOOK_PROFESSOR": "https://example/p",
        "WEBHOOK_EXPERT": "https://example/e",
    }


def test_missing_webhooks_lists_unconfigured() -> None:
    settings = _settings(
        gemini_api_key="k",
        discord_bot_token="t",
        webhook_professor="https://example/p",
    )

    missing = settings.missing_webhooks()

    assert "WEBHOOK_PROFESSOR" not in missing
    assert "WEBHOOK_EXPERT" in missing
    assert "WEBHOOK_GRAD_STUDENT" in missing
    assert "WEBHOOK_LAYPERSON" in missing
