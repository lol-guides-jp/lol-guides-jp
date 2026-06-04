#!/usr/bin/env python3
"""guide.mdの得意/苦手がmatchups.mdでカバーされているかチェック"""

import json

DATA = json.load(open("docs/data.json", encoding="utf-8"))

missing_total = 0
champs_with_missing = 0

for c in DATA["champions"]:
    # メイン対面（matchups.md 由来）= matchupsByRole のメインレーン。
    # matchups フラットフィールドは matchupsByRole に統合され data.json から除外された（2026-06-04）。
    main_role = c.get("mainRole") or c.get("role")
    main_matchups = c.get("matchupsByRole", {}).get(main_role, [])
    matchup_ids = set(m["opponentId"] for m in main_matchups)

    missing = []
    for entry in c["favorableMatchups"] + c["unfavorableMatchups"]:
        name = entry["name"]
        opp = next((x for x in DATA["champions"] if x["ja"] == name or x["en"] == name), None)
        if opp and opp["id"] not in matchup_ids:
            missing.append(name)

    if missing:
        champs_with_missing += 1
        missing_total += len(missing)
        print(f"{c['ja']}: matchups.mdに未収録 → {', '.join(missing)}")

print(f"\n合計: {champs_with_missing}体に{missing_total}件の未カバー対面")
