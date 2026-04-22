#!/bin/bash
# check-patch.sh
# 毎週月曜4時: パッチバージョンを確認し、更新があればガイドを自動更新する
# 複数パッチをスキップした場合は順番に処理し、matchupは重複排除して1回だけキューに追加する
#
# cron登録:
#   0 4 * * 1 /home/ojita/lol-guides-jp/scripts/check-patch.sh >> /home/ojita/lol-guides-jp/scripts/cron.log 2>&1
#
# 手動実行（ドライラン）:
#   ./scripts/check-patch.sh --dry-run

set -euo pipefail

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
DATE=$(date +%Y-%m-%d)
log_prefix() { echo "[$(date '+%Y-%m-%d %H:%M:%S')]"; }
PATCH_FILE="${PROJECT_DIR}/current-patch.txt"
CLAUDE_LOCAL="/home/ojita/CLAUDE.local.md"

source "${PROJECT_DIR}/scripts/lib.sh"

# --- ドライランフラグ ---
DRY_RUN=0
for _arg in "$@"; do [ "$_arg" = "--dry-run" ] && DRY_RUN=1; done
export DRY_RUN

# --- 失敗通知（CLAUDE.local.md への追記） ---
notify_failure() {
    local reason="$1"
    echo "$(log_prefix) ERROR: ${reason}"
    echo "⚠️ ${DATE}: lol-guides-jp check-patch.sh 失敗（${reason}）" >> "${CLAUDE_LOCAL}"
}

cd "$PROJECT_DIR" || { echo "$(log_prefix) ERROR: ディレクトリが見つかりません"; exit 1; }

echo "$(log_prefix) ===== パッチチェック開始 ====="

# --- 最新パッチバージョンを取得（L1: Python stdlib、公式ニュースページから抽出） ---
LATEST=$(python3 - <<'PYEOF'
import urllib.request, re, sys
try:
    req = urllib.request.Request(
        "https://www.leagueoflegends.com/en-us/news/game-updates/",
        headers={"User-Agent": "Mozilla/5.0 (compatible; patch-checker/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", errors="ignore")
    matches = re.findall(r'patch-(\d+)-(\d+)-notes', html)
    if not matches:
        raise ValueError("パッチノートリンクが見つかりません")
    major, minor = max((int(m), int(n)) for m, n in matches)
    print(f"{major}.{minor}")
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
) || {
    notify_failure "最新パッチバージョン取得失敗"
    exit 1
}

echo "$(log_prefix) INFO: 最新パッチ=${LATEST}"

# --- 既知パッチと比較 ---
CURRENT=$(cat "${PATCH_FILE}" 2>/dev/null | tr -d '[:space:]' || echo "")

if [ "${LATEST}" = "${CURRENT}" ]; then
    echo "$(log_prefix) INFO: パッチ変更なし（${CURRENT}）。終了"
    echo "$(log_prefix) ===== パッチチェック完了 ====="
    exit 0
fi

echo "$(log_prefix) INFO: 新パッチ検出: ${CURRENT} → ${LATEST}"

# --- 処理対象パッチ一覧を生成（CURRENT+1 〜 LATEST、同一メジャーのみ対応） ---
CUR_MAJOR=$(echo "${CURRENT}" | cut -d. -f1)
CUR_MINOR=$(echo "${CURRENT}" | cut -d. -f2)
LAT_MAJOR=$(echo "${LATEST}" | cut -d. -f1)
LAT_MINOR=$(echo "${LATEST}" | cut -d. -f2)

if [ "${CUR_MAJOR}" != "${LAT_MAJOR}" ]; then
    notify_failure "メジャーバージョンが変わりました（${CURRENT}→${LATEST}）。手動対応が必要です"
    exit 1
fi

MISSED_PATCHES=()
for minor in $(seq $((CUR_MINOR + 1)) "${LAT_MINOR}"); do
    MISSED_PATCHES+=("${CUR_MAJOR}.${minor}")
done

echo "$(log_prefix) INFO: 処理対象パッチ: ${MISSED_PATCHES[*]}"

if [ "${DRY_RUN}" = "1" ]; then
    echo "$(log_prefix) DRY-RUN: 以下の処理をスキップします:"
    for patch in "${MISSED_PATCHES[@]}"; do
        echo "$(log_prefix)   - fetch-patch-notes.py ${patch}"
        echo "$(log_prefix)   - update-guides (patches/${patch}.md)"
    done
    echo "$(log_prefix)   - update-patch-version.py → パッチ${LATEST}"
    echo "$(log_prefix)   - requeue-patched-matchups.py ${MISSED_PATCHES[*]}"
    echo "$(log_prefix)   - build-json.js"
    echo "$(log_prefix)   - current-patch.txt を ${LATEST} に更新"
    echo "$(log_prefix)   - auto_commit: patches/ champions/ docs/data.json current-patch.txt"
    echo "$(log_prefix)   - auto_push"
    echo "$(log_prefix) ===== パッチチェック完了（DRY-RUN） ====="
    exit 0
fi

# --- 各パッチを順番に処理 ---
for PATCH in "${MISSED_PATCHES[@]}"; do
    echo "$(log_prefix) INFO: ===== パッチ${PATCH} 処理開始 ====="

    # パッチノート取得
    echo "$(log_prefix) INFO: パッチノート取得中（${PATCH}）..."
    if ! python3 "${PROJECT_DIR}/scripts/fetch-patch-notes.py" "${PATCH}"; then
        notify_failure "fetch-patch-notes.py 失敗（パッチ${PATCH}）"
        exit 1
    fi
    if [ ! -f "${PROJECT_DIR}/patches/${PATCH}.md" ]; then
        notify_failure "patches/${PATCH}.md が生成されていない"
        exit 1
    fi

    # ガイド更新（L3: Claude）
    echo "$(log_prefix) INFO: ガイド更新中（${PATCH}）..."
    json=$(run_cmd "update-guides") || { notify_failure "update-guides 失敗（パッチ${PATCH}）"; exit 1; }
    if [ -z "$json" ]; then
        notify_failure "update-guides 結果が空（パッチ${PATCH}）"
        exit 1
    fi
    dispatch_ops "$json" || { notify_failure "update-guides dispatch_ops 失敗（パッチ${PATCH}）"; exit 1; }

    echo "$(log_prefix) INFO: ===== パッチ${PATCH} ガイド更新完了 ====="
done

# --- 全ページのパッチバージョン表記を最新に一括更新（L1） ---
echo "$(log_prefix) INFO: パッチバージョン表記を パッチ${LATEST} に更新中..."
python3 "${PROJECT_DIR}/scripts/update-patch-version.py" "${LATEST}" || \
    notify_failure "update-patch-version.py 失敗（パッチ${LATEST}）"

# --- data.json 再ビルド ---
echo "$(log_prefix) INFO: data.json 再ビルド中..."
node "${PROJECT_DIR}/scripts/build-json.js" || \
    notify_failure "build-json.js 失敗（パッチ${LATEST}）"

# --- matchup再キュー（全対象パッチをまとめて重複排除し先頭に追加） ---
echo "$(log_prefix) INFO: matchup再キュー中（${MISSED_PATCHES[*]}）..."
python3 "${PROJECT_DIR}/scripts/requeue-patched-matchups.py" "${MISSED_PATCHES[@]}" || \
    notify_failure "requeue-patched-matchups.py 失敗"

# --- パッチバージョンを更新 ---
echo "${LATEST}" > "${PATCH_FILE}"
echo "$(log_prefix) INFO: current-patch.txt を ${LATEST} に更新"

# --- git commit + push（auto_commit 経由で明示パスのみ stage） ---
# coding-standards.md §8 に従い `git add .` は使わない。
# 変更対象: パッチノート・champions/ ガイド・data.json・current-patch.txt
# （scripts/missing-*.txt は gitignored のため含めない）
auto_commit patches champions docs/data.json current-patch.txt \
    -- "feat: パッチ${LATEST} ガイド更新 (自動)"
auto_push || { notify_failure "push 失敗（パッチ${LATEST}）"; exit 1; }

# CLAUDE.local.md に成功通知
# 過去の check-patch 関連の失敗/成功通知を掃除してから新しい成功通知を付ける。
# notify_failure は "⚠️ <日付>: lol-guides-jp <何か> 失敗" 形式で append するが、
# reason 文字列の組み立てによってはパイプ内のスクリプト名（fetch-patch-notes.py 等）が
# 行の主語になる場合があるため、check-patch / fetch-patch-notes / update-patch-version /
# update-guides を一括で掃除対象にする。
# 過去成功通知（"- <日付> lol-guides-jp: パッチX.Y ガイド更新完了"）も重複回避のため掃除。
grep -vE "lol-guides-jp (check-patch|fetch-patch-notes|update-patch-version|update-guides)|lol-guides-jp: パッチ.+ ガイド更新完了" \
    "${CLAUDE_LOCAL}" > "${CLAUDE_LOCAL}.tmp" && mv "${CLAUDE_LOCAL}.tmp" "${CLAUDE_LOCAL}" || true
echo "- ${DATE} lol-guides-jp: パッチ${LATEST} ガイド更新完了 → lol-guides-jp/champions/ を確認" >> "${CLAUDE_LOCAL}"

echo "$(log_prefix) ===== パッチチェック完了 ====="
