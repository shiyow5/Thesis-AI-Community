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

_REPLY_MARKER_RE = re.compile(r"^\s*@(\w+)\b[\s:、,]*")
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
_LEADING_HONORIFIC_RE = re.compile(rf"^(?:{'|'.join(_HONORIFICS)})[\s:、,]*")


def _strip_honorific_suffix(token: str) -> str:
    """トークン末尾の敬称（例: ``研究生さん`` → ``研究生``）を 1 つ取り除く。"""
    for honorific in _HONORIFICS:
        if token.endswith(honorific) and len(token) > len(honorific):
            return token[: -len(honorific)]
    return token


def _resolve_alias(token: str, aliases: dict[str, str]) -> str | None:
    """``@`` 直後のトークンをペルソナキーに解決する。

    完全一致 → 最長前方一致 → 部分一致の順で試す。モデルは表示名に敬称を付けたり
    （例: ``@教授さん``）、表示名を略したり（例: ``他分野の研究生`` → ``研究生``）するため、
    末尾敬称を落としたうえで柔軟に解決する。
    """
    token = _strip_honorific_suffix(token.strip())
    if not token:
        return None
    if token in aliases:
        return aliases[token]
    best_name: str | None = None
    for name in aliases:
        if token.startswith(name) and (best_name is None or len(name) > len(best_name)):
            best_name = name
    if best_name is not None:
        return aliases[best_name]
    # 略称: トークンと表示名のどちらかが他方を含む（誤マッチ抑制のため 2 文字以上）。
    if len(token) >= 2:
        for name in aliases:
            if len(name) >= 2 and (token in name or name in token):
                return aliases[name]
    return None


def parse_reply_marker(text: str, aliases: dict[str, str]) -> tuple[str | None, str]:
    """先頭の ``@名前`` 返信マーカーを解析し、(対象ペルソナキー, 除去後の本文) を返す。

    ``aliases`` はキー/表示名 → ペルソナキーの対応。モデルは表示名（例: @教授）でも
    キー（例: @professor）でも、敬称付き（例: @教授さん）でも書きうるため許容する。
    また ``@表示名 さん`` のように空白＋敬称で書かれると本文先頭に敬称が残るため除去する。
    """
    match = _REPLY_MARKER_RE.match(text)
    if match:
        key = _resolve_alias(match.group(1), aliases)
        if key is not None:
            rest = text[match.end() :]
            rest = _LEADING_HONORIFIC_RE.sub("", rest, count=1)
            return key, rest.strip()
    return None, text.strip()
