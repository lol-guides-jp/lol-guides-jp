#!/usr/bin/env python3
"""matchups.md / guide.md 品質修正スクリプト"""

import os, re, json

CHAMP_DIR = os.path.join(os.path.dirname(__file__), "..", "champions")
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")

DATA = json.load(open(DATA_FILE))
ja_to_id = {c["ja"]: c["id"] for c in DATA["champions"]}
id_to_ja = {c["id"]: c["ja"] for c in DATA["champions"]}

DIFF_SCORE = {"有利": 2, "やや有利": 1, "五分": 0, "やや不利": -1, "不利": -2}
SCORE_DIFF = {v: k for k, v in DIFF_SCORE.items()}

# --- 1. 対称整合性修正 ---
# A側の難易度を正とし、B側を反転値に修正する
# ただしA/Bどちらを正とするか: id辞書順で先の方を正とする
print("=== 対称整合性修正 ===")

def parse_matchups_with_pos(champ_id):
    path = os.path.join(CHAMP_DIR, champ_id, "matchups.md")
    if not os.path.isfile(path):
        return {}, ""
    with open(path, "r") as f:
        content = f.read()
    result = {}
    for m in re.finditer(r'(## vs .+?（(.+?)）\n- \*\*)(.+?)(（勝率約)', content):
        opp_ja = m.group(2)
        diff = m.group(3)
        opp_id = ja_to_id.get(opp_ja)
        if opp_id and diff in DIFF_SCORE:
            result[opp_id] = {"diff": diff, "start": m.start(3), "end": m.end(3)}
    return result, content

all_data = {}
for c in DATA["champions"]:
    matchups, content = parse_matchups_with_pos(c["id"])
    all_data[c["id"]] = {"matchups": matchups, "content": content}

sym_fixes = 0
checked = set()
for cid in sorted(all_data.keys()):
    for opp_id, info_a in all_data[cid]["matchups"].items():
        pair = tuple(sorted([cid, opp_id]))
        if pair in checked:
            continue
        checked.add(pair)

        info_b = all_data.get(opp_id, {}).get("matchups", {}).get(cid)
        if info_b is None:
            continue

        score_a = DIFF_SCORE[info_a["diff"]]
        score_b = DIFF_SCORE[info_b["diff"]]
        if score_a + score_b == 0:
            continue

        # A側（辞書順先）を正とし、B側を修正
        expected_b = SCORE_DIFF[-score_a]
        content_b = all_data[opp_id]["content"]
        old_diff = info_b["diff"]
        content_b = (
            content_b[:info_b["start"]] + expected_b + content_b[info_b["end"]:]
        )
        all_data[opp_id]["content"] = content_b
        # positionがずれるので再パースはしない（1対面1修正なので安全）
        sym_fixes += 1
        print(f"  {id_to_ja[opp_id]} vs {id_to_ja[cid]}: {old_diff}→{expected_b}")

# 修正内容を書き出し
for cid, data in all_data.items():
    path = os.path.join(CHAMP_DIR, cid, "matchups.md")
    if not os.path.isfile(path):
        continue
    with open(path, "r") as f:
        original = f.read()
    if data["content"] != original:
        with open(path, "w") as f:
            f.write(data["content"])

print(f"対称修正: {sym_fixes}件\n")

# --- 2. 表記揺れ修正（guide.md + matchups.md） ---
print("=== 表記揺れ修正 ===")

REPLACEMENTS = [
    ("ウォーウィック", "ワーウィック"),
    ("ウォリック", "ワーウィック"),
    ("BotRK", "ブレード・オブ・ザ・ルインドキング"),
    ("BOTRK", "ブレード・オブ・ザ・ルインドキング"),
    ("BoRK", "ブレード・オブ・ザ・ルインドキング"),
]

# 正規表現置換（単語境界必要なもの）
REGEX_REPLACEMENTS = [
    (r"\bIE\b", "インフィニティ・エッジ"),
    (r"\bGA\b", "ガーディアンエンジェル"),
    (r"\bQSS\b", "クイックシルバーサッシュ"),
    (r"\bLDR\b", "ドミニクリガード"),
    (r"\bBT\b", "ブラッドサースター"),
    (r"\bPD\b", "ファントムダンサー"),
    (r"\bRFC\b", "ラピッドファイアキャノン"),
]

notation_fixes = 0
for champ_dir in sorted(os.listdir(CHAMP_DIR)):
    if champ_dir == "_template":
        continue
    for filename in ["matchups.md", "guide.md"]:
        filepath = os.path.join(CHAMP_DIR, champ_dir, filename)
        if not os.path.isfile(filepath):
            continue
        with open(filepath, "r") as f:
            content = f.read()
        new_content = content
        for old, new in REPLACEMENTS:
            new_content = new_content.replace(old, new)
        for pattern, replacement in REGEX_REPLACEMENTS:
            new_content = re.sub(pattern, replacement, new_content)
        if new_content != content:
            with open(filepath, "w") as f:
                f.write(new_content)
            notation_fixes += 1
            print(f"  修正: {champ_dir}/{filename}")

print(f"表記揺れ修正: {notation_fixes}件")
