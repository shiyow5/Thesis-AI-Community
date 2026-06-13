#!/usr/bin/env bash
# Thesis-AI-Community を systemd ユーザーサービスとして導入する（WSL2 / Linux 用）。
# uv と作業ディレクトリのパスを実環境から自動補完してユニットを生成し、起動する。
set -euo pipefail

SERVICE="thesis-ai"
WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

UV="$(command -v uv || true)"
if [[ -z "${UV}" ]]; then
  echo "error: uv が見つかりません。先に uv を導入してください。" >&2
  exit 1
fi

if ! systemctl --user is-system-running >/dev/null 2>&1; then
  echo "error: ユーザー systemd が利用できません（WSL なら /etc/wsl.conf で systemd=true を有効化）。" >&2
  exit 1
fi

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "${UNIT_DIR}"
UNIT_PATH="${UNIT_DIR}/${SERVICE}.service"

cat > "${UNIT_PATH}" <<EOF
[Unit]
Description=Thesis-AI-Community Discord bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${WORKDIR}
ExecStart=${UV} run python -m thesis_ai.main
Restart=always
RestartSec=5
Environment=PATH=$(dirname "${UV}"):/usr/bin:/bin

[Install]
WantedBy=default.target
EOF

echo "生成: ${UNIT_PATH}"
systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE}.service"

echo
echo "状態:"
systemctl --user --no-pager status "${SERVICE}.service" | head -n 6 || true

cat <<EOF

------------------------------------------------------------
導入完了。よく使うコマンド:
  systemctl --user status  ${SERVICE}      # 状態
  systemctl --user restart ${SERVICE}      # 再起動
  systemctl --user stop    ${SERVICE}      # 停止
  journalctl --user -u ${SERVICE} -f       # ログ追尾

WSL/ログアウト後も自動起動させるには linger を有効化（要 root, 一度だけ）:
  sudo loginctl enable-linger ${USER}

Windows ログオン時に WSL を自動起動するには、タスクスケジューラで
ログオン時に次を実行する設定を追加してください:
  wsl.exe -d <ディストリ名> -u ${USER} true
------------------------------------------------------------
EOF
