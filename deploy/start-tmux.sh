#!/usr/bin/env bash
# bot をデタッチ tmux セッションで起動する。
# サーバーの電源が入っていれば、ログアウトしても動き続ける（KillUserProcesses=no 前提）。
# 冪等: 既に起動済みなら何もしない。@reboot cron からも呼べる。
set -u

SESSION="thesis-ai"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMUX_BIN="$(command -v tmux || echo /usr/bin/tmux)"

# ローカルフォールバック用 ollama(:11435) を先に確実に起動する（冪等・依存担保）。
# 失敗してもボットは Flash-Lite へ降格できるので起動は止めない。
bash "${DIR}/deploy/start-ollama-local.sh" || true

if "${TMUX_BIN}" has-session -t "${SESSION}" 2>/dev/null; then
  echo "tmux セッション '${SESSION}' は既に稼働中。"
  exit 0
fi

"${TMUX_BIN}" new-session -d -s "${SESSION}" "bash '${DIR}/deploy/run-forever.sh'"
echo "tmux セッション '${SESSION}' を起動しました。"
echo "  ログ追尾: tail -f '${DIR}/logs/bot.log'"
echo "  画面接続: tmux attach -t ${SESSION}     (デタッチは Ctrl-b d)"
echo "  状態確認: tmux has-session -t ${SESSION} && echo running"
echo "  停止:     tmux kill-session -t ${SESSION}"
