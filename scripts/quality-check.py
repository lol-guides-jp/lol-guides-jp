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
    (r"ウルゴット", "アーゴット"),
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
    (r"コグマウ(?!＝)", "コグ＝マウ"),
    (r"カイサ(?!＝)", "カイ＝サ"),
    (r"ジャーヴァン4世", "ジャーヴァンIV"),
    (r"ヴァイン", "ヴェイン"),
    (r"の窓(?!口|側|辺)", "のチャンス/隙（「窓」はゲームジャーゴン）"),
    (r"パブリックエクセキューション", "公開処刑（アンベッサRのカタカナ音写）"),
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

# --- 3. 日英混在・要変換候補チェック ---
print("\n=== 日英混在・要変換候補 ===")

# 英語→日本語変換候補（LoLコミュニティで定着しているものは除外: CS, CD, HP, AD, AP, AA）
# \b は Python3 で日本語文字を word char 扱いするため ASCII 境界パターンを使う
TRANSLATE_CANDIDATES = [
    (r"(?<![a-zA-Z])[Uu][Ll][Tt](?![a-zA-Z])", "R（スキル名）"),
    (r"ウルト(?!ラ)", "R（スキル名）"),
    (r"(?<![a-zA-Z])push(?![a-zA-Z])",          "プッシュ"),
    (r"(?<![a-zA-Z])poke(?![a-zA-Z])",          "ポーク"),
    (r"(?<![a-zA-Z])gank(?![a-zA-Z])",          "ガンク"),
    (r"(?<![a-zA-Z])wave(?![a-zA-Z])",          "ウェーブ"),
    (r"(?<![a-zA-Z])freeze(?![a-zA-Z])",        "フリーズ"),
    (r"(?<![a-zA-Z])trade(?![a-zA-Z])",         "トレード"),
    (r"all-in",                                  "オールイン"),
    (r"(?<![a-zA-Z])farm(?![a-zA-Z])",          "ファーム"),
    (r"(?<![a-zA-Z])jungle(?![a-zA-Z])",        "ジャングル"),
    (r"(?<![a-zA-Z])lane(?![a-zA-Z])",          "レーン"),
    (r"(?<![a-zA-Z])skill(?![a-zA-Z])",         "スキル"),
    (r"(?<![a-zA-Z])combo(?![a-zA-Z])",         "コンボ"),
]

# 英語チャンプ名リスト（ヘッダ行・括弧内は除外して本文行のみチェック）
en_names = sorted(en_to_id.keys(), key=len, reverse=True)
en_name_pattern = r'\b(' + '|'.join(re.escape(n) for n in en_names) + r')\b'

mix_issues = []

for champ_dir in sorted(os.listdir(CHAMP_DIR)):
    if champ_dir == "_template":
        continue
    filepath = os.path.join(CHAMP_DIR, champ_dir, "matchups.md")
    if not os.path.isfile(filepath):
        continue
    with open(filepath, "r") as f:
        lines = f.readlines()

    for lineno, line in enumerate(lines, 1):
        # ヘッダ行（## vs）とファイル先頭行はスキップ
        if line.startswith("#") or line.startswith(">"):
            continue
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue

        # 変換候補チェック
        for pattern, suggestion in TRANSLATE_CANDIDATES:
            if re.search(pattern, stripped, re.IGNORECASE):
                found = re.search(pattern, stripped, re.IGNORECASE).group()
                mix_issues.append(
                    f"{champ_dir}/matchups.md:{lineno}: 「{found}」→「{suggestion}」候補\n"
                    f"    {stripped[:80]}"
                )

        # 英語チャンプ名の本文混入チェック（括弧内は許容）
        # 括弧内を除いた文字列で検索
        stripped_no_paren = re.sub(r'（[^）]*）|\([^)]*\)', '', stripped)
        for m in re.finditer(en_name_pattern, stripped_no_paren):
            en_name = m.group()
            ja_name = id_to_ja.get(en_to_id.get(en_name, ""), en_name)
            mix_issues.append(
                f"{champ_dir}/matchups.md:{lineno}: 英語チャンプ名「{en_name}」→「{ja_name}」候補\n"
                f"    {stripped[:80]}"
            )

print(f"{len(mix_issues)}件の候補")
for issue in mix_issues:
    print(f"  {issue}")

# --- 4. スキル名バリデーション（セクション文脈で両チャンプの公式名を参照） ---
print("\n=== スキル名バリデーション ===")

# 全チャンプのスキルマップ: {champ_id: {key: {"official": str, "valid": set}}}
champ_skill_map = {}
for c in DATA["champions"]:
    skill_map = {}
    for skill in c.get("skills", []):
        key = skill["key"]
        if key not in {'P', 'Q', 'W', 'E', 'R'}:
            continue
        full_name = skill["name"]
        valid = {full_name}
        for part in full_name.split("/"):
            valid.add(part.strip())
        skill_map[key] = {"official": full_name.split("/")[0].strip(), "valid": valid}
    champ_skill_map[c["id"]] = skill_map

section_re = re.compile(r'^## vs (.+?)（(.+?)）')
skill_ref_re = re.compile(r'([PQWER])（([^）]+)）')

cnt_valid = cnt_invalid = 0
invalid_by_champ = {}
extra_count = 0

def check_skill_names_in_file(filepath, main_sm, is_matchups=True):
    """スキル名バリデーション。matchups.md は対戦相手セクション切り替えあり、guide.md はなし。"""
    issues = []
    valid = invalid = 0
    opp_sm = {}
    opp_ja_name = ""

    with open(filepath, "r") as f:
        lines = f.readlines()

    for lineno, line in enumerate(lines, 1):
        if is_matchups:
            m_sec = section_re.match(line.strip())
            if m_sec:
                ja_part, en_part = m_sec.group(1), m_sec.group(2)
                opp_id = ja_to_id.get(ja_part) or en_to_id.get(ja_part) or \
                         ja_to_id.get(en_part) or en_to_id.get(en_part)
                opp_sm = champ_skill_map.get(opp_id, {})
                opp_ja_name = id_to_ja.get(opp_id, ja_part) if opp_id else ja_part
                continue

        if line.startswith("#") or line.startswith(">") or line.startswith("---"):
            continue
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue

        for m in skill_ref_re.finditer(stripped):
            key, name = m.group(1), m.group(2)
            main_valid = main_sm.get(key, {}).get("valid", set())
            opp_valid  = opp_sm.get(key, {}).get("valid", set())
            all_valid  = main_valid | opp_valid

            if name in all_valid:
                valid += 1
            else:
                invalid += 1
                cands = []
                mo = main_sm.get(key, {}).get("official")
                oo = opp_sm.get(key, {}).get("official")
                if mo:
                    cands.append(f"{key}（{mo}）[自]")
                if oo and oo != mo:
                    cands.append(f"{key}（{oo}）[{opp_ja_name}]")
                issues.append((lineno, key, name, " / ".join(cands)))

    return valid, invalid, issues

for champ_dir in sorted(os.listdir(CHAMP_DIR)):
    if champ_dir == "_template" or champ_dir not in champ_skill_map:
        continue
    main_sm = champ_skill_map[champ_dir]
    champ_issues = []

    for filename, is_matchups in [("matchups.md", True), ("guide.md", False)]:
        filepath = os.path.join(CHAMP_DIR, champ_dir, filename)
        if not os.path.isfile(filepath):
            continue
        v, inv, issues = check_skill_names_in_file(filepath, main_sm, is_matchups)
        cnt_valid += v
        cnt_invalid += inv
        for lineno, key, name, cands in issues:
            champ_issues.append((lineno, key, name, cands, filename))

    if champ_issues:
        invalid_by_champ[champ_dir] = champ_issues

print(f"有効: {cnt_valid}件 / 不明スキル名: {cnt_invalid}件")
print()
total_files = len(invalid_by_champ)
print(f"不明スキル名 チャンプ別上位20件（全{total_files}ファイル）:")
for champ, issues in sorted(invalid_by_champ.items(), key=lambda x: -len(x[1]))[:20]:
    print(f"  {champ:<20} {len(issues)}件")

if "--verbose" in __import__("sys").argv:
    import sys
    print("\n--- 不明スキル名（全件・修正候補付き） ---")
    for champ, issues in sorted(invalid_by_champ.items(), key=lambda x: -len(x[1])):
        for lineno, key, name, cands, fname in issues:
            print(f"  {champ}/{fname}:{lineno}: {key}（{name}） → {cands}")

# --- Section 5: 文字化けチェック ---
print()
print("=== 文字化けチェック ===")
GARBLED_CHARS = ['\ufffd', '▪', '▫']  # U+FFFD(置換文字), ▪, ▫
garbled_found = []
for c in DATA["champions"]:
    path = os.path.join(CHAMP_DIR, c["id"], "matchups.md")
    if not os.path.isfile(path):
        continue
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            for ch in GARBLED_CHARS:
                if ch in line:
                    garbled_found.append((c["id"], lineno, line.strip()[:80]))
                    break

if garbled_found:
    print(f"文字化け検出: {len(garbled_found)}件")
    for champ_id, lineno, preview in garbled_found[:20]:
        print(f"  {champ_id}/matchups.md:{lineno}: {preview}")
else:
    print("文字化け: 0件")
