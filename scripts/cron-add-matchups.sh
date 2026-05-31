#!/bin/bash
# cron-add-matchups.sh
# 5時間ごと（1日5回）対面ガイドを自動追加する（batch=20, 案B Sonnet 4.6 + WebSearch, lite モード）
# missing-*.txt が空になったら自動的に requeue-*.txt（残数最多のロール）に切替。
#
# cron登録:
#   0 0,5,10,15,20 * * * bash /home/ojita/lol-guides-jp/scripts/cron-add-matchups.sh >> /home/ojita/lol-guides-jp/scripts/cron.log 2>&1

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
# subrole 系は matchups-sub.md に書き込むため、add-matchups.sh に --target を指定する
# （Phase C-3 で add-matchups.sh 側に --target サポートを追加予定）
#
# 「残数最多のロール」を毎回選ぶラウンドロビン: requeue / requeue-subrole 系で使う
pick_max_remaining() {
    local pattern="$1"
    for f in $pattern; do
        [ -f "$f" ] && [ -s "$f" ] && echo "$(wc -l < "$f") $f"
    done | sort -rn | head -1 | awk '{print $2}'
}

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
    # ① missing モード（既存）
    SELECTED_STAGE="missing"
    SELECTED_SOURCE="(scripts/missing-*.txt 自動選択)"
    echo "$(log_prefix) INFO: missing キュー残 ${MISSING_TOTAL} 件、通常モード"
else
    # ② requeue モード（メインロール対面の再生成）
    REQUEUE_TARGET=$(pick_max_remaining "${PROJECT_DIR}/scripts/requeue-[!s]*.txt")
    if [ -n "${REQUEUE_TARGET:-}" ]; then
        REQUEUE_REMAIN=$(wc -l < "$REQUEUE_TARGET")
        SELECTED_STAGE="requeue"
        SELECTED_SOURCE="$REQUEUE_TARGET"
        SELECTED_FORCE="--force"
        echo "$(log_prefix) INFO: missing 空、requeue モード ($(basename "$REQUEUE_TARGET"), 残 ${REQUEUE_REMAIN} 件)"
    else
        # ③ missing-subrole モード（サブロール対面の新規生成）
        MISSING_SUB_TARGET=$(pick_max_remaining "${PROJECT_DIR}/scripts/missing-subrole-*.txt")
        if [ -n "${MISSING_SUB_TARGET:-}" ]; then
            MISSING_SUB_REMAIN=$(wc -l < "$MISSING_SUB_TARGET")
            SELECTED_STAGE="missing-subrole"
            SELECTED_SOURCE="$MISSING_SUB_TARGET"
            SELECTED_TARGET="matchups-sub.md"
            echo "$(log_prefix) INFO: missing/requeue 空、missing-subrole モード ($(basename "$MISSING_SUB_TARGET"), 残 ${MISSING_SUB_REMAIN} 件)"
        else
            # ④ requeue-subrole モード（サブロール対面の再生成）
            REQUEUE_SUB_TARGET=$(pick_max_remaining "${PROJECT_DIR}/scripts/requeue-subrole-*.txt")
            if [ -n "${REQUEUE_SUB_TARGET:-}" ]; then
                REQUEUE_SUB_REMAIN=$(wc -l < "$REQUEUE_SUB_TARGET")
                SELECTED_STAGE="requeue-subrole"
                SELECTED_SOURCE="$REQUEUE_SUB_TARGET"
                SELECTED_TARGET="matchups-sub.md"
                SELECTED_FORCE="--force"
                echo "$(log_prefix) INFO: 全 missing/requeue 空、requeue-subrole モード ($(basename "$REQUEUE_SUB_TARGET"), 残 ${REQUEUE_SUB_REMAIN} 件)"
            else
                echo "$(log_prefix) INFO: 全キュー（missing/requeue/missing-subrole/requeue-subrole）空、処理なし"
                exit 0
            fi
        fi
    fi
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
