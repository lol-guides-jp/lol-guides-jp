#!/usr/bin/env python3
"""matchups.md / guide.md 品質修正スクリプト"""

import os, re, json, subprocess

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

# learn.py が蓄積した学習済み修正を自動ロード
_EXPR_RULES_FILE = os.path.join(os.path.dirname(__file__), "expression-rules.json")
_learned = []
if os.path.isfile(_EXPR_RULES_FILE):
    _rules = json.load(open(_EXPR_RULES_FILE, encoding="utf-8"))
    _learned = [(r["literal"], r["replacement"]) for r in _rules.get("learned_replacements", [])]

REPLACEMENTS = [
    # アイテム名の誤り
    ("オラクルのエリクサー", "オラクルレンズ"),
    ("オラクルエリクサー", "オラクルレンズ"),
    # ルーン名の誤り
    ("第2の風", "息継ぎ"),
    ("第二の風", "息継ぎ"),
    ("セカンドウィンド", "息継ぎ"),
    ("コンカー", "征服者"),
    ("フリートフットワークワーク", "フリートフットワーク"),  # 二重置換の修正用
    # チャンピオン名の誤り
    ("ウォーウィック", "ワーウィック"),
    ("ウォリック", "ワーウィック"),
    ("ウルゴット", "アーゴット"),
    ("コグマウ", "コグ＝マウ"),
    ("カイサ", "カイ＝サ"),
    ("ジャーヴァン4世", "ジャーヴァンIV"),
    ("ヴァイン", "ヴェイン"),
    ("BotRK", "ブレード・オブ・ザ・ルインドキング"),
    ("BOTRK", "ブレード・オブ・ザ・ルインドキング"),
    ("BoRK", "ブレード・オブ・ザ・ルインドキング"),
    # ゼラス(Xerath)スキル名誤称
    ("アルカン・パルス:アキシス", "アーケーンライト"),  # Rの誤称（アルカン・パルスはQに近い語感）
    ("アルカン・パルス:アキション", "アーケーンライト"),
    # ジェイスの形態名
    ("砲形態", "キャノンモード"),
    ("槌形態", "ハンマーモード"),
    # ゲーム用語の表記統一（カタカナ優先）
    ("真ダメージ", "トゥルーダメージ"),
    # ミニオン関連
    ("ミニオン波", "ミニオンウェーブ"),
    # タワープレート表記
    ("プレート金", "プレートゴールド"),
    # アンベッサRカタカナ音写
    ("パブリックエクセキューション", "公開処刑"),
]

# 正規表現置換（単語境界必要なもの）
REGEX_REPLACEMENTS = [
    (r"\bLH\b", "CS"),
    # 処刑ライン数値修正（アーゴットRの処刑ラインは25%）
    (r"(デスグラインダー[^。]*?)HP30%以下", r"\g<1>HP25%以下"),
    (r"\bIE\b", "インフィニティ・エッジ"),
    (r"\bGA\b", "ガーディアンエンジェル"),
    (r"\bQSS\b", "クイックシルバーサッシュ"),
    (r"\bLDR\b", "ドミニクリガード"),
    (r"\bBT\b", "ブラッドサースター"),
    (r"\bPD\b", "ファントムダンサー"),
    (r"\bRFC\b", "ラピッドファイアキャノン"),
    # スキルCD秒数の除去（パッチ・レベル依存のため）
    # サモナースペルの固定CD（300/240/360秒）は除外
    (r"(CD|クールダウン)約(?!300|240|360)(\d+)秒", r"\1"),
    # 括弧内CD秒数の除去: （CD18秒Lv1）（CD8/7.5秒）（CD160〜100秒）→削除 ※サモナースペル除外
    (r"（CD(?!300|240|360)\d+[^）]*）", ""),
    # CDの外側括弧形式: CD（16秒Lv1）→ CD ※Lv付きで明確にCD値と判断できる
    (r"（\d+[./〜→]?\d*秒Lv\d+）", ""),
    # （CDLv1）残骸の除去（前回の正規表現が副産物として生成）
    (r"（CDLv\d+）", ""),
    # CDが+秒数パターン: 「CDが9秒まで短縮」→「CDが短縮」 ※サモナースペル除外
    (r"CDが(?!300|240|360)\d+[./〜]?\d*秒(?:（Lv\d+）)?", "CDが"),
    # 文中CD+秒数: 「CD26秒」「CD8秒」→「CD」 ※サモナースペル除外
    (r"CD(?!300|240|360)\d+[./〜]?\d*秒", "CD"),
    # スキル持続時間の秒数除去
    (r"持続約\d+秒", "持続"),
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
        for old, new in REPLACEMENTS + _learned:
            new_content = new_content.replace(old, new)
        for pattern, replacement in REGEX_REPLACEMENTS:
            new_content = re.sub(pattern, replacement, new_content)
        if new_content != content:
            with open(filepath, "w") as f:
                f.write(new_content)
            notation_fixes += 1
            print(f"  修正: {champ_dir}/{filename}")

print(f"表記揺れ修正: {notation_fixes}件")

# --- 2b. スキル名フォーマット逆転修正: スキル名（キー）→ キー（スキル名） ---
print("\n=== スキル名フォーマット逆転修正 ===")

# 全チャンプのスキル名を収集（形態変化は両名とも登録）
all_skill_names = set()
for c in DATA["champions"]:
    for s in c.get("skills", []):
        for name in s["name"].split("/"):
            name = name.strip()
            if name and len(name) >= 2:
                all_skill_names.add(name)

# スキル名（キー）→ キー（スキル名）の置換パターンを生成
# 長い名前優先でマッチ（部分マッチ防止）
skill_names_sorted = sorted(all_skill_names, key=len, reverse=True)
FORMAT_FIX_PATTERN = re.compile(
    r'(' + '|'.join(re.escape(n) for n in skill_names_sorted) + r')（([PQWER])）'
)

format_fixes = 0
for champ_dir in sorted(os.listdir(CHAMP_DIR)):
    if champ_dir == "_template":
        continue
    for filename in ["matchups.md", "guide.md"]:
        filepath = os.path.join(CHAMP_DIR, champ_dir, filename)
        if not os.path.isfile(filepath):
            continue
        with open(filepath, "r") as f:
            content = f.read()
        new_content = FORMAT_FIX_PATTERN.sub(lambda m: f"{m.group(2)}（{m.group(1)}）", content)
        if new_content != content:
            with open(filepath, "w") as f:
                f.write(new_content)
            format_fixes += 1
            print(f"  修正: {champ_dir}/{filename}")

print(f"フォーマット逆転修正: {format_fixes}件")

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
    # AA表記統一
    (r"オートアタック", "AA"),
    (r"(?<![a-zA-Z])Auto(?![a-zA-Z])", "AA"),
    # HP割→HP%統一（HP3割→HP30% 等）
    (r"HP([1-9])割", lambda m: f"HP{int(m.group(1))*10}%"),
    # パッシブ表記統一（P（...） → パッシブ（...））
    (r"(?<![a-zA-Z])P（", "パッシブ（"),
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

# --- 5b. ルーン名の日本語化（ddragon 公式名、guide.md + matchups.md） ---
print("\n=== ルーン名の日本語化 ===")

RUNES_FILE = os.path.join(os.path.dirname(__file__), "runes-ja.json")
rune_fixes = 0

if os.path.isfile(RUNES_FILE):
    runes_map = json.load(open(RUNES_FILE, encoding="utf-8"))
    # 長い名前優先でソート（部分マッチ防止）
    runes_sorted = sorted(runes_map.items(), key=lambda x: len(x[0]), reverse=True)
    # アイテム名と衝突するルーン名: 後続に大文字語が続く場合（複合語）はスキップ
    RUNE_COMPOUND_EXCLUSIONS = {"Guardian"}  # Guardian Angel と衝突

    for champ_dir in sorted(os.listdir(CHAMP_DIR)):
        if champ_dir == "_template":
            continue
        for filename in ["matchups.md", "guide.md"]:
            filepath = os.path.join(CHAMP_DIR, champ_dir, filename)
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
                for en_name, ja_name in runes_sorted:
                    if en_name in RUNE_COMPOUND_EXCLUSIONS:
                        # スペース+大文字が続く場合（複合語の一部）は除外
                        pattern = r'(?<![a-zA-Z])' + re.escape(en_name) + r'(?! [A-Z])(?![a-zA-Z])'
                    else:
                        pattern = r'(?<![a-zA-Z])' + re.escape(en_name) + r'(?![a-zA-Z])'
                    new_line = re.sub(pattern, ja_name, new_line)
                if new_line != line:
                    changed = True
                new_lines.append(new_line)

            if changed:
                with open(filepath, "w") as f:
                    f.writelines(new_lines)
                rune_fixes += 1
                print(f"  修正: {champ_dir}/{filename}")
else:
    print("  runes-ja.json が見つかりません。scripts/fetch-runes.py を実行してください")

print(f"ルーン名修正: {rune_fixes}件")

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

# --- 6. スキル名正規化（統合版）---
# invalid判定をセクション文脈（メインチャンプ+対戦相手）ベースで行う
# - 3+セクション出現 → メインチャンプのスキル名ミス → メイン公式名で置換
# - 1-2セクション出現 → 対戦相手のスキル名ミス → 対戦相手公式名で置換（セクション単位）
print("\n=== スキル名正規化（統合） ===")

_ja_to_id = {c["ja"]: c["id"] for c in DATA["champions"]}
_en_to_id = {c["en"]: c["id"] for c in DATA["champions"]}

# 全チャンプスキルマップ: {id: {key: {"official": str, "valid": set}}}
_champ_sm = {}
for c in DATA["champions"]:
    sm = {}
    for skill in c.get("skills", []):
        key = skill["key"]
        if key not in "PQWER":
            continue
        full_name = skill["name"]
        official = full_name.split("/")[0].strip()
        valid = {full_name, official}
        for part in full_name.split("/"):
            valid.add(part.strip())
        sm[key] = {"official": official, "valid": valid}
    _champ_sm[c["id"]] = sm

_sec_re = re.compile(r'^## vs (.+?)（(.+?)）')
_skill_re = re.compile(r'([PQWER])（([^）]+)）')
_skill_extra_re = re.compile(r'([PQWER])（([^）、,，（(]+)[、,，（(][^）]*）')
skill_fix_total = 0

# Pass 0: 有効名+追記を剥ぎ取る（例: Q（コラプトシェル、CD10秒）→ Q（コラプトシェル））
extra_fix_total = 0
for champ_dir in sorted(os.listdir(CHAMP_DIR)):
    if champ_dir == "_template" or champ_dir not in _champ_sm:
        continue
    filepath = os.path.join(CHAMP_DIR, champ_dir, "matchups.md")
    if not os.path.isfile(filepath):
        continue

    main_sm = _champ_sm[champ_dir]
    opp_sm_cur = {}

    with open(filepath, "r") as f:
        lines = f.readlines()

    new_lines = []
    changed = False
    for line in lines:
        m = _sec_re.match(line.strip())
        if m:
            ja_p, en_p = m.group(1), m.group(2)
            opp_id = _ja_to_id.get(ja_p) or _en_to_id.get(ja_p) or _ja_to_id.get(en_p) or _en_to_id.get(en_p)
            opp_sm_cur = _champ_sm.get(opp_id, {})
        new_line = line
        for m2 in _skill_extra_re.finditer(line):
            key, base = m2.group(1), m2.group(2)
            all_valid = main_sm.get(key, {}).get("valid", set()) | opp_sm_cur.get(key, {}).get("valid", set())
            if base in all_valid:
                new_line = new_line.replace(m2.group(0), f"{key}（{base}）", 1)
        if new_line != line:
            changed = True
        new_lines.append(new_line)

    if changed:
        with open(filepath, "w") as f:
            f.writelines(new_lines)
        extra_fix_total += 1
        print(f"  修正: {champ_dir}/matchups.md")

print(f"スキル名+追記修正: {extra_fix_total}件\n")

for champ_dir in sorted(os.listdir(CHAMP_DIR)):
    if champ_dir == "_template" or champ_dir not in _champ_sm:
        continue
    filepath = os.path.join(CHAMP_DIR, champ_dir, "matchups.md")
    if not os.path.isfile(filepath):
        continue

    main_sm = _champ_sm[champ_dir]

    with open(filepath, "r") as f:
        content = f.read()
    lines = content.splitlines(keepends=True)

    # Pass 1: 全セクションの対戦相手IDを解決
    sec_opp = {}  # section_str -> opp_id or None
    for line in lines:
        m = _sec_re.match(line.strip())
        if m:
            ja_p, en_p = m.group(1), m.group(2)
            sec_opp[line.strip()] = (
                _ja_to_id.get(ja_p) or _en_to_id.get(ja_p) or
                _ja_to_id.get(en_p) or _en_to_id.get(en_p)
            )

    # Pass 2: (key, wrong) → 出現セクション集合を集計（セクション文脈で invalid 判定）
    pair_secs = {}   # (key, wrong) -> set of section_str
    current_sec = None
    for line in lines:
        m = _sec_re.match(line.strip())
        if m:
            current_sec = line.strip()
            continue
        if line.startswith("#") or line.startswith(">") or line.startswith("---"):
            continue
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue
        opp_id  = sec_opp.get(current_sec)
        opp_sm  = _champ_sm.get(opp_id, {})
        for m in _skill_re.finditer(stripped):
            key, name = m.group(1), m.group(2)
            main_valid = main_sm.get(key, {}).get("valid", set())
            opp_valid  = opp_sm.get(key, {}).get("valid", set())
            all_valid  = main_valid | opp_valid
            if name in all_valid:
                continue
            pair_secs.setdefault((key, name), set()).add(current_sec)

    if not pair_secs:
        continue

    # Pass 3: 置換を決定
    # 3+セクション → メインチャンプのキー公式名（ファイル全体置換）
    # 1-2セクション → 各セクションの対戦相手キー公式名（セクション単位置換）
    global_replacements = {}     # old_str -> new_str
    section_replacements = {}    # (old_str, sec) -> new_str

    for (key, wrong), secs in pair_secs.items():
        old_str = f"{key}（{wrong}）"
        if len(secs) >= 3:
            main_official = main_sm.get(key, {}).get("official")
            if main_official:
                new_str = f"{key}（{main_official}）"
                if old_str != new_str:
                    global_replacements[old_str] = new_str
        else:
            for sec in secs:
                opp_id = sec_opp.get(sec)
                opp_official = _champ_sm.get(opp_id, {}).get(key, {}).get("official")
                if opp_official:
                    new_str = f"{key}（{opp_official}）"
                    if old_str != new_str:
                        section_replacements[(old_str, sec)] = new_str

    if not global_replacements and not section_replacements:
        continue

    # Pass 4: 置換適用
    new_lines = []
    current_sec = None
    for line in lines:
        m = _sec_re.match(line.strip())
        if m:
            current_sec = line.strip()
        new_line = line
        # グローバル置換（全セクション共通）
        for old, new in global_replacements.items():
            if old in new_line:
                new_line = new_line.replace(old, new)
        # セクション単位置換
        for (old, sec), new in section_replacements.items():
            if current_sec == sec and old in new_line:
                new_line = new_line.replace(old, new)
        new_lines.append(new_line)

    new_content = "".join(new_lines)
    if new_content != content:
        with open(filepath, "w") as f:
            f.write(new_content)
        n = len(global_replacements) + len(section_replacements)
        skill_fix_total += n
        if global_replacements:
            for old, new in global_replacements.items():
                print(f"  {champ_dir}: {old} → {new} (全体)")
        if section_replacements:
            print(f"  {champ_dir}: 対戦相手スキル {len(section_replacements)}件")

print(f"スキル名正規化: {skill_fix_total}パターン")

# ==========================================================
# 最終: data.json 再ビルド（手動修正後の乖離解消）
# ==========================================================
BUILD_JS = os.path.join(os.path.dirname(__file__), "build-json.js")
if os.path.isfile(BUILD_JS):
    print("\n=== data.json 再ビルド ===")
    result = subprocess.run(["node", BUILD_JS], capture_output=True, text=True,
                            cwd=os.path.join(os.path.dirname(__file__), ".."))
    if result.returncode == 0:
        print("data.json 再ビルド完了")
    else:
        print(f"WARNING: build-json.js 失敗: {result.stderr[:300]}")
