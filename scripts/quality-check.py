#!/usr/bin/env python3
"""matchups.md 品質チェックスクリプト"""

import os, re, json

CHAMP_DIR = os.path.join(os.path.dirname(__file__), "..", "champions")
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")

DATA = json.load(open(DATA_FILE))
id_to_ja = {c["id"]: c["ja"] for c in DATA["champions"]}
ja_to_id = {c["ja"]: c["id"] for c in DATA["champions"]}
en_to_id = {c["en"]: c["id"] for c in DATA["champions"]}

# --- 1. 対称整合性チェック ---
print("=== 対称マッチアップ整合性チェック ===")

DIFF_SCORE = {"有利": 2, "やや有利": 1, "五分": 0, "やや不利": -1, "不利": -2}
DIFF_REVERSE = {2: "不利", 1: "やや不利", 0: "五分", -1: "やや有利", -2: "有利"}

def parse_matchups(champ_id):
    path = os.path.join(CHAMP_DIR, champ_id, "matchups.md")
    if not os.path.isfile(path):
        return {}
    with open(path, "r") as f:
        content = f.read()
    result = {}
    for m in re.finditer(r'## vs .+?（(.+?)）\n- \*\*(.+?)(（勝率)', content):
        opp_ja = m.group(1)
        diff = m.group(2)
        opp_id = ja_to_id.get(opp_ja) or en_to_id.get(opp_ja)
        if opp_id and diff in DIFF_SCORE:
            result[opp_id] = diff
    return result

all_matchups = {}
for c in DATA["champions"]:
    all_matchups[c["id"]] = parse_matchups(c["id"])

sym_issues = []
checked = set()
for cid, matchups in all_matchups.items():
    for opp_id, diff in matchups.items():
        pair = tuple(sorted([cid, opp_id]))
        if pair in checked:
            continue
        checked.add(pair)
        reverse = all_matchups.get(opp_id, {}).get(cid)
        if reverse is None:
            continue
        score_a = DIFF_SCORE[diff]
        score_b = DIFF_SCORE[reverse]
        if score_a + score_b != 0:
            expected_b = DIFF_REVERSE.get(score_a, "?")
            sym_issues.append(
                f"{id_to_ja[cid]} vs {id_to_ja[opp_id]}: "
                f"{diff}/{reverse} (期待: {diff}/{expected_b})"
            )

print(f"{len(sym_issues)}件の非対称")
for issue in sorted(sym_issues):
    print(f"  {issue}")

# --- 2. 表記揺れチェック ---
print("\n=== 表記揺れ・未翻訳語チェック ===")

KNOWN_ISSUES = [
    (r"ウォーウィック", "ワーウィック"),
    (r"BotRK|BOTRK|BoRK", "ブレード・オブ・ザ・ルインドキング"),
    (r"\bIE\b", "インフィニティ・エッジ"),
    (r"\bGA\b", "ガーディアンエンジェル"),
    (r"\bQSS\b", "クイックシルバーサッシュ"),
    (r"\bLDR\b", "ドミニクリガード"),
    (r"\bBT\b", "ブラッドサースター"),
    (r"\bPD\b", "ファントムダンサー"),
    (r"\bRFC\b", "ラピッドファイアキャノン"),
    (r"ヴァイオレット", "ヴァイ"),
    (r"ウォリック", "ワーウィック"),
]

notation_issues = []
for champ_dir in sorted(os.listdir(CHAMP_DIR)):
    if champ_dir == "_template":
        continue
    for filename in ["matchups.md", "guide.md"]:
        filepath = os.path.join(CHAMP_DIR, champ_dir, filename)
        if not os.path.isfile(filepath):
            continue
        with open(filepath, "r") as f:
            content = f.read()
        for pattern, correct in KNOWN_ISSUES:
            matches = re.findall(pattern, content)
            if matches:
                notation_issues.append(
                    f"{champ_dir}/{filename}: 「{matches[0]}」→「{correct}」"
                )

print(f"{len(notation_issues)}件")
for issue in sorted(notation_issues):
    print(f"  {issue}")
