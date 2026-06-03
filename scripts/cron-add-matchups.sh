#!/bin/bash
# cron-add-matchups.sh
# 5時間ごと（1日5回）対面ガイドを自動追加する（batch=20, 案B Sonnet 4.6 + WebSearch, lite モード）
# missing-*.txt が空になったら自動的に requeue-*.txt（残数最多のロール）に切替。
#
# cron登録:
#   0 0,5,10,15,20 * * * bash /home/ojita/lol-guides-jp/scripts/cron-add-matchups.sh >> /home/ojita/lol-guides-jp/scripts/cron.log 2>&1
#
# 枠タイプ検証（dry-run、add-matchups.sh は呼ばず段選択だけ確認）:
#   FORCE_HOUR=5  bash scripts/cron-add-matchups.sh --dry-run   # subrole 枠の選択を確認
#   FORCE_HOUR=10 bash scripts/cron-add-matchups.sh --dry-run   # requeue 枠の選択を確認

set -euo pipefail

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
LOCK_FILE="/tmp/lol-guides-add-matchups.lock"
log_prefix() { echo "[$(date '+%Y-%m-%d %H:%M:%S')]"; }

# --- ドライランフラグ ---
DRY_RUN=0
for _arg in "$@"; do [ "$_arg" = "--dry-run" ] && DRY_RUN=1; done

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
# cost-mode lite: $0.30/件想定。品質劣化が目立てば --cost-mode quality に切替（notes/migration-2026-05-24-gen-matchup.md 参照）。
#
# DRY_RUN の方針: 4段切替の判定までは実行し、どの段に入るか・どのキューを使うかを報告する。
# add-matchups.sh の呼び出しはスキップする（その dry-run は単体で確認すること）。

# 4段切替: missing → requeue → missing-subrole → requeue-subrole
# subrole 系は matchups-sub.md に書き込むため、add-matchups.sh に --target を指定する。
#
# 枠タイプ制（2026-06-03 追加）: requeue(メイン再生成) がパッチ追従で定期的に再充填され、
# subrole が構造的に後回しになってサイトに1件も出ない問題への対処。
# 実行時刻で枠を分け、subrole 枠では subrole を requeue より優先する。
#   - subrole 枠（5,15時）: missing → missing-subrole → requeue-subrole → requeue
#   - requeue 枠（その他 0,10,20時）: missing → requeue → missing-subrole → requeue-subrole
# どちらの枠でもメイン新規 missing（新チャンプ等）は最優先（取りこぼし防止）。
#
# 「残数最多のロール」を毎回選ぶラウンドロビン: requeue / subrole 系で使う
pick_max_remaining() {
    local pattern="$1"
    for f in $pattern; do
        [ -f "$f" ] && [ -s "$f" ] && echo "$(wc -l < "$f") $f"
    done | sort -rn | head -1 | awk '{print $2}'
}

# 各段を試す。キューがあれば SELECTED_* を設定して return 0、空なら return 1。
# set -e 下でも || で連鎖するため return 1 は安全（左辺の非ゼロは set -e 対象外）。
try_requeue() {
    local t; t=$(pick_max_remaining "${PROJECT_DIR}/scripts/requeue-[!s]*.txt")
    [ -z "${t:-}" ] && return 1
    SELECTED_STAGE="requeue"; SELECTED_SOURCE="$t"; SELECTED_TARGET="matchups.md"; SELECTED_FORCE="--force"
    echo "$(log_prefix) INFO: requeue モード ($(basename "$t"), 残 $(wc -l < "$t") 件)"
}
try_missing_subrole() {
    local t; t=$(pick_max_remaining "${PROJECT_DIR}/scripts/missing-subrole-*.txt")
    [ -z "${t:-}" ] && return 1
    SELECTED_STAGE="missing-subrole"; SELECTED_SOURCE="$t"; SELECTED_TARGET="matchups-sub.md"; SELECTED_FORCE=""
    echo "$(log_prefix) INFO: missing-subrole モード ($(basename "$t"), 残 $(wc -l < "$t") 件)"
}
try_requeue_subrole() {
    local t; t=$(pick_max_remaining "${PROJECT_DIR}/scripts/requeue-subrole-*.txt")
    [ -z "${t:-}" ] && return 1
    SELECTED_STAGE="requeue-subrole"; SELECTED_SOURCE="$t"; SELECTED_TARGET="matchups-sub.md"; SELECTED_FORCE="--force"
    echo "$(log_prefix) INFO: requeue-subrole モード ($(basename "$t"), 残 $(wc -l < "$t") 件)"
}

# 実行時刻で枠タイプを決める。FORCE_HOUR で上書き可（dry-run 検証用）。
# 注意: 下の 5|15 は crontab の発火時刻（0,5,10,15,20）のうち subrole に割り当てる2枠。
#       crontab の時刻を変えたらこの case も必ず見直すこと（時刻が両者で二重管理のため修正漏れ注意）。
HOUR=$((10#${FORCE_HOUR:-$(date +%H)}))
case "$HOUR" in
    5|15) SLOT_TYPE="subrole" ;;   # subrole 枠（1日2回）
    *)    SLOT_TYPE="requeue" ;;   # requeue 枠（0,10,20時）
esac

# メインロール missing の残件数。subrole はファイル名でフィルタする。
# NG: `cat missing-*.txt | grep -v subrole` … missing-subrole-*.txt の中身は
#     "subrole" 文字列を含まないため除外されず、subrole キューを誤カウントしていた
#     （2026-05-25 フェーズ4実装で混入、4日間 missing モードに誤判定し生成停止）。
# OK: ファイル名グロブ [!s] で subrole 系を除外（requeue 側の [!s] パターンに統一）。
MISSING_TOTAL=$(cat "${PROJECT_DIR}"/scripts/missing-[!s]*.txt 2>/dev/null | wc -l || true)

SELECTED_STAGE=""
SELECTED_SOURCE=""
SELECTED_TARGET="matchups.md"
SELECTED_FORCE=""

if [ "${MISSING_TOTAL:-0}" -gt 0 ]; then
    # ① missing モード（両枠共通で最優先。新チャンプ等の取りこぼし防止）
    SELECTED_STAGE="missing"
    SELECTED_SOURCE="(scripts/missing-*.txt 自動選択)"
    echo "$(log_prefix) INFO: missing キュー残 ${MISSING_TOTAL} 件、通常モード (${SLOT_TYPE}枠)"
elif [ "$SLOT_TYPE" = "subrole" ]; then
    # subrole 枠（5,15時）: サブロールを requeue より優先して消化する
    echo "$(log_prefix) INFO: missing 空、subrole 枠 → subrole 優先で選択"
    try_missing_subrole || try_requeue_subrole || try_requeue || {
        echo "$(log_prefix) INFO: 全キュー空、処理なし"; exit 0
    }
else
    # requeue 枠（0,10,20時）: メイン再生成を優先（従来の段順）
    echo "$(log_prefix) INFO: missing 空、requeue 枠 → 従来の段順で選択"
    try_requeue || try_missing_subrole || try_requeue_subrole || {
        echo "$(log_prefix) INFO: 全キュー空、処理なし"; exit 0
    }
fi

# DRY_RUN: 判定までで止める。本実行の add-matchups.sh を呼ばない。
if [ "${DRY_RUN}" = "1" ]; then
    echo "$(log_prefix) DRY-RUN: 選択された段=${SELECTED_STAGE} target=${SELECTED_TARGET}"
    echo "$(log_prefix) DRY-RUN:   source=${SELECTED_SOURCE}"
    echo "$(log_prefix) DRY-RUN:   add-matchups.sh は呼ばない（単体 dry-run で確認すること）"
    echo "$(log_prefix) ===== cron-add-matchups 終了（DRY-RUN） ====="
    exit 0
fi

# 本実行: 選択された段で add-matchups.sh を呼ぶ
if [ "$SELECTED_STAGE" = "missing" ]; then
    "${PROJECT_DIR}/scripts/add-matchups.sh" --cost-mode lite --batch 20 --sleep 10 \
        2>&1 | tee /tmp/add-matchups-last.log
elif [ -n "$SELECTED_TARGET" ] && [ "$SELECTED_TARGET" != "matchups.md" ]; then
    "${PROJECT_DIR}/scripts/add-matchups.sh" --cost-mode lite --batch 20 --sleep 10 \
        --source "$SELECTED_SOURCE" --target "$SELECTED_TARGET" ${SELECTED_FORCE} \
        2>&1 | tee /tmp/add-matchups-last.log
else
    "${PROJECT_DIR}/scripts/add-matchups.sh" --cost-mode lite --batch 20 --sleep 10 \
        --source "$SELECTED_SOURCE" ${SELECTED_FORCE} \
        2>&1 | tee /tmp/add-matchups-last.log
fi

echo "$(log_prefix) ===== cron-add-matchups 終了 ====="

# 実行結果を CLAUDE.local.md に記録（CLAUDE.md §セッション管理の通知方針に従う）
# 正常系（失敗=0）は記録しない。~/CLAUDE.local.md は「ユーザーが確認すべきもの」専用のため。
# 詳細なログは /mnt/c/Obsidian/90_Claude作業用/ログ/ 側に蓄積する想定。
SUMMARY=$(grep "完了: 成功=" /tmp/add-matchups-last.log | tail -1 || echo "完了行なし")
if echo "$SUMMARY" | grep -qE "失敗=[1-9]|完了行なし"; then
    echo "- [$(date '+%Y-%m-%d %H:%M')] lol-guides-jp: cron-add-matchups ${SUMMARY}" \
        >> /home/ojita/CLAUDE.local.md
fi
