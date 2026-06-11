"""アプリ設定。`.env` から読み込み、必須値が欠けていれば起動時に fail-fast する。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """環境変数 / `.env` からロードされる設定値。

    各フェーズで利用するフィールドは段階的に追加する。Phase 0 では起動に最低限
    必要なシークレットのみを必須とする。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 必須 ---
    gemini_api_key: str
    discord_bot_token: str


def load_settings() -> Settings:
    """設定をロードする。必須値が欠けていれば pydantic がエラーを送出する。"""
    return Settings()  # 値は env / .env から供給される
