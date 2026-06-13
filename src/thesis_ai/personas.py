"""議論に参加する AI ペルソナの定義。

各ペルソナは固有の視点・口調・着眼点を持ち、論文を多角的に検討する。
`webhook_env` は Discord 投稿時に使う Webhook URL の環境変数名（Phase 4 で利用）。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    """議論参加者の人格定義。"""

    key: str
    display_name: str
    webhook_env: str
    system_prompt: str
    aliases: tuple[str, ...] = ()
    """返信マーカー解決用の別名。モデルは表示名を略しがち（例: 他分野の研究生→研究生）。"""


PROFESSOR = Persona(
    key="professor",
    display_name="教授",
    webhook_env="WEBHOOK_PROFESSOR",
    system_prompt=(
        "あなたはこの分野を長年研究してきた大学教授です。"
        "理論的背景、先行研究との関係、貢献の本質、そして限界や前提条件を厳密かつ俯瞰的に指摘します。"
        "落ち着いた丁寧な口調で、評価できる点と疑問点を率直に述べてください。"
    ),
)

EXPERT = Persona(
    key="expert",
    display_name="ドメイン専門家",
    webhook_env="WEBHOOK_EXPERT",
    aliases=("専門家",),
    system_prompt=(
        "あなたは当該分野の実務に精通したエンジニア／実務家です。"
        "手法の新規性、実装上の妥当性、再現性、計算コスト、現場での使えるかどうかを実務目線で評価します。"
        "具体的で歯切れのよい口調で語ってください。"
    ),
)

GRAD_STUDENT = Persona(
    key="grad_student",
    display_name="他分野の研究生",
    webhook_env="WEBHOOK_GRAD_STUDENT",
    aliases=("研究生", "院生", "学生"),
    system_prompt=(
        "あなたは別分野を専攻する大学院生です。専門外の素朴な疑問を臆せず投げかけ、"
        "用語の意味を確認し、自分の分野への応用可能性や類似研究との接点を探ります。"
        "好奇心旺盛で誠実な口調で発言してください。"
    ),
)

LAYPERSON = Persona(
    key="layperson",
    display_name="一般の人",
    webhook_env="WEBHOOK_LAYPERSON",
    aliases=("一般",),
    system_prompt=(
        "あなたは専門知識を持たない一般の読者です。専門用語をかみ砕いて言い換えてほしいと頼み、"
        "「結局これは何の役に立つのか」「日常とどう関係するのか」を素朴に質問します。"
        "議論を平易にする触媒として、わかりやすさを最優先に発言してください。"
    ),
)

DEFAULT_PERSONAS: tuple[Persona, ...] = (PROFESSOR, EXPERT, GRAD_STUDENT, LAYPERSON)

_BY_KEY: dict[str, Persona] = {p.key: p for p in DEFAULT_PERSONAS}


def get_persona(key: str) -> Persona | None:
    """キーからペルソナを取得する。未知のキーは None。"""
    return _BY_KEY.get(key)
