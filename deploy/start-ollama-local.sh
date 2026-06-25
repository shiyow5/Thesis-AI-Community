#!/usr/bin/env bash
# ボットのローカルフォールバック用 ollama(:11435) の watchdog を tmux で起動する（冪等）。
# 監視ループ本体は run-ollama-forever.sh。@reboot / start-tmux.sh から呼ばれる。
# tmux セッションなので、電源が入っていればログアウト後も監視が継続する（KillUserProcesses=no 前提）。
# テスト用に OLLAMA_LOCAL_HOST で待受ホスト（とセッション名）を上書き可能。
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${OLLAMA_LOCAL_HOST:-127.0.0.1:11435}"
SESSION="ollama-${HOST##*:}"
TMUX_BIN="$(command -v tmux || echo /usr/bin/tmux)"

if "${TMUX_BIN}" has-session -t "${SESSION}" 2>/dev/null; then
  echo "ollama 監視セッション '${SESSION}' は既に稼働中。"
  exit 0
fi

"${TMUX_BIN}" new-session -d -s "${SESSION}" \
  "OLLAMA_LOCAL_HOST='${HOST}' bash '${DIR}/deploy/run-ollama-forever.sh'"
echo "ollama 監視セッション '${SESSION}' を起動しました（host=${HOST}）。"
echo "  ログ: tail -f '${DIR}/logs/ollama-${HOST##*:}.log'"
echo "  接続: tmux attach -t ${SESSION}     (デタッチは Ctrl-b d)"
echo "  停止: tmux kill-session -t ${SESSION}"
