"""割り込み応答: ユーザーの質問に最も適切なペルソナを選ぶための補助。

LLM に「どのペルソナが答えるべきか」を選ばせるためのプロンプト構築と、その出力から
ペルソナキーを頑健に取り出すパーサを提供する（純粋関数・テスト容易）。
実際の選定・回答生成は DiscussionEngine が本モジュールを使って行う。
"""

from thesis_ai.llm.base import Message
from thesis_ai.personas import Persona

SELECTOR_SYSTEM = (
    "あなたは議論の司会者です。以下の参加者の中から、ユーザーの質問に最も適切に"
    "答えられる人を1人だけ選びます。回答は、選んだ参加者の英語キー（例: professor）"
    "だけを出力してください。説明は不要です。"
)


def build_selector_messages(personas: tuple[Persona, ...], user_message: str) -> list[Message]:
    """回答者選定用のメッセージ列を構築する。"""
    roster = "\n".join(f"- {p.key}: {p.display_name}" for p in personas)
    system = f"{SELECTOR_SYSTEM}\n\n参加者:\n{roster}"
    return [
        Message(role="system", content=system),
        Message(role="user", content=f"ユーザーの質問:\n{user_message}"),
    ]


def parse_persona_key(text: str, valid_keys: list[str]) -> str:
    """LLM 出力からペルソナキーを取り出す。該当なしは先頭キーにフォールバック。"""
    lowered = text.strip().lower()
    for key in valid_keys:
        if key in lowered:
            return key
    return valid_keys[0]


def parse_affirmative(text: str) -> bool:
    """LLM の はい/いいえ 出力を解釈する。判別できなければ False（=継続）を返す。"""
    lowered = text.strip().lower()
    if "いいえ" in lowered:
        return False
    return "はい" in lowered or "yes" in lowered
