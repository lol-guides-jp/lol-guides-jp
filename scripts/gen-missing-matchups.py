#!/usr/bin/env python3
"""guide.mdの得意/苦手で未カバーの対面リストをJSON出力"""

import json, os

DATA = json.load(open("docs/data.json"))
CHAMP_DIR = "champions"

missing = {}
for c in DATA["champions"]:
    matchup_ids = set(m["opponentId"] for m in c["matchups"])
    champ_missing = []
    for entry in c["favorableMatchups"] + c["unfavorableMatchups"]:
        name = entry["name"]
        is_fav = entry in c["favorableMatchups"]
        opp = next((x for x in DATA["champions"] if x["ja"] == name or x["en"] == name), None)
        if opp and opp["id"] not in matchup_ids:
            champ_missing.append({
                "opp_id": opp["id"],
                "opp_ja": opp["ja"],
                "opp_en": opp["en"],
                "type": "得意" if is_fav else "苦手",
                "summary": entry["description"]
            })
    if champ_missing:
        missing[c["id"]] = {
            "ja": c["ja"],
            "en": c["en"],
            "role": c["role"],
            "count": len(champ_missing),
            "missing": champ_missing
        }

# 出力
with open("scripts/missing-matchups.json", "w") as f:
    json.dump(missing, f, ensure_ascii=False, indent=2)

total = sum(v["count"] for v in missing.values())
print(f"{len(missing)}体に{total}件の未カバー対面 → scripts/missing-matchups.json")
