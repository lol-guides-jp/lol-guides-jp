#!/usr/bin/env python3
"""missing-matchups.jsonをロール別にテキスト化"""
import json

d = json.load(open("scripts/missing-matchups.json"))
by_role = {}
for cid, info in d.items():
    role = info["role"]
    if role not in by_role:
        by_role[role] = []
    by_role[role].append((cid, info))

for role, champs in by_role.items():
    lines = []
    for cid, info in sorted(champs):
        for m in info["missing"]:
            lines.append(f"{cid}|{info['ja']}|{m['opp_id']}|{m['opp_ja']}|{m['opp_en']}|{m['type']}|{m['summary']}")
    fname = f"scripts/missing-{role.replace('レーン','').replace('ル','')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(lines))
    print(f"{fname}: {len(lines)}件")
