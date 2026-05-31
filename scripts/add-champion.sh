#!/bin/bash
# add-champion.sh
# Data Dragon で新規チャンピオンを検出し、登録〜公開までを自動化する。
#   1. check-new-champions.py で未登録チャンプを検出
#   2. ddragon-keys.json に登録 → gen-guide で guide.md 生成
#   3. build-json.js で data.json 再ビルド（新チャンを反映）
#   4. gen-champion-queue.py で同ロール対面を missing-{role}.txt に投入（cron が最優先消化）
#   5. auto_commit / auto_push
#
# 新規がなければ何もせず正常終了（冪等）。check-patch.sh（日次cron）から呼ばれる想定。
# 単体実行・ドライランも可。
#
# 手動実行（ドライラン）:
#   ./scripts/add-champion.sh --dry-run

set -euo pipefail

export NVM_DIR="${HOME}/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
DATE=$(date +%Y-%m-%d)
log_prefix() { echo "[$(date '+%Y-%m-%d %H:%M:%S')]"; }
PATCH_FILE="${PROJECT_DIR}/current-patch.txt"
CLAUDE_LOCAL="${HOME}/CLAUDE.local.md"

source "${PROJECT_DIR}/scripts/lib.sh"

# --- ドライランフラグ（DRY_RUN は export しない: run_cmd の挙動を変えないため）---
DRY_RUN=0
for _arg in "$@"; do [ "$_arg" = "--dry-run" ] && DRY_RUN=1; done

cd "$PROJECT_DIR" || { echo "$(log_prefix) ERROR: ディレクトリが見つかりません"; exit 1; }

notify_failure() {
    local reason="$1"
    echo "$(log_prefix) ERROR: ${reason}"
    echo "⚠️ ${DATE}: lol-guides-jp add-champion.sh 失敗（${reason}）" >> "${CLAUDE_LOCAL}"
}

echo "$(log_prefix) ===== 新規チャンピオン検出開始 ====="

# --- 1. 新規検出 ---
NEW_JSON=$(python3 "${PROJECT_DIR}/scripts/check-new-champions.py") \
    || { notify_failure "check-new-champions.py 失敗"; exit 1; }
NEW_COUNT=$(echo "$NEW_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")

if [ "$NEW_COUNT" = "0" ]; then
    echo "$(log_prefix) INFO: 新規チャンピオンなし。終了"
    echo "$(log_prefix) ===== 新規チャンピオン検出完了 ====="
    exit 0
fi

echo "$(log_prefix) INFO: 新規 ${NEW_COUNT}体検出"

PATCH=$(tr -d '[:space:]' < "${PATCH_FILE}" 2>/dev/null || echo "")
[ -z "$PATCH" ] && PATCH="26.11"

# フィールド取り出しヘルパー（NEW_JSON の i 番目の key を返す）
get_field() {
    echo "$NEW_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)[$1]['$2'])"
}

# --- ドライラン: 検出結果と処理計画のみ表示 ---
if [ "$DRY_RUN" = "1" ]; then
    echo "$(log_prefix) DRY-RUN: 以下を処理予定（実行はしない）:"
    for i in $(seq 0 $((NEW_COUNT - 1))); do
        c_id=$(get_field "$i" id)
        c_ja=$(get_field "$i" ja)
        c_key=$(get_field "$i" ddragonKey)
        c_tags=$(echo "$NEW_JSON" | python3 -c "import sys,json; print('/'.join(json.load(sys.stdin)[$i]['tags']))")
        echo "$(log_prefix)   - ${c_id}（${c_ja}）ddragonKey=${c_key} tags=${c_tags}"
        echo "$(log_prefix)       → ddragon-keys.json 登録 / gen-guide で guide.md 生成（roleはgen-guideが判定）"
        echo "$(log_prefix)       → build-json.js 再ビルド / 同ロール対面を missing-{role}.txt に投入"
    done
    echo "$(log_prefix)   → auto_commit: scripts/ddragon-keys.json champions/<slug>/guide.md docs/data.json"
    echo "$(log_prefix)   → auto_push"
    echo "$(log_prefix) ===== 新規チャンピオン検出完了（DRY-RUN） ====="
    exit 0
fi

# --- 2. 各新規チャンプ: ddragon-keys 登録 + gen-guide + guide.md 書き込み ---
SUCCEEDED_SLUGS=()   # キュー投入・コミット対象（guide生成成功分）
ADDED_NAMES=()

for i in $(seq 0 $((NEW_COUNT - 1))); do
    c_id=$(get_field "$i" id)
    c_ja=$(get_field "$i" ja)
    c_key=$(get_field "$i" ddragonKey)

    echo "$(log_prefix) INFO: ===== ${c_id}（${c_ja}）処理開始 ====="

    # 2a. ddragon-keys.json に登録（ソート維持・末尾改行付与・冪等）
    SLUG="$c_id" KEY="$c_key" python3 - <<'PYEOF' || { notify_failure "ddragon-keys 登録失敗（${c_id}）"; continue; }
import json, os
f = "scripts/ddragon-keys.json"
d = json.load(open(f, encoding="utf-8"))
d[os.environ["SLUG"]] = os.environ["KEY"]
d = dict(sorted(d.items()))
with open(f, "w", encoding="utf-8") as fh:
    json.dump(d, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
PYEOF
    echo "$(log_prefix) INFO: ddragon-keys.json に ${c_id} -> ${c_key} を登録"

    # 2b. gen-guide 入力 JSON を生成（特殊文字を含むので python で安全に組む）
    gen_input=$(echo "$NEW_JSON" | python3 -c "
import sys, json
c = json.load(sys.stdin)[$i]
print(json.dumps({'id': c['id'], 'ja': c['ja'], 'en': c['en'],
                  'skills': c['skills'], 'patch': '${PATCH}'}, ensure_ascii=False))
")

    # 2c. gen-guide 実行（L3: Sonnet + WebSearch）
    echo "$(log_prefix) INFO: gen-guide 実行中（${c_id}）..."
    gen_result=$(run_cmd "gen-guide" "$gen_input") \
        || { notify_failure "gen-guide 失敗（${c_id}）"; continue; }
    if [ -z "$gen_result" ]; then
        notify_failure "gen-guide 結果が空（${c_id}）"
        continue
    fi

    # 2d. guide.md 書き込み（role を受け取る）
    role=$(echo "$gen_result" | python3 "${PROJECT_DIR}/scripts/write-guide.py" "$c_id") \
        || { notify_failure "write-guide.py 失敗（${c_id}）"; continue; }

    echo "$(log_prefix) INFO: ${c_id} guide.md 生成完了（role=${role}）"
    SUCCEEDED_SLUGS+=("$c_id")
    ADDED_NAMES+=("$c_ja")
done

if [ ${#SUCCEEDED_SLUGS[@]} -eq 0 ]; then
    notify_failure "guide 生成が全て失敗。コミットせず終了"
    exit 1
fi

# --- 3. data.json 再ビルド（新チャンを反映。キュー生成が data.json を参照するため先に実行）---
echo "$(log_prefix) INFO: data.json 再ビルド中..."
node "${PROJECT_DIR}/scripts/build-json.js" \
    || { notify_failure "build-json.js 失敗"; exit 1; }

# --- 4. 対面キュー投入（同ロール全チャンプ。新チャン同士も data.json 反映後なので拾える）---
TOTAL_PAIRS=0
for slug in "${SUCCEEDED_SLUGS[@]}"; do
    added=$(python3 "${PROJECT_DIR}/scripts/gen-champion-queue.py" "$slug") \
        || { notify_failure "gen-champion-queue.py 失敗（${slug}）"; continue; }
    TOTAL_PAIRS=$((TOTAL_PAIRS + ${added:-0}))
done
echo "$(log_prefix) INFO: 対面キュー投入 合計 ${TOTAL_PAIRS}件（missing-*.txt、cron が最優先消化）"

# --- 5. commit + push（明示パスのみ stage。missing-*.txt は gitignored のため含めない）---
COMMIT_PATHS=("scripts/ddragon-keys.json" "docs/data.json")
for slug in "${SUCCEEDED_SLUGS[@]}"; do
    COMMIT_PATHS+=("champions/${slug}/guide.md")
done

auto_commit "${COMMIT_PATHS[@]}" \
    -- "feat: 新チャンピオン ${ADDED_NAMES[*]} 追加（guide生成・対面キュー投入）(自動生成)"
auto_push || { notify_failure "push 失敗"; exit 1; }

# --- 6. CLAUDE.local.md に成功通知（古い add-champion 通知を掃除してから付ける）---
grep -vE "lol-guides-jp add-champion" "${CLAUDE_LOCAL}" > "${CLAUDE_LOCAL}.tmp" \
    && mv "${CLAUDE_LOCAL}.tmp" "${CLAUDE_LOCAL}" || true
echo "- ${DATE} lol-guides-jp: 新チャンピオン ${ADDED_NAMES[*]} 追加。対面${TOTAL_PAIRS}件をキュー投入（cron消化待ち）→ champions/ を確認" >> "${CLAUDE_LOCAL}"

echo "$(log_prefix) ===== 新規チャンピオン追加完了（${#SUCCEEDED_SLUGS[@]}体）====="
