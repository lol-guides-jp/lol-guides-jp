#!/usr/bin/env python3
"""replace-section.py
matchups.md の特定セクションを dispatch_ops JSON の内容で置き換える

Usage:
  echo "$ops_json" | python3 scripts/replace-section.py <champ_id> <opp_ja> <opp_en>

  - ops_json は write-matchup / rewrite-matchup が返す dispatch_ops 形式
  - セクションが見つからない場合はファイル末尾にフォールバック追記
"""

import os, re, json, sys

CHAMP_DIR = os.path.join(os.path.dirname(__file__), "..", "champions")

champ_id = sys.argv[1]
opp_ja   = sys.argv[2]
opp_en   = sys.argv[3]

ops = json.load(sys.stdin)
new_content = ops[0]["content"]  # "\n## vs X（Y）\n..." 形式

path = os.path.join(CHAMP_DIR, champ_id, "matchups.md")
if not os.path.isfile(path):
    print(f"ERROR: {path} が見つかりません", file=sys.stderr)
    sys.exit(1)

content = open(path).read()
header  = f"## vs {opp_ja}（{opp_en}）"
pat = re.compile(r'^' + re.escape(header) + r'\n.*?(?=\n## |\Z)', re.MULTILINE | re.DOTALL)

clean = new_content.lstrip('\n')  # 先頭の余分な改行を除去

if pat.search(content):
    result = pat.sub(clean, content)
    open(path, 'w').write(result)
    print(f"replaced: {champ_id}/matchups.md  vs {opp_ja}")
else:
    open(path, 'a').write(f"\n{clean}")
    print(f"appended (fallback): {champ_id}/matchups.md  vs {opp_ja}")
