#!/usr/bin/env python3
"""build-rewrite-input.py
matchups.md の既存エントリを読み取り、rewrite-matchup コマンド用 JSON を stdout に出力する

Usage:
  python3 scripts/build-rewrite-input.py <champ_id> <champ_ja> <opp_id> <opp_ja> <opp_en> <champ_skills> <opp_skills>

  champ_skills / opp_skills: "P:名前,Q:名前,W:名前,E:名前,R:名前" 形式

Exit code:
  0: 正常
  1: エントリが見つからない
"""

import os, re, json, sys

CHAMP_DIR = os.path.join(os.path.dirname(__file__), "..", "champions")

champ_id, champ_ja, opp_id, opp_ja, opp_en, champ_skills, opp_skills = sys.argv[1:]

path = os.path.join(CHAMP_DIR, champ_id, "matchups.md")
if not os.path.isfile(path):
    print(f"ERROR: {path} が見つかりません", file=sys.stderr)
    sys.exit(1)

content = open(path).read()
header = f"## vs {opp_ja}（{opp_en}）"
m = re.search(r'^' + re.escape(header) + r'\n(.*?)(?=\n## |\Z)', content, re.MULTILINE | re.DOTALL)

if not m:
    print(f"ERROR: {champ_id}/matchups.md にエントリが見つかりません: {header}", file=sys.stderr)
    sys.exit(1)

existing_body = m.group(1)

result = {
    "champ_id":      champ_id,
    "champ_ja":      champ_ja,
    "opp_id":        opp_id,
    "opp_ja":        opp_ja,
    "opp_en":        opp_en,
    "existing_body": existing_body,
    "champ_skills":  champ_skills,
    "opp_skills":    opp_skills,
}

print(json.dumps(result, ensure_ascii=False))
