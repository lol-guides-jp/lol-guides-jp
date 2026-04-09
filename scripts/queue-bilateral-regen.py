#!/usr/bin/env python3
"""queue-bilateral-regen.py
両方向エントリが既に存在するペアを missing-*.txt の末尾に追記する。
add-matchups.sh --force で再生成することで、同一 research から両方向を生成し直す。

Usage:
  python3 scripts/queue-bilateral-regen.py [--dry-run]
"""

import os, glob, re, json, sys

PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")
CHAMPS_DIR = os.path.join(PROJECT_DIR, "champions")
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")

data = json.load(open(os.path.join(PROJECT_DIR, "docs/data.json")))
en_to_id  = {c["en"].lower().replace(" ","").replace("'","").replace(".",""):c["id"] for c in data["champions"]}
id_to_info = {c["id"]: c for c in data["champions"]}

ROLE_FILE = {
    "トップレーン": "missing-トップ.txt",
    "ジャングル":   "missing-ジャング.txt",
    "ミッドレーン": "missing-ミッド.txt",
    "ADC":          "missing-ADC.txt",
    "サポート":     "missing-サポート.txt",
}

dry_run = "--dry-run" in sys.argv

def get_matchup_opps(matchup_file):
    """matchups.md から {opp_id: opp_en} を返す"""
    result = {}
    for line in open(matchup_file).read().splitlines():
        m = re.match(r"^## vs .+（(.+)）", line)
        if m:
            en_raw = m.group(1)
            key = en_raw.lower().replace(" ","").replace("'","").replace(".","")
            cid = en_to_id.get(key)
            if cid:
                result[cid] = en_raw
    return result

def get_type_hint(champ_id, opp_ja):
    """guide.md の得意/苦手からヒントを取得"""
    guide = os.path.join(CHAMPS_DIR, champ_id, "guide.md")
    if not os.path.isfile(guide):
        return ""
    content = open(guide).read()
    fav, unfav = set(), set()
    cur = None
    for line in content.splitlines():
        if "得意マッチアップ" in line: cur = "fav"
        elif "苦手マッチアップ" in line: cur = "unfav"
        elif line.startswith("## "): cur = None
        elif cur and line.startswith("- **"):
            m = re.match(r"- \*\*(.+?)\*\*", line)
            if m:
                (fav if cur == "fav" else unfav).add(m.group(1))
    if opp_ja in fav: return "得意"
    if opp_ja in unfav: return "苦手"
    return ""

# 全チャンプのエントリを収集
champ_opps = {}
for mf in sorted(glob.glob(f"{CHAMPS_DIR}/*/matchups.md")):
    cid = os.path.basename(os.path.dirname(mf))
    champ_opps[cid] = get_matchup_opps(mf)

# 既に missing に入っているペアを収集（重複追記を防ぐ）
already_missing = set()
for mf in glob.glob(f"{SCRIPTS_DIR}/missing-*.txt"):
    for line in open(mf).read().splitlines():
        if line.strip():
            parts = line.split("|")
            if len(parts) >= 3:
                already_missing.add((parts[0], parts[2]))

# 両方向揃ってるペアを抽出して role 別に整理
to_add = {}  # role_file -> [line, ...]
seen = set()
count = 0

for a, a_opps in champ_opps.items():
    a_info = id_to_info.get(a)
    if not a_info:
        continue
    role = a_info.get("role", "")
    role_file = ROLE_FILE.get(role)
    if not role_file:
        continue

    for b, b_en in a_opps.items():
        if (a, b) in seen or (b, a) in seen:
            continue
        seen.add((a, b))

        b_has_a = a in champ_opps.get(b, {})
        if not b_has_a:
            continue  # 片方だけ → 対象外

        if (a, b) in already_missing:
            continue  # 既にmissingに入ってる

        a_ja  = a_info["ja"]
        b_info = id_to_info.get(b, {})
        b_ja  = b_info.get("ja", b)
        type_hint = get_type_hint(a, b_ja)

        line = f"{a}|{a_ja}|{b}|{b_ja}|{b_en}|{type_hint}|"
        to_add.setdefault(role_file, []).append(line)
        count += 1

print(f"追記対象: {count} ペア")
for rf, lines in sorted(to_add.items()):
    print(f"  {rf}: {len(lines)} 件")

if dry_run:
    print("\n[DRY-RUN] ファイルへの書き込みをスキップ")
    for rf, lines in sorted(to_add.items()):
        for l in lines[:3]:
            print(f"  {l}")
        if len(lines) > 3:
            print(f"  ... 他 {len(lines)-3} 件")
    sys.exit(0)

# 末尾に追記
for rf, lines in to_add.items():
    path = os.path.join(SCRIPTS_DIR, rf)
    with open(path, "a") as f:
        for line in lines:
            f.write(line + "\n")
    print(f"追記完了: {path} (+{len(lines)}件)")
