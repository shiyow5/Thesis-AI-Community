"""議論制御のための LLM プロンプト構築と出力パーサ（純粋関数・テスト容易）。

- 回答者選定（割り込み時にどのペルソナが答えるか）
- 次の発言者選定（自由発話の司会判断。終了なら None）
- 返信マーカー解析（発言が特定の参加者への返信かどうか）
"""

import re

from thesis_ai.llm.base import Message
from thesis_ai.personas import Persona

SELECTOR_SYSTEM = (
    "あなたは議論の司会者です。以下の参加者の中から、ユーザーの質問に最も適切に"
    "答えられる人を1人だけ選びます。回答は、選んだ参加者の英語キー（例: professor）"
    "だけを出力してください。説明は不要です。"
)

NEXT_SPEAKER_SYSTEM = (
    "あなたは論文を議論するパネルの司会者です。これまでの流れを読み、次に発言するのに"
    "最もふさわしい参加者を1人選びます。まだ誰も発言していなければ口火を切る人を選びます。"
    "未回答の質問が残っていればそれに答えられる人を優先します。論点が十分に出尽くし、"
    "質問にも答えが出ていて自然に終えてよいなら DONE と出力します。"
    "出力は参加者の英語キー（例: professor）1つ、または DONE のみ。説明は不要です。"
)

_DONE_RE = re.compile(r"\bdone\b", re.IGNORECASE)


def is_done_signal(text: str) -> bool:
    """司会の出力が議論の終了（DONE）を示すかを判定する。

    有効なペルソナキーが取れなかったときに、「終了の意思表示」と「単なる解析不能」を
    区別するために使う。前者は議論を終え、後者は継続（ラウンドロビン）させる。
    """
    return bool(_DONE_RE.search(text))


def _roster(personas: tuple[Persona, ...]) -> str:
    return "\n".join(f"- {p.key}: {p.display_name}" for p in personas)


def build_selector_messages(personas: tuple[Persona, ...], user_message: str) -> list[Message]:
    """回答者選定用のメッセージ列を構築する。"""
    system = f"{SELECTOR_SYSTEM}\n\n参加者:\n{_roster(personas)}"
    return [
        Message(role="system", content=system),
        Message(role="user", content=f"ユーザーの質問:\n{user_message}"),
    ]


def build_next_speaker_messages(personas: tuple[Persona, ...], history: str) -> list[Message]:
    """次の発言者選定用のメッセージ列を構築する。"""
    body = history or "（まだ発言はありません）"
    return [
        Message(role="system", content=f"{NEXT_SPEAKER_SYSTEM}\n\n参加者:\n{_roster(personas)}"),
        Message(
            role="user",
            content=(
                f"これまでの議論:\n{body}\n\n"
                "次に発言すべき参加者のキー、または DONE を出力してください。"
            ),
        ),
    ]


def parse_persona_key(text: str, valid_keys: list[str]) -> str:
    """LLM 出力からペルソナキーを取り出す。該当なしは先頭キーにフォールバック。"""
    lowered = text.strip().lower()
    for key in valid_keys:
        if key in lowered:
            return key
    return valid_keys[0]


def parse_next_speaker(text: str, valid_keys: list[str]) -> str | None:
    """次の発言者キーを返す。キーが見つからなければ（DONE 含む）None=終了。"""
    lowered = text.strip().lower()
    for key in valid_keys:
        if key in lowered:
            return key
    return None


_HONORIFICS = ("さん", "さま", "様", "氏", "先生", "くん", "君", "ちゃん")
_HONORIFIC_HEAD_RE = re.compile(rf"^(?:{'|'.join(_HONORIFICS)})")
# ``@名前`` の直後にこれらの助詞が続く場合、名前は文の構成要素（主語等）なので本文に残す。
_PARTICLES = ("の", "が", "は", "を", "に", "へ", "と", "も", "で", "や", "から", "まで", "より")
_SEPARATORS = " 　:：、,。\n\t"


def _longest_leading_alias(text: str, aliases: dict[str, str]) -> str | None:
    """``text`` の先頭に一致する最長のエイリアス名を返す（無ければ None）。"""
    best: str | None = None
    for name in aliases:
        if name and text.startswith(name) and (best is None or len(name) > len(best)):
            best = name
    return best


def parse_reply_marker(text: str, aliases: dict[str, str]) -> tuple[str | None, str]:
    """先頭の ``@名前`` 返信マーカーを解析し、(対象ペルソナキー, 整形後の本文) を返す。

    モデルはメンションを 2 通りに使う:
    - 純粋な宛先指定（例: ``@教授、…`` / ``@研究生さん\n…``）→ 名前ごと本文から除去する。
    - 文中の参照（例: ``@研究生さんの例えを聞いて…``）→ 名前は文法上必要なので本文に残し、
      ``@`` 記号のみ除去する。直後が助詞なら後者と判定する。

    ``aliases`` はキー/表示名/略称 → ペルソナキーの対応。
    """
    stripped = text.lstrip()
    if not stripped.startswith("@"):
        return None, text.strip()

    after_at = stripped[1:]
    name = _longest_leading_alias(after_at, aliases)
    if name is None:
        return None, text.strip()
    key = aliases[name]

    rest = after_at[len(name) :].lstrip(" 　")
    honorific_match = _HONORIFIC_HEAD_RE.match(rest)
    honorific = honorific_match.group(0) if honorific_match else ""
    tail = rest[len(honorific) :]

    if any(tail.startswith(p) for p in _PARTICLES):
        # 文中参照: 名前＋敬称を残し、@ と名前間の空白だけ正規化する。
        return key, (name + honorific + tail).strip()
    # 宛先指定: 名前・敬称・区切りをまとめて除去する。
    return key, tail.lstrip(_SEPARATORS).strip()


def strip_at_sigils(text: str, aliases: dict[str, str]) -> str:
    """本文中に残った ``@名前`` の ``@`` 記号だけを除去する（名前は残す）。

    先頭以外（文中）のメンションは返信マーカー解析の対象外で ``@`` が残るため、
    ``@他分野の研究生 さん`` → ``他分野の研究生 さん`` のように記号のみ整える。
    長い名前を優先して置換し、部分一致での取りこぼしを防ぐ。
    """
    for name in sorted(aliases, key=len, reverse=True):
        if name:
            text = text.replace(f"@{name}", name)
    return text
