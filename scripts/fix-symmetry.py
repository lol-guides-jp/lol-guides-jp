#!/usr/bin/env python3
"""対称マッチアップ整合性を修正（辞書順先のA側を正、B側を反転に修正）"""

import os, re, json

CHAMP_DIR = os.path.join(os.path.dirname(__file__), "..", "champions")
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")

DATA = json.load(open(DATA_FILE))
ja_to_id = {c["ja"]: c["id"] for c in DATA["champions"]}
en_to_id = {c["en"]: c["id"] for c in DATA["champions"]}
id_to_ja = {c["id"]: c["ja"] for c in DATA["champions"]}
id_to_en = {c["id"]: c["en"] for c in DATA["champions"]}
name_to_id = {**ja_to_id, **en_to_id}

DIFF_SCORE = {"有利": 2, "やや有利": 1, "五分": 0, "やや不利": -1, "不利": -2}
SCORE_DIFF = {v: k for k, v in DIFF_SCORE.items()}

# ヘッダー+難易度パターン: "## vs NAME1（NAME2）\n- **DIFF（勝率"
# NAME1/NAME2 は日本語/英語のどちらでもあり得る
DIFF_PATTERN = re.compile(
    r'## vs (.+?)（(.+?)）\n- \*\*(.+?)（勝率'
)

def get_matchup_diffs(champ_id):
    path = os.path.join(CHAMP_DIR, champ_id, "matchups.md")
    if not os.path.isfile(path):
        return {}
    with open(path, "r") as f:
        content = f.read()
    result = {}
    for m in DIFF_PATTERN.finditer(content):
        name1, name2, diff = m.group(1), m.group(2), m.group(3)
        opp_id = name_to_id.get(name1) or name_to_id.get(name2)
        if opp_id and diff in DIFF_SCORE:
            result[opp_id] = diff
    return result

all_diffs = {}
for c in DATA["champions"]:
    all_diffs[c["id"]] = get_matchup_diffs(c["id"])

# 非対称ペアを収集
fixes = {}  # {champ_id: {opp_id: new_diff}}
checked = set()
for cid in sorted(all_diffs.keys()):
    for opp_id, diff_a in all_diffs[cid].items():
        pair = tuple(sorted([cid, opp_id]))
        if pair in checked:
            continue
        checked.add(pair)
        diff_b = all_diffs.get(opp_id, {}).get(cid)
        if diff_b is None:
            continue
        score_a = DIFF_SCORE[diff_a]
        score_b = DIFF_SCORE[diff_b]
        if score_a + score_b == 0:
            continue
        # cid（辞書順先）を正とし、opp_id（辞書順後）を修正
        if cid < opp_id:
            target_id = opp_id
            source_id = cid
            new_diff = SCORE_DIFF[-score_a]
        else:
            target_id = cid
            source_id = opp_id
            new_diff = SCORE_DIFF[-score_b]
        if target_id not in fixes:
            fixes[target_id] = {}
        fixes[target_id][source_id] = new_diff

# ファイル修正
total = 0
for champ_id, opp_fixes in fixes.items():
    path = os.path.join(CHAMP_DIR, champ_id, "matchups.md")
    if not os.path.isfile(path):
        continue
    with open(path, "r") as f:
        content = f.read()
    for opp_id, new_diff in opp_fixes.items():
        opp_ja = id_to_ja[opp_id]
        opp_en = id_to_en[opp_id]
        # 括弧の外または中にja/enどちらかがある
        for name in [opp_ja, opp_en]:
            escaped = re.escape(name)
            # パターン1: ## vs ...（{name}）\n- **DIFF（勝率
            pat = re.compile(
                r'(## vs .+?（' + escaped + r'）\n- \*\*)'
                r'(.+?)'
                r'(（勝率)'
            )
            m = pat.search(content)
            if not m:
                # パターン2: ## vs {name}（...）\n- **DIFF（勝率
                pat = re.compile(
                    r'(## vs ' + escaped + r'（.+?）\n- \*\*)'
                    r'(.+?)'
                    r'(（勝率)'
                )
                m = pat.search(content)
            if m:
                old_diff = m.group(2)
                if old_diff != new_diff:
                    content = content[:m.start(2)] + new_diff + content[m.end(2):]
                    total += 1
                    print(f"  {id_to_ja[champ_id]} vs {opp_ja}: {old_diff}→{new_diff}")
                break
    with open(path, "w") as f:
        f.write(content)

print(f"\n合計 {total}件修正")
