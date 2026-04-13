#!/usr/bin/env python3
"""scrape-winrate.py — Lolalytics から対面勝率を取得する

使い方:
  python3 scripts/scrape-winrate.py <champ_slug> <opp_slug>

引数:
  champ_slug, opp_slug: Lolalytics URL スラグ（ddragonKey.lower() ベース）
  ※ スペース・記号を含む en 名をそのまま渡さないこと

出力:
  勝率の数値のみ（例: 46.9）を stdout に出力。取得失敗時は exit 1。

例:
  python3 scripts/scrape-winrate.py aatrox garen
  python3 scripts/scrape-winrate.py tahmkench garen
  # => 46.9
"""

import re
import subprocess
import sys


def scrape_winrate(champ: str, opp: str) -> str:
    """Lolalytics の vs ページから勝率を取得して返す。"""
    url = f"https://lolalytics.com/lol/{champ.lower()}/vs/{opp.lower()}/build/?tier=all"

    result = subprocess.run(
        ["curl", "-s", "--max-time", "10", url],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: curl failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(1)

    html = result.stdout
    if not html:
        print("ERROR: empty response", file=sys.stderr)
        sys.exit(1)

    # "wins against <a href=...>ChampName</a> 46.9% of the time"
    m = re.search(
        r'wins against <a href=[^>]+>[^<]+</a> ([\d.]+)% of the time',
        html,
    )
    if not m:
        print("ERROR: winrate pattern not found in HTML", file=sys.stderr)
        sys.exit(1)

    return m.group(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <champ_en> <opp_en>", file=sys.stderr)
        sys.exit(1)

    winrate = scrape_winrate(sys.argv[1], sys.argv[2])
    print(winrate)
