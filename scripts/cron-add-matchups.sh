#!/bin/bash
# cron-add-matchups.sh
# 90分ごと（1日16回）対面ガイドを自動追加する（batch=12, Gemini 3.1 Flash Lite + Sonnet レビュー）
# 503時は即バッチ終了して次のcronに委ねる。Sonnet review 2件連続失敗時もバッチ終了。
#
# cron登録:
#   0  0,3,6,9,12,15,18,21 * * * /home/ojita/lol-guides-jp/scripts/cron-add-matchups.sh >> /home/ojita/lol-guides-jp/scripts/cron.log 2>&1
#   30 1,4,7,10,13,16,19,22 * * * /home/ojita/lol-guides-jp/scripts/cron-add-matchups.sh >> /home/ojita/lol-guides-jp/scripts/cron.log 2>&1

set -euo pipefail

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
LOCK_FILE="/tmp/lol-guides-add-matchups.lock"
log_prefix() { echo "[$(date '+%Y-%m-%d %H:%M:%S')]"; }

# 重複実行防止（PIDベース: 異常終了でロックが残った場合は自動回復）
if [ -f "$LOCK_FILE" ]; then
    pid=$(cat "$LOCK_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        echo "$(log_prefix) INFO: 前回の実行が残っているためスキップ (PID=${pid})"
        exit 0
    else
        echo "$(log_prefix) WARN: ロックファイルが残っていたが PID=${pid} は存在しない。削除して続行"
        rm -f "$LOCK_FILE"
    fi
fi
echo $$ > "$LOCK_FILE"
trap "rm -f '${LOCK_FILE}'" EXIT

cd "$PROJECT_DIR"

echo "$(log_prefix) ===== cron-add-matchups 起動 ====="
"${PROJECT_DIR}/scripts/add-matchups.sh" --batch 12 --sleep 10 2>&1 | tee /tmp/add-matchups-last.log
echo "$(log_prefix) ===== cron-add-matchups 終了 ====="

# 実行結果をCLAUDE.local.mdに記録
SUMMARY=$(grep "完了: 成功=" /tmp/add-matchups-last.log | tail -1 || echo "完了行なし")
echo "- [$(date '+%Y-%m-%d %H:%M')] lol-guides-jp: cron-add-matchups ${SUMMARY}" \
    >> /home/ojita/CLAUDE.local.md
