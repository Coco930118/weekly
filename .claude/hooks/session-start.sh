#!/bin/bash
set -euo pipefail

# JST timezone
export TZ="Asia/Tokyo"

# Git user settings (for commits in remote environment)
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  git config --global user.email "claude-code@anthropic.com" 2>/dev/null || true
  git config --global user.name "Claude Code" 2>/dev/null || true
fi

# Detect if today is Monday and output routine trigger
DAY=$(TZ="Asia/Tokyo" date +%u)  # 1=Mon ... 7=Sun
HOUR=$(TZ="Asia/Tokyo" date +%H)
TODAY=$(TZ="Asia/Tokyo" date +%Y-%m-%d)

echo "=== coconocanvas Session Start ==="
echo "Date (JST): ${TODAY}"

if [ "$DAY" = "1" ]; then
  echo "MONDAY_ROUTINE=true" >> "${CLAUDE_ENV_FILE:-/dev/null}" 2>/dev/null || true
  echo ""
  echo "📅 本日は月曜日です。"
  echo "CLAUDE.md の「月曜自動実行ルーティン」に従い、LINEスタンプ制作を自動実行します。"
  echo "作業開始日: ${TODAY}"
fi
