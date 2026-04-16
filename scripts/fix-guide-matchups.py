#!/usr/bin/env python3
"""fix-guide-matchups.py
guide.md の 得意マッチアップ / 苦手マッチアップ セクションを
matchups.md の verdict に基づいて再構築する（API不要・$0）。

使い方:
  python3 scripts/fix-guide-matchups.py              # Q4矛盾チャンプを全件修正
  python3 scripts/fix-guide-matchups.py urgot        # 単一チャンプ指定
  python3 scripts/fix-guide-matchups.py --all        # 全チャンプを対象
  python3 scripts/fix-guide-matchups.py --dry-run    # ドライラン（変更を表示のみ）

ルール:
  - 有利 / やや有利 → 得意マッチアップ（スコア降順 top TOP_N 件）
  - 不利 / やや不利 → 苦手マッチアップ（スコア昇順 top TOP_N 件）
  - 説明文: 得意=verdict_reason、苦手=注意ポイント（なければverdict_reason）
"""

import os, re, json, sys
from collections import defaultdict

CHAMP_DIR = os.path.join(os.path.dirname(__file__), "..", "champions")
DATA_FILE  = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")
MECHANICS_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "champion-mechanics.json")

TOP_N = 4  # 得意/苦手それぞれ上位何件を掲載するか

DATA = json.load(open(DATA_FILE, encoding="utf-8"))
ja_to_id = {c["ja"]: c["id"] for c in DATA["champions"]}
en_to_id = {c["en"]: c["id"] for c in DATA["champions"]}

VERDICT_SCORE = {"有利": 2, "やや有利": 1, "五分": 0, "やや不利": -1, "不利": -2}

# ============================================================
# matchups.md パーサー
# ============================================================

def parse_matchups(champ_id):
    """matchups.md から {opp_ja: {verdict, score, reason, caution}} を返す"""
    path = os.path.join(CHAMP_DIR, champ_id, "matchups.md")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        content = f.read()
    result = {}
    for m in re.finditer(r'^## vs (.+?)（.+?）\n(.*?)(?=\n## |\Z)', content, re.MULTILINE | re.DOTALL):
        opp_ja = m.group(1).strip()
        body   = m.group(2)
        vm = re.search(r'^- \*\*(.+?)（勝率約[^）]*）\*\*[：:]\s*(.+)', body, re.MULTILINE)
        if not vm:
            continue
        verdict = vm.group(1).strip()
        reason  = vm.group(2).strip()
        score   = VERDICT_SCORE.get(verdict, 0)
        cm = re.search(r'^- \*\*注意ポイント\*\*[：:]\s*(.+)', body, re.MULTILINE)
        caution = cm.group(1).strip() if cm else reason
        result[opp_ja] = {"verdict": verdict, "score": score, "reason": reason, "caution": caution}
    return result

# ============================================================
# guide.md セクション更新
# ============================================================

FAV_HEADER   = "## 得意マッチアップ"
UNFAV_HEADER = "## 苦手マッチアップ"
SEC_PAT = re.compile(r'^## ', re.MULTILINE)

def build_section(header, entries):
    """得意/苦手セクションのMarkdownを生成する"""
    lines = [header, ""]
    for opp_ja, d in entries:
        desc = d["reason"] if header == FAV_HEADER else d["caution"]
        lines.append(f"- **{opp_ja}**: {desc}")
    lines.append("")
    return "\n".join(lines) + "\n"

def replace_section(content, header, new_section):
    """guide.md内のセクションを差し替える"""
    # セクション開始位置を探す
    pat = re.compile(r'^' + re.escape(header) + r'\n.*?(?=^## |\Z)', re.MULTILINE | re.DOTALL)
    if pat.search(content):
        return pat.sub(new_section, content)
    return content  # セクションが存在しない場合はそのまま

def update_guide(champ_id, matchups, dry_run=False):
    """guide.md の得意/苦手セクションを再構築する。変更があれば True を返す"""
    guide_path = os.path.join(CHAMP_DIR, champ_id, "guide.md")
    if not os.path.isfile(guide_path):
        return False

    favorable   = sorted([(ja, d) for ja, d in matchups.items() if d["score"] > 0],
                          key=lambda x: -x[1]["score"])[:TOP_N]
    unfavorable = sorted([(ja, d) for ja, d in matchups.items() if d["score"] < 0],
                          key=lambda x: x[1]["score"])[:TOP_N]

    if not favorable and not unfavorable:
        return False

    with open(guide_path, encoding="utf-8") as f:
        content = f.read()

    new_content = content
    if favorable:
        new_content = replace_section(new_content, FAV_HEADER,   build_section(FAV_HEADER,   favorable))
    if unfavorable:
        new_content = replace_section(new_content, UNFAV_HEADER, build_section(UNFAV_HEADER, unfavorable))

    if new_content == content:
        return False

    if dry_run:
        print(f"  [DRY-RUN] {champ_id}/guide.md")
        for ja, d in favorable:
            print(f"    得意: {ja}（{d['verdict']}）")
        for ja, d in unfavorable:
            print(f"    苦手: {ja}（{d['verdict']}）")
    else:
        with open(guide_path, "w", encoding="utf-8") as f:
            f.write(new_content)

    return True

# ============================================================
# Q4矛盾チャンプの抽出（scan-broken.py と同ロジック）
# ============================================================

def find_q4_champs():
    """guide.md 得意/苦手 vs matchups.md verdict に矛盾があるチャンプIDセットを返す"""
    def parse_guide_matchups(champ_id):
        path = os.path.join(CHAMP_DIR, champ_id, "guide.md")
        if not os.path.isfile(path):
            return set(), set()
        with open(path, encoding="utf-8") as f:
            content = f.read()
        favorable, unfavorable = set(), set()
        cur = None
        for line in content.splitlines():
            if re.search(r'^## 得意マッチアップ', line):
                cur = "fav"
            elif re.search(r'^## 苦手マッチアップ', line):
                cur = "unfav"
            elif line.startswith("## "):
                cur = None
            elif cur and line.startswith("- **"):
                m = re.match(r'- \*\*(.+?)\*\*', line)
                if m:
                    (favorable if cur == "fav" else unfavorable).add(m.group(1))
        return favorable, unfavorable

    q4_champs = set()
    for c in DATA["champions"]:
        champ_id = c["id"]
        matchups = parse_matchups(champ_id)
        fav, unfav = parse_guide_matchups(champ_id)
        for opp_ja, d in matchups.items():
            if opp_ja in fav   and d["score"] < 0:
                q4_champs.add(champ_id)
            if opp_ja in unfav and d["score"] > 0:
                q4_champs.add(champ_id)
    return q4_champs

# ============================================================
# メイン
# ============================================================

dry_run  = "--dry-run" in sys.argv
all_mode = "--all"     in sys.argv
args     = [a for a in sys.argv[1:] if not a.startswith("--")]

if args:
    target_ids = args
elif all_mode:
    target_ids = [c["id"] for c in DATA["champions"]]
else:
    print("Q4矛盾チャンプを検出中...")
    target_ids = sorted(find_q4_champs())
    print(f"対象: {len(target_ids)}件\n")

fixed = 0
skipped = 0
for champ_id in target_ids:
    matchups = parse_matchups(champ_id)
    if not matchups:
        skipped += 1
        continue
    changed = update_guide(champ_id, matchups, dry_run=dry_run)
    if changed:
        print(f"{'[DRY]' if dry_run else '更新'}: {champ_id}/guide.md")
        fixed += 1
    else:
        skipped += 1

print(f"\n完了: 更新={fixed}件 / スキップ={skipped}件")
