#!/usr/bin/env python3
"""matchups.md 壊れエントリ検出スクリプト（ルールベース・コスト$0）

3段階のtiering:
  broken  — 構造的に壊れてる（全再生成: research + write）
  quality — 内容が悪い（matchup.mdから再生成: write only）
  minor   — quality-fix.pyで対応可能な軽微な修正
  ok      — 問題なし

使い方:
  python3 scripts/scan-broken.py              # サマリー表示
  python3 scripts/scan-broken.py --all        # 全件詳細
  python3 scripts/scan-broken.py --tsv        # TSV出力（champ_id, opp_id, tier, reason）
"""

import os, re, json, sys
from collections import defaultdict

CHAMP_DIR = os.path.join(os.path.dirname(__file__), "..", "champions")
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")
MECHANICS_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "champion-mechanics.json")

DATA = json.load(open(DATA_FILE))
MECHANICS = json.load(open(MECHANICS_FILE))

cmap = {c["id"]: c for c in DATA["champions"]}
ja_to_id = {c["ja"]: c["id"] for c in DATA["champions"]}
en_to_id = {c["en"]: c["id"] for c in DATA["champions"]}

APHELIOS_WEAPON_NAMES = {"カリバルム", "セヴェラム", "インフェルナム", "クレッシェンダム", "タルサ"}

def get_skills(champ_id):
    """チャンプのスキル名→キーマップを返す（形態変化は両名を登録）"""
    c = cmap.get(champ_id, {})
    result = {}
    for s in c.get("skills", []):
        key = s["key"]
        for name in s["name"].split("/"):
            # ｢｣（隅付き括弧）を除去してマッチ精度を上げる（例: jhin）
            name = name.strip().replace("｢", "").replace("｣", "")
            if name:
                result[name] = key
    # aphelios は武器名で書くのが正しい表記 → 武器名をスキル名として扱う
    if champ_id == "aphelios":
        for w in APHELIOS_WEAPON_NAMES:
            result[w] = "Q"
    return result

def parse_entries(champ_id):
    path = os.path.join(CHAMP_DIR, champ_id, "matchups.md")
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        content = f.read()
    entries = []
    for m in re.finditer(r'^## vs (.+?)（(.+?)）\n(.*?)(?=\n## |\Z)', content, re.MULTILINE | re.DOTALL):
        opp_ja = m.group(1).strip()
        opp_en = m.group(2).strip()
        body = m.group(3)
        opp_id = ja_to_id.get(opp_ja) or en_to_id.get(opp_en)
        entries.append({
            "champ_id": champ_id,
            "opp_ja": opp_ja,
            "opp_en": opp_en,
            "opp_id": opp_id,
            "body": body,
        })
    return entries

# ============================================================
# ルール定義
# ============================================================

# --- [broken] Rule B1: 視点逆転 — 対面スキル名を主チャンプの行動として使用 ---
ACTION_PATTERN = re.compile(r'[）)]で(ポーク|削|当て|ハラス|突進|捕捉|起動|発動|追撃|攻撃|仕掛け|飛び|抑制|スロー|キャッチ)')
SKILL_KEY_INLINE = re.compile(r'([PQWER])（([^）]+)）')

def rule_b1_perspective(entry, champ_skills, opp_skills):
    for m in re.finditer(r'([PQWER])（([^）]+)）' + ACTION_PATTERN.pattern, entry["body"]):
        key, name = m.group(1), m.group(2)
        if name in opp_skills and name not in champ_skills:
            return f"視点逆転: {key}（{name}）は対面スキルだが主チャンプの行動として記述"
    return None

# --- [broken] Rule B3: verdict行（勝率約N%）が存在しない ---
FULL_VERDICT_PAT = re.compile(r'^- \*\*(?:有利|やや有利|五分|やや不利|不利)（勝率約', re.MULTILINE)

def rule_b3_no_verdict(entry):
    if len(entry["body"]) < 200:
        return None
    if not FULL_VERDICT_PAT.search(entry["body"]):
        return "verdict行（勝率約N%）が存在しない"
    return None

# --- [broken] Rule B2: 主チャンプのスキルが一つも出てこない ---
def rule_b2_no_champ_skills(entry, champ_skills, opp_skills):
    if not champ_skills:
        return None
    found = any(name in entry["body"] for name in champ_skills)
    if not found and len(entry["body"]) > 200:
        return "主チャンプのスキル名が本文に一切登場しない"
    return None

# --- [quality] Rule Q1: スキル名フォーマット逆転 ---
SKILL_FORMAT_REVERSED = re.compile(r'([^\s（(、。]{2,15})（([PQWER])）')

def rule_q1_format(entry, champ_skills, opp_skills):
    all_skills = set(champ_skills) | set(opp_skills)
    issues = []
    for m in SKILL_FORMAT_REVERSED.finditer(entry["body"]):
        name, key = m.group(1), m.group(2)
        if name in all_skills:
            issues.append(f"フォーマット逆転: 「{name}（{key}）」→「{key}（{name}）」")
    return issues

# --- [quality] Rule Q2: 固有メカニクス混入（champion-mechanics.jsonから参照）---
def rule_q2_wrong_mechanic(entry):
    issues = []
    opp_id = entry.get("opp_id", "") or ""
    champ_id = entry["champ_id"]
    for mechanic, owners in MECHANICS.items():
        if mechanic.startswith("_"):
            continue
        if not owners:
            continue
        if mechanic in entry["body"]:
            if opp_id not in owners and champ_id not in owners:
                issues.append(f"固有メカニクス混入: 「{mechanic}」({'/'.join(owners)}の固有)")
    return issues

# --- [quality] Rule Q4: guide.md の得意/苦手とmatchups.md のverdictが矛盾 ---
FAVORABLE_VERDICTS  = {"有利", "やや有利"}
UNFAVORABLE_VERDICTS = {"不利", "やや不利"}
VERDICT_PAT = re.compile(r'^- \*\*(.+?)（勝率約')

def _parse_guide_matchups(champ_id):
    """guide.md から 得意/苦手マッチアップのチャンプ名セットを返す"""
    path = os.path.join(CHAMP_DIR, champ_id, "guide.md")
    if not os.path.isfile(path):
        return set(), set()
    with open(path) as f:
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

_guide_cache = {}

def rule_q4_guide_verdict(entry):
    champ_id = entry["champ_id"]
    if champ_id not in _guide_cache:
        _guide_cache[champ_id] = _parse_guide_matchups(champ_id)
    favorable, unfavorable = _guide_cache[champ_id]

    opp_ja = entry["opp_ja"]
    verdict_m = re.search(r'^- \*\*(.+?)（勝率約', entry["body"], re.MULTILINE)
    if not verdict_m:
        return None
    verdict = verdict_m.group(1)

    if opp_ja in favorable and verdict in UNFAVORABLE_VERDICTS:
        return f"guide.md「得意」なのにmatchups.md verdict=「{verdict}」({opp_ja})"
    if opp_ja in unfavorable and verdict in FAVORABLE_VERDICTS:
        return f"guide.md「苦手」なのにmatchups.md verdict=「{verdict}」({opp_ja})"
    return None

# --- [quality] Rule Q3: 概要行にCS/分の数値統計 ---
CS_STAT = re.compile(r'\d+\.\d+/分')

def rule_q3_cs_stat(entry):
    first_line = entry["body"].split("\n")[0]
    if CS_STAT.search(first_line):
        return f"概要にCS/分の数値統計"
    return None

# --- [minor] Rule M1: 残存表記揺れ ---
NOTATION_CHECKS = [
    (re.compile(r'\bLH\b'),                    "LH→CS"),
    (re.compile(r'第2の風|セカンドウィンド'),   "第2の風→息継ぎ"),
    (re.compile(r'オラクルのエリクサー'),        "オラクルのエリクサー→オラクルレンズ"),
    (re.compile(r'砲形態'),                    "砲形態→キャノンモード"),
    (re.compile(r'槌形態'),                    "槌形態→ハンマーモード"),
    (re.compile(r'プレート金(?!貨)'),           "プレート金→プレートゴールド"),
    (re.compile(r'コンカー'),                  "コンカー→征服者"),
    (re.compile(r'フリートフット(?!ワーク)'),   "フリートフット→フリートフットワーク"),
]

def rule_m1_notation(entry):
    issues = []
    for pattern, label in NOTATION_CHECKS:
        if pattern.search(entry["body"]):
            issues.append(label)
    return issues

# --- [minor] Rule M2: 翻訳アーティファクト ---
ARTIFACTS = ["コンビネーション取引", "スプリットプッシュ取引", "ダメージ取引交換"]

def rule_m2_artifact(entry):
    return [f"翻訳アーティファクト: 「{p}」" for p in ARTIFACTS if p in entry["body"]]

# --- [minor] Rule M3: 処刑ライン誤記 ---
AMBESSA_R_BAD = re.compile(
    r'公開処刑.{0,50}(?:HP\d+%以下で(?:処刑|刑執行|確定)|HP\d+%処刑ライン|処刑ラインは\d+%|即処刑|確定処刑|刑執行可能)'
)

def rule_m3_execute(entry):
    issues = []
    if re.search(r'デスグラインダー[^。]{0,30}HP30%', entry["body"]):
        issues.append("デスグラインダー処刑ラインHP30%→HP25%")
    # アンベッサR（公開処刑）は処刑効果なし: 対面視点・主チャンプ視点の両方を検出
    if (entry.get("opp_id") == "ambessa" or entry["champ_id"] == "ambessa") \
            and AMBESSA_R_BAD.search(entry["body"]):
        issues.append("アンベッサR（公開処刑）に処刑ライン/HP%記述（処刑効果なし）")
    return issues

# ============================================================
# tiering ロジック
# ============================================================

def classify(entry, champ_skills, opp_skills):
    """(tier, [reasons]) を返す。tier: broken/quality/minor/ok"""
    # broken チェック（構造的に壊れてる）
    r = rule_b1_perspective(entry, champ_skills, opp_skills)
    if r:
        return "broken", [r]
    r = rule_b3_no_verdict(entry)
    if r:
        return "broken", [r]

    # quality チェック（内容が悪い・旧スキル名・フォーマット違反）
    quality_issues = []
    r = rule_b2_no_champ_skills(entry, champ_skills, opp_skills)
    if r:
        quality_issues.append(r)  # 公式スキル名不在 → qualityに格下げ
    quality_issues += rule_q1_format(entry, champ_skills, opp_skills)
    quality_issues += rule_q2_wrong_mechanic(entry)
    r = rule_q3_cs_stat(entry)
    if r:
        quality_issues.append(r)
    r = rule_q4_guide_verdict(entry)
    if r:
        quality_issues.append(r)
    if quality_issues:
        return "quality", quality_issues

    # minor チェック
    minor_issues = []
    minor_issues += rule_m1_notation(entry)
    minor_issues += rule_m2_artifact(entry)
    minor_issues += rule_m3_execute(entry)
    if minor_issues:
        return "minor", minor_issues

    return "ok", []

# ============================================================
# メイン
# ============================================================

tsv_mode = "--tsv" in sys.argv
all_mode = "--all" in sys.argv

# --champ <id> で単一チャンプのみスキャン（add-matchups.sh の品質チェック用）
champ_filter = None
if "--champ" in sys.argv:
    idx = sys.argv.index("--champ")
    champ_filter = sys.argv[idx + 1]

if tsv_mode:
    print("champ_id\topp_id\topp_ja\ttier\treasons")

counts = defaultdict(int)
results = []

for c in sorted(DATA["champions"], key=lambda x: x["id"]):
    champ_id = c["id"]
    if champ_filter and champ_id != champ_filter:
        continue
    champ_skills = get_skills(champ_id)
    for entry in parse_entries(champ_id):
        opp_id = entry.get("opp_id", "") or ""
        opp_skills = get_skills(opp_id) if opp_id else {}
        tier, reasons = classify(entry, champ_skills, opp_skills)
        counts[tier] += 1
        if tier != "ok":
            results.append((champ_id, opp_id, entry["opp_ja"], tier, reasons))
            if tsv_mode:
                print(f"{champ_id}\t{opp_id}\t{entry['opp_ja']}\t{tier}\t{'; '.join(reasons)}")

total = sum(counts.values())

if not tsv_mode:
    print("=== matchups.md スキャン結果 ===\n")
    print(f"総エントリ数: {total}")
    for tier in ["broken", "quality", "minor", "ok"]:
        pct = counts[tier] / total * 100
        print(f"  {tier:8s}: {counts[tier]:4d}件 ({pct:.1f}%)")

    print("\n=== tier別サマリー ===")
    for tier in ["broken", "quality", "minor"]:
        tier_results = [(c, o, oj, r) for c, o, oj, t, r in results if t == tier]
        if not tier_results:
            continue
        print(f"\n[{tier}] {len(tier_results)}件")
        by_champ = defaultdict(list)
        for c, o, oj, r in tier_results:
            by_champ[c].append((oj, r))
        for champ_id, items in sorted(by_champ.items(), key=lambda x: -len(x[1]))[:10]:
            print(f"  {champ_id} ({len(items)}件):", ", ".join(oj for oj, _ in items[:5]),
                  ("..." if len(items) > 5 else ""))

    if all_mode:
        print("\n=== 全件詳細 ===")
        for c, o, oj, tier, reasons in results:
            print(f"[{tier}] {c}/matchups.md vs {oj}: {'; '.join(reasons)}")
