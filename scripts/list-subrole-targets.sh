#!/bin/bash
# list-subrole-targets.sh
# 全170体のメイン/サブロール判定を Sonnet 4.6 + WebSearch で1回実行し、
# scripts/subrole-targets.json に書き出す。
# パッチ追従（check-patch.sh）から呼ばれる想定だが、手動実行も可能。
#
# 手動実行:
#   ./scripts/list-subrole-targets.sh
#   ./scripts/list-subrole-targets.sh --dry-run
#
# 出力: scripts/subrole-targets.json（git 管理）
# 旧ファイルは scripts/subrole-targets.json.prev にバックアップされる

set -euo pipefail

export NVM_DIR="${HOME}/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[${DATE} $(date +%H:%M:%S)]"
OUTPUT_FILE="${PROJECT_DIR}/scripts/subrole-targets.json"
BACKUP_FILE="${PROJECT_DIR}/scripts/subrole-targets.json.prev"
PATCH_FILE="${PROJECT_DIR}/current-patch.txt"

source "${PROJECT_DIR}/scripts/lib.sh"

# --- ドライランフラグ ---
DRY_RUN=0
for _arg in "$@"; do [ "$_arg" = "--dry-run" ] && DRY_RUN=1; done

cd "$PROJECT_DIR" || { echo "${LOG_PREFIX} ERROR: ディレクトリが見つかりません"; exit 1; }

echo "${LOG_PREFIX} ===== サブロール判定開始 ====="

# --- 現在のパッチを取得 ---
CURRENT_PATCH=$(cat "${PATCH_FILE}" 2>/dev/null | tr -d '[:space:]' || echo "26.10")
echo "${LOG_PREFIX} INFO: 対象パッチ=${CURRENT_PATCH}"

# --- 全チャンプリストを docs/data.json から抽出 ---
# data.json のフィールド: id, en (英語名), ja (日本語名), role, ...
CHAMPIONS_JSON=$(node -e "
const data = require('${PROJECT_DIR}/docs/data.json');
const champions = data.champions.map(c => ({
  id: c.id,
  ja: c.ja || c.name || c.id,
  en: c.en || c.id
}));
process.stdout.write(JSON.stringify(champions));
") || { echo "${LOG_PREFIX} ERROR: data.json からチャンプ抽出失敗"; exit 1; }

CHAMP_COUNT=$(echo "$CHAMPIONS_JSON" | node -e "process.stdout.write(JSON.parse(require('fs').readFileSync(0, 'utf-8')).length.toString())")
echo "${LOG_PREFIX} INFO: 対象チャンプ数=${CHAMP_COUNT}"

if [ "${DRY_RUN}" = "1" ]; then
    echo "${LOG_PREFIX} DRY-RUN: list-subrole-targets コマンドを Sonnet で実行します"
    echo "${LOG_PREFIX} DRY-RUN: 出力先 → ${OUTPUT_FILE}"
    echo "${LOG_PREFIX} DRY-RUN: 推定コスト \$5-10（Sonnet 4.6 + WebSearch 最大3回）"
    echo "${LOG_PREFIX} ===== サブロール判定終了（DRY-RUN） ====="
    exit 0
fi

# --- 入力 JSON を組み立て ---
INPUT_JSON=$(node -e "
const champions = ${CHAMPIONS_JSON};
process.stdout.write(JSON.stringify({champions, patch: '${CURRENT_PATCH}'}));
")

# --- Sonnet 4.6 で実行 ---
echo "${LOG_PREFIX} INFO: list-subrole-targets コマンドを実行中..."
result=$(run_cmd "list-subrole-targets" "$INPUT_JSON") || {
    echo "${LOG_PREFIX} ERROR: list-subrole-targets 実行失敗"
    exit 1
}

if [ -z "$result" ]; then
    echo "${LOG_PREFIX} ERROR: 出力が空"
    exit 1
fi

# --- JSON 検証 ---
echo "$result" | node -e "
const raw = require('fs').readFileSync(0, 'utf-8').trim();
let json;
try { json = JSON.parse(raw); } catch (e) {
  console.error('JSON parse 失敗: ' + e.message);
  console.error('--- raw output (first 500 chars) ---');
  console.error(raw.substring(0, 500));
  process.exit(1);
}
if (!json.champions || typeof json.champions !== 'object') {
  console.error('ERROR: champions フィールドが不正');
  process.exit(1);
}
const count = Object.keys(json.champions).length;
if (count < 100) {
  console.error('ERROR: champions エントリ数が少なすぎる (' + count + ' < 100)');
  process.exit(1);
}
console.error('INFO: ' + count + ' 体のロール判定を取得');
" || { echo "${LOG_PREFIX} ERROR: JSON 検証失敗"; exit 1; }

# --- バックアップ + 書き出し ---
if [ -f "${OUTPUT_FILE}" ]; then
    cp "${OUTPUT_FILE}" "${BACKUP_FILE}"
    echo "${LOG_PREFIX} INFO: 旧ファイルを ${BACKUP_FILE} にバックアップ"
fi

# JSON を整形して書き出し
echo "$result" | node -e "
const raw = require('fs').readFileSync(0, 'utf-8').trim();
const json = JSON.parse(raw);
require('fs').writeFileSync('${OUTPUT_FILE}', JSON.stringify(json, null, 2) + '\n');
"

echo "${LOG_PREFIX} INFO: ${OUTPUT_FILE} に書き出し完了"
echo "${LOG_PREFIX} ===== サブロール判定終了 ====="
