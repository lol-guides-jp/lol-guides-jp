#!/bin/bash
# review-guide.sh
# guide.md の品質レビューを1体ずつ Sonnet で実施し、修正版で書き換える
#
# 使い方:
#   ./scripts/review-guide.sh [--count N] [--dry-run]
#
# cron登録（例: 毎日3時に2体）:
#   0 3 * * * bash /home/ojita/lol-guides-jp/scripts/review-guide.sh --count 2 >> /home/ojita/lol-guides-jp/scripts/cron.log 2>&1
#
# 設計メモ:
#   - 対象選定: list-guide-review-targets.py（直近パッチ変更チャンプ優先）
#   - レビュー: .claude/commands/review-guide.md（Sonnet）
#   - 結果反映: approved → guide.md 上書き / no_change → 履歴更新のみ / rejected → CLAUDE.local.md 通知

set -euo pipefail

export NVM_DIR="${HOME}/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="${HOME}/lol-guides-jp"
HISTORY_FILE="${PROJECT_DIR}/scripts/review-history.json"
CLAUDE_LOCAL="${HOME}/CLAUDE.local.md"
log_prefix() { echo "[$(date '+%Y-%m-%d %H:%M:%S')]"; }

source "${PROJECT_DIR}/scripts/lib.sh"

# --- 引数解析 ---
COUNT=2
DRY_RUN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --count)   COUNT="$2";  shift 2 ;;
        --dry-run) DRY_RUN=1;   shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

cd "$PROJECT_DIR"
echo "$(log_prefix) ===== review-guide 開始 (count=${COUNT}, dry-run=${DRY_RUN}) ====="

# --- 終了時処理 ---
PROCESSED=0
NO_CHANGE=0
REJECTED=0
FAILED=0
_finalize() {
    echo "$(log_prefix) ===== 完了: 修正=${PROCESSED} 無変更=${NO_CHANGE} 却下=${REJECTED} 失敗=${FAILED} ====="
    [ "${DRY_RUN}" = "1" ] && return 0

    local handled=$((PROCESSED + NO_CHANGE + REJECTED))
    [ "${handled}" -gt 0 ] || return 0

    # guide.md 修正があれば fix:、なければ履歴のみで chore:
    if [ "${PROCESSED}" -gt 0 ]; then
        auto_commit champions/*/guide.md scripts/review-history.json \
            -- "fix: guide.md ${PROCESSED}件 品質レビュー反映 (自動)"
    else
        auto_commit scripts/review-history.json \
            -- "chore: review-history.json 更新 (修正なし) (自動)"
    fi
    auto_push || echo "$(log_prefix) WARN: push 失敗（trap EXIT 内のため継続）"
}
trap '_finalize' EXIT

# --- 対象選定 ---
TARGETS=()
while IFS= read -r line; do
    [ -z "$line" ] && continue
    TARGETS+=("$line")
done < <(python3 "${PROJECT_DIR}/scripts/list-guide-review-targets.py" --count "${COUNT}")

if [ "${#TARGETS[@]}" -eq 0 ]; then
    echo "$(log_prefix) INFO: 対象なし。終了"
    exit 0
fi

echo "$(log_prefix) INFO: 対象 ${#TARGETS[@]}件: ${TARGETS[*]}"

# --- 各チャンプを処理 ---
for champ_id in "${TARGETS[@]}"; do
    echo "$(log_prefix) INFO: ${champ_id} レビュー中..."

    guide_file="${PROJECT_DIR}/champions/${champ_id}/guide.md"
    if [ ! -f "${guide_file}" ]; then
        echo "$(log_prefix) WARN: ${guide_file} が存在しない。スキップ"
        FAILED=$((FAILED + 1))
        continue
    fi

    # data.json（14MB・matchups 全文込み）から該当チャンプの正規データだけ /tmp に抽出する。
    # review-guide.md にはこの slim ファイルを読ませ、AI に 14MB を読ませる無駄を消す（2026-05-30）。
    # data.json 本体は無変更なので SPA・build-json・他スクリプトには影響しない。
    slim_data="/tmp/review-data-${champ_id}.json"
    rm -f "${slim_data}"
    python3 - "${champ_id}" "${slim_data}" << 'PYEOF' || true
import json, sys
champ_id, out_path = sys.argv[1], sys.argv[2]
data = json.load(open("docs/data.json", encoding="utf-8"))
c = next((x for x in data["champions"] if x["id"] == champ_id), None)
if c is None:
    sys.exit(1)
keys = ["id", "en", "ja", "ddragonKey", "role", "skills"]
slim = {k: c[k] for k in keys if k in c}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(slim, f, ensure_ascii=False, indent=2)
PYEOF
    if [ ! -f "${slim_data}" ]; then
        echo "$(log_prefix) ERROR: ${champ_id} データ抽出失敗（data.json に存在しない？）"
        FAILED=$((FAILED + 1))
        continue
    fi

    if [ "${DRY_RUN}" = "1" ]; then
        echo "$(log_prefix) [DRY-RUN] ${champ_id}: slim抽出OK ($(wc -m < "${slim_data}")文字)。Sonnet 呼び出しはスキップ"
        continue
    fi

    # Sonnet レビュー実行（run_cmd の第2引数が $ARGUMENTS に展開される）
    json=$(run_cmd "review-guide" "${champ_id}") || {
        echo "$(log_prefix) ERROR: ${champ_id} review-guide 呼び出し失敗"
        FAILED=$((FAILED + 1))
        continue
    }

    # status を抽出
    status=$(echo "$json" | python3 -c "import sys, json; d=json.loads(sys.stdin.read()); print(d.get('status', ''))" 2>/dev/null || echo "")

    case "$status" in
        approved)
            new_md=$(echo "$json" | python3 -c "import sys, json; d=json.loads(sys.stdin.read()); print(d.get('guide_md', ''))")
            if [ -z "$new_md" ]; then
                echo "$(log_prefix) ERROR: ${champ_id} approved だが guide_md が空"
                FAILED=$((FAILED + 1))
                continue
            fi
            echo "$new_md" > "${guide_file}"
            echo "$(log_prefix) OK: ${champ_id} 修正適用"
            PROCESSED=$((PROCESSED + 1))
            ;;
        no_change)
            echo "$(log_prefix) INFO: ${champ_id} 修正不要"
            NO_CHANGE=$((NO_CHANGE + 1))
            ;;
        rejected)
            reason=$(echo "$json" | python3 -c "import sys, json; d=json.loads(sys.stdin.read()); print(d.get('reason', ''))")
            echo "$(log_prefix) WARN: ${champ_id} rejected: ${reason}"
            REJECTED=$((REJECTED + 1))
            # 人手レビュー候補として通知
            echo "- [$(date +%Y-%m-%d)] lol-guides-jp: ${champ_id}/guide.md レビュー却下 - ${reason}" >> "${CLAUDE_LOCAL}"
            ;;
        *)
            echo "$(log_prefix) ERROR: ${champ_id} 不明な status: ${status}"
            FAILED=$((FAILED + 1))
            continue
            ;;
    esac

    # review-history.json を更新
    python3 - << PYEOF
import json
from pathlib import Path
from datetime import date

hist_file = Path("${HISTORY_FILE}")
hist = json.loads(hist_file.read_text(encoding="utf-8")) if hist_file.exists() else {}
prev = hist.get("${champ_id}", {})
hist["${champ_id}"] = {
    "last_reviewed": date.today().isoformat(),
    "review_count": prev.get("review_count", 0) + 1,
    "last_status": "${status}",
}
hist_file.write_text(json.dumps(hist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PYEOF
done
