#!/bin/bash
# list-subrole-targets.sh
# 全チャンプのメイン/サブロール判定を「1体ずつ」Sonnet 4.6 + WebSearch で実行し、
# scripts/subrole-targets.json に書き出す。
#
# 旧実装は「170体を1回・検索3回」で判定していたが、170体ぶんの実 pick 率を3検索で
# 取れず、内部知識ベースの誤判定（例: ノクターン/リリアに MID サブが付く）が多発した。
# → gen-matchup.md と同じ「細粒度1単位ごとに専用 WebSearch を割り当てる」方式に統一。
#   各体で judge-subrole コマンドが pick 率のレーン内訳を読み、15% 閾値で main/sub を判定する。
#
# パッチ追従（check-patch.sh / refresh-subrole-targets.py）から呼ばれる想定だが手動実行も可。
#
# 手動実行:
#   ./scripts/list-subrole-targets.sh                 # 全体フル判定（≈170体ぶんの API 消化）
#   ./scripts/list-subrole-targets.sh --dry-run       # API を叩かず計画とコスト概算のみ表示
#   ./scripts/list-subrole-targets.sh --limit 3       # 先頭3体だけ実判定（パイプライン疎通テスト用）
#
# 出力: scripts/subrole-targets.json（git 管理）
# 旧ファイルは scripts/subrole-targets.json.prev にバックアップされる

set -euo pipefail

export NVM_DIR="${HOME}/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
SCRIPTS_DIR="${PROJECT_DIR}/scripts"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[${DATE} $(date +%H:%M:%S)]"
OUTPUT_FILE="${SCRIPTS_DIR}/subrole-targets.json"
BACKUP_FILE="${SCRIPTS_DIR}/subrole-targets.json.prev"
PATCH_FILE="${PROJECT_DIR}/current-patch.txt"

source "${PROJECT_DIR}/scripts/lib.sh"

# --- フラグ ---
DRY_RUN=0
LIMIT=0
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --limit) LIMIT="${2:-0}"; shift 2 ;;
        *) echo "${LOG_PREFIX} WARN: 未知の引数 '$1' を無視"; shift ;;
    esac
done

cd "$PROJECT_DIR" || { echo "${LOG_PREFIX} ERROR: ディレクトリが見つかりません"; exit 1; }

echo "${LOG_PREFIX} ===== サブロール判定開始（1体ループ方式） ====="

# --- 現在のパッチ ---
CURRENT_PATCH=$(tr -d '[:space:]' < "${PATCH_FILE}" 2>/dev/null || echo "26.11")
echo "${LOG_PREFIX} INFO: 対象パッチ=${CURRENT_PATCH}"

# --- 全チャンプを data.json から抽出（id/ja/en + role はフォールバック用） ---
TMP_DIR=$(mktemp -d)
trap 'rm -rf "${TMP_DIR}"' EXIT
CHAMPS_JSONL="${TMP_DIR}/champs.jsonl"

node -e "
const data = require('${PROJECT_DIR}/docs/data.json');
const out = data.champions.map(c => ({ id: c.id, ja: c.ja || c.name || c.id, en: c.en || c.id, role: c.role || c.mainRole }));
process.stdout.write(out.map(o => JSON.stringify(o)).join('\n') + '\n');
" > "${CHAMPS_JSONL}" || { echo "${LOG_PREFIX} ERROR: data.json からチャンプ抽出失敗"; exit 1; }

TOTAL=$(wc -l < "${CHAMPS_JSONL}" | tr -d ' ')
echo "${LOG_PREFIX} INFO: 対象チャンプ数=${TOTAL}"

# --- ドライラン ---
if [ "${DRY_RUN}" = "1" ]; then
    echo "${LOG_PREFIX} DRY-RUN: judge-subrole を ${TOTAL} 体ぶん Sonnet 4.6 で実行する想定"
    echo "${LOG_PREFIX} DRY-RUN: 1体あたり WebSearch 最大3回。推定コスト ≈ \$0.2/体 → 全体 ≈ \$$(awk "BEGIN{printf \"%.0f\", ${TOTAL}*0.2}")"
    echo "${LOG_PREFIX} DRY-RUN: 出力先 → ${OUTPUT_FILE}"
    echo "${LOG_PREFIX} DRY-RUN: 疎通だけ見るなら --limit 3 で先頭3体を実判定できる"
    echo "${LOG_PREFIX} ===== サブロール判定終了（DRY-RUN） ====="
    exit 0
fi

# --- 1体ずつ判定 ---
RESULTS_JSONL="${TMP_DIR}/results.jsonl"
: > "${RESULTS_JSONL}"
success=0; fallback=0; idx=0

while IFS= read -r champ_line || [ -n "$champ_line" ]; do
    [ -z "$champ_line" ] && continue
    idx=$((idx + 1))
    if [ "${LIMIT}" -gt 0 ] && [ "${idx}" -gt "${LIMIT}" ]; then
        echo "${LOG_PREFIX} INFO: --limit ${LIMIT} に到達、打ち切り"
        break
    fi

    cid=$(printf '%s' "$champ_line" | node -e "process.stdout.write(JSON.parse(require('fs').readFileSync(0,'utf-8')).id)")
    input=$(node -e "
      const c = JSON.parse(process.argv[1]);
      process.stdout.write(JSON.stringify({ champ: { id: c.id, ja: c.ja, en: c.en }, patch: process.argv[2] }));
    " "$champ_line" "$CURRENT_PATCH")

    echo "${LOG_PREFIX} INFO: [${idx}/${TOTAL}] ${cid} 判定中..."
    # run_cmd 失敗（API エラー等）でもループは止めない。normalize 側でフォールバックする。
    result=$(run_cmd "judge-subrole" "$input") || result=""

    # 生出力 → 正規エントリ1行を RESULTS_JSONL に追記。OK/FALLBACK は stderr から拾って集計。
    status_file="${TMP_DIR}/status.txt"
    printf '%s' "$result" \
        | node "${SCRIPTS_DIR}/normalize-subrole-result.js" "$champ_line" \
        >> "${RESULTS_JSONL}" 2> "${status_file}"
    last_status=$(head -1 "${status_file}" 2>/dev/null || true)
    case "$last_status" in
        OK*) success=$((success + 1)) ;;
        *) fallback=$((fallback + 1)); echo "${LOG_PREFIX} WARN: ${cid} フォールバック（${last_status}）" ;;
    esac
done < "${CHAMPS_JSONL}"

echo "${LOG_PREFIX} INFO: 判定完了 成功=${success} フォールバック=${fallback}"

# --- 集約して書き出し（バックアップ付き） ---
MIN_COUNT=100
[ "${LIMIT}" -gt 0 ] && MIN_COUNT="${LIMIT}"

if [ -f "${OUTPUT_FILE}" ]; then
    cp "${OUTPUT_FILE}" "${BACKUP_FILE}"
    echo "${LOG_PREFIX} INFO: 旧ファイルを ${BACKUP_FILE} にバックアップ"
fi

node "${SCRIPTS_DIR}/assemble-subrole-targets.js" \
    "${RESULTS_JSONL}" "${CURRENT_PATCH}" "${OUTPUT_FILE}" "${MIN_COUNT}" \
    || { echo "${LOG_PREFIX} ERROR: 集約失敗（subrole-targets.json は更新しない）"; exit 1; }

echo "${LOG_PREFIX} INFO: ${OUTPUT_FILE} に書き出し完了"
echo "${LOG_PREFIX} ===== サブロール判定終了 ====="
