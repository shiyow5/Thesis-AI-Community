"""config.Settings のロード挙動テスト。"""

import pytest
from pydantic import ValidationError

from thesis_ai.config import Settings


def test_loads_required_values_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    settings = Settings(_env_file=None)  # .env を無視してテスト隔離

    assert settings.gemini_api_key == "test-key"
    assert settings.discord_bot_token == "test-token"


def test_missing_required_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
