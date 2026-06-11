"""アプリ設定。`.env` から読み込み、必須値が欠けていれば起動時に fail-fast する。"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from thesis_ai.personas import DEFAULT_PERSONAS


class Settings(BaseSettings):
    """環境変数 / `.env` からロードされる設定値。

    LLM / Discord トークンは必須。Webhook URL やチャンネル ID は実運用で必要だが、
    一部機能のみ使う場合やテスト時に未設定でも import できるよう任意とする。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 必須 ---
    gemini_api_key: str
    discord_bot_token: str

    # --- Discord（実運用で必要） ---
    discord_guild_id: int | None = None
    discord_channel_id: int | None = None

    # --- ペルソナ投稿用 Webhook ---
    webhook_professor: str | None = None
    webhook_expert: str | None = None
    webhook_grad_student: str | None = None
    webhook_layperson: str | None = None

    # --- LLM モデル名 ---
    # Gemini API 上の Gemma 4 は gemma-4-31b-it / gemma-4-26b-a4b-it（27b は存在しない）
    gemma_model: str = "gemma-4-31b-it"
    # フォールバックは無料枠の大きい Flash-Lite（~1,000 RPD）
    flash_model: str = "gemini-2.5-flash-lite"

    # --- 議論ポリシー ---
    # 1 論文あたりの総発言数の上限（暴走防止）。司会判断で論点が尽きれば上限前に終了する
    discussion_max_turns: int = 20

    # --- ローカルフォールバック ---
    local_llm_base_url: str = "http://localhost:1234/v1"
    local_llm_model: str | None = None

    # --- 任意 ---
    contact_email: str | None = None

    def webhook_map(self) -> dict[str, str]:
        """``webhook_env`` 名 → URL の辞書を返す（設定済みのものだけ）。"""
        mapping = {
            "WEBHOOK_PROFESSOR": self.webhook_professor,
            "WEBHOOK_EXPERT": self.webhook_expert,
            "WEBHOOK_GRAD_STUDENT": self.webhook_grad_student,
            "WEBHOOK_LAYPERSON": self.webhook_layperson,
        }
        return {env: url for env, url in mapping.items() if url}

    def missing_webhooks(self) -> list[str]:
        """未設定のペルソナ Webhook 環境変数名を返す。"""
        configured = self.webhook_map()
        return [p.webhook_env for p in DEFAULT_PERSONAS if p.webhook_env not in configured]


def load_settings() -> Settings:
    """設定をロードする。必須値が欠けていれば pydantic がエラーを送出する。"""
    return Settings()  # 値は env / .env から供給される
