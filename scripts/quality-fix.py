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
    ("ウルゴット", "アーゴット"),
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

# --- 3. 日英混在修正（matchups.md 本文行のみ） ---
print("\n=== 日英混在修正 ===")

en_to_ja = {c["en"]: c["ja"] for c in DATA["champions"]}
en_names_sorted = sorted(en_to_ja.keys(), key=len, reverse=True)

# 本文行に適用する一括置換（ヘッダ・括弧内は除外）
# 置換順序は長いパターン優先（部分マッチ防止）
BODY_REPLACEMENTS = [
    # Ult/ウルト → R（括弧内のスキル名は保持）
    (r"(?<![a-zA-Z])[Uu][Ll][Tt](?=[（(])", "R"),   # ULT（スキル名） → R（スキル名）
    (r"(?<![a-zA-Z])[Uu][Ll][Tt](?![a-zA-Z（(])", "R"),  # Ult単体 → R
    (r"ウルト(?!ラ)(?=[（(])", "R"),   # ウルト（スキル名） → R（スキル名）
    (r"ウルト(?!ラ)(?![（(])", "R"),   # ウルト単体 → R
    # 英語スタンドアロン語
    (r"スロー[Pp]ush", "スロープッシュ"),
    (r"Sterak['']s Gage", "ステラックの篭手"),
    (r"Sterak['']s", "ステラックの"),
    (r"スタラックのゲージ", "ステラックの篭手"),
    (r"[Gg]ank(?![a-zA-Z])", "ガンク"),
    (r"(?<![a-zA-Z])[Jj]ungle(?![a-zA-Z])", "ジャングル"),
    (r"(?<![a-zA-Z])early game(?![a-zA-Z])", "序盤"),
    (r"(?<![a-zA-Z])mid game(?![a-zA-Z])", "中盤"),
    (r"(?<![a-zA-Z])late game(?![a-zA-Z])", "終盤"),
    (r"(?<![a-zA-Z])early(?![a-zA-Z])", "序盤"),
    (r"execution(?![a-zA-Z])", "処刑"),
    (r"CS/min", "CS/分"),
    (r"(\d+)wave(\d+)", r"\1ウェーブ\2"),  # 1wave6体 → 1ウェーブ6体
]

mix_fixes = 0
for champ_dir in sorted(os.listdir(CHAMP_DIR)):
    if champ_dir == "_template":
        continue
    filepath = os.path.join(CHAMP_DIR, champ_dir, "matchups.md")
    if not os.path.isfile(filepath):
        continue
    with open(filepath, "r") as f:
        lines = f.readlines()

    new_lines = []
    changed = False
    for line in lines:
        new_line = line
        # ヘッダ行・メタ行は変更しない
        if new_line.startswith("#") or new_line.startswith(">") or new_line.startswith("---"):
            new_lines.append(new_line)
            continue

        # 一括置換
        for pattern, replacement in BODY_REPLACEMENTS:
            new_line = re.sub(pattern, replacement, new_line)

        # 英語チャンプ名を日本語に置換（括弧内は除外）
        # 括弧内を一時的にマスクしてから置換
        placeholders = {}
        def mask_parens(m):
            key = f"__PAREN{len(placeholders)}__"
            placeholders[key] = m.group(0)
            return key
        masked = re.sub(r'（[^）]*）|\([^)]*\)', mask_parens, new_line)
        for en_name in en_names_sorted:
            pattern = r'(?<![a-zA-Z])' + re.escape(en_name) + r'(?![a-zA-Z])'
            masked = re.sub(pattern, en_to_ja[en_name], masked)
        for key, val in placeholders.items():
            masked = masked.replace(key, val)
        new_line = masked

        if new_line != line:
            changed = True
        new_lines.append(new_line)

    if changed:
        with open(filepath, "w") as f:
            f.writelines(new_lines)
        mix_fixes += 1
        print(f"  修正: {champ_dir}/matchups.md")

print(f"日英混在修正: {mix_fixes}件")

# --- 5. アイテム名の日本語化（ddragon 公式名） ---
print("\n=== アイテム名の日本語化 ===")

ITEMS_FILE = os.path.join(os.path.dirname(__file__), "items-ja.json")
item_fixes = 0

if os.path.isfile(ITEMS_FILE):
    items_map = json.load(open(ITEMS_FILE, encoding="utf-8"))
    # 長い名前優先でソート（部分マッチ防止）
    items_sorted = sorted(items_map.items(), key=lambda x: len(x[0]), reverse=True)

    for champ_dir in sorted(os.listdir(CHAMP_DIR)):
        if champ_dir == "_template":
            continue
        filepath = os.path.join(CHAMP_DIR, champ_dir, "matchups.md")
        if not os.path.isfile(filepath):
            continue
        with open(filepath, "r") as f:
            lines = f.readlines()

        new_lines = []
        changed = False
        for line in lines:
            if line.startswith("#") or line.startswith(">") or line.startswith("---"):
                new_lines.append(line)
                continue
            new_line = line
            for en_name, ja_name in items_sorted:
                # 単語境界（ASCII）でマッチ
                pattern = r'(?<![a-zA-Z])' + re.escape(en_name) + r'(?![a-zA-Z])'
                new_line = re.sub(pattern, ja_name, new_line)
            if new_line != line:
                changed = True
            new_lines.append(new_line)

        if changed:
            with open(filepath, "w") as f:
                f.writelines(new_lines)
            item_fixes += 1
            print(f"  修正: {champ_dir}/matchups.md")
else:
    print("  items-ja.json が見つかりません。scripts/fetch-items.py を実行してください")

print(f"アイテム名修正: {item_fixes}件")

# --- 4. 勝率表記の正規化（範囲→中央値の整数、小数点除去） ---
print("\n=== 勝率表記の正規化 ===")

import math

def normalize_winrate(m):
    inner = m.group(1)  # 例: 47〜49、46.4〜49.4、52.3
    if '〜' in inner:
        parts = inner.split('〜')
        avg = (float(parts[0]) + float(parts[1])) / 2
        return f"勝率約{round(avg)}%"
    else:
        return f"勝率約{round(float(inner))}%"

winrate_fixes = 0
for champ_dir in sorted(os.listdir(CHAMP_DIR)):
    if champ_dir == "_template":
        continue
    filepath = os.path.join(CHAMP_DIR, champ_dir, "matchups.md")
    if not os.path.isfile(filepath):
        continue
    with open(filepath, "r") as f:
        content = f.read()
    new_content = re.sub(r'勝率約([\d.]+(?:〜[\d.]+)?)%', normalize_winrate, content)
    if new_content != content:
        with open(filepath, "w") as f:
            f.write(new_content)
        winrate_fixes += 1
        print(f"  修正: {champ_dir}/matchups.md")

print(f"勝率正規化: {winrate_fixes}件")

# --- 6. チャンプ自身のスキル名正規化（ヒューリスティック） ---
# 各champions/X/matchups.md で、同一キー（Q/W/E/R）の不明スキル名が
# 3セクション以上に出現 → そのキーのメインチャンプ公式名で一括置換
print("\n=== チャンプ自身スキル名正規化 ===")

# 公式スキル名セット構築
valid_skill_names_fix = {'P': set(), 'Q': set(), 'W': set(), 'E': set(), 'R': set()}
champ_skills_fix = {}  # champ_id -> {key: official_name}
for c in DATA["champions"]:
    skills = {}
    for skill in c.get("skills", []):
        key = skill["key"]
        if key not in valid_skill_names_fix:
            continue
        full_name = skill["name"]
        valid_skill_names_fix[key].add(full_name)
        for part in full_name.split("/"):
            valid_skill_names_fix[key].add(part.strip())
        skills[key] = full_name  # 最初のパート（/区切り前）を正規名とする
    champ_skills_fix[c["id"]] = skills

skill_ref_pattern_fix = re.compile(r'([PQWER])（([^）]+)）')
section_pattern = re.compile(r'^## vs ')
skill_norm_fixes = 0

for champ_dir in sorted(os.listdir(CHAMP_DIR)):
    if champ_dir == "_template":
        continue
    if champ_dir not in champ_skills_fix:
        continue
    filepath = os.path.join(CHAMP_DIR, champ_dir, "matchups.md")
    if not os.path.isfile(filepath):
        continue

    official_skills = champ_skills_fix[champ_dir]  # {key: official_name}

    with open(filepath, "r") as f:
        content = f.read()

    # セクション別に不明スキル名の出現数をカウント
    current_section = None
    sections_with_wrong = {}  # (key, wrong_name) -> set of sections

    for line in content.splitlines():
        if line.startswith("## vs"):
            current_section = line.strip()
        if line.startswith("#") or line.startswith(">") or line.startswith("---"):
            continue
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue
        # 括弧内を一時マスク（ネスト対策）
        masked = re.sub(r'（[^）]*）', lambda m: '（' + 'X' * (len(m.group(0)) - 2) + '）', stripped)
        for m in skill_ref_pattern_fix.finditer(stripped):
            key = m.group(1)
            name = m.group(2)
            valid_set = valid_skill_names_fix.get(key, set())
            if name in valid_set:
                continue
            is_extra = any(
                name.startswith(off) and len(name) > len(off) and name[len(off)] in '、，,（('
                for off in valid_set
            )
            if not is_extra:
                pair = (key, name)
                if pair not in sections_with_wrong:
                    sections_with_wrong[pair] = set()
                if current_section:
                    sections_with_wrong[pair].add(current_section)

    # 3セクション以上に出現 + そのキーに公式名がある → 置換
    new_content = content
    for (key, wrong_name), sections in sorted(sections_with_wrong.items()):
        if len(sections) < 3:
            continue
        official = official_skills.get(key)
        if not official:
            continue
        old_str = f"{key}（{wrong_name}）"
        new_str = f"{key}（{official}）"
        if old_str in new_content:
            new_content = new_content.replace(old_str, new_str)
            print(f"  {champ_dir}: {old_str} → {new_str} ({len(sections)}セクション)")
            skill_norm_fixes += 1

    if new_content != content:
        with open(filepath, "w") as f:
            f.write(new_content)

print(f"スキル名正規化: {skill_norm_fixes}パターン")
