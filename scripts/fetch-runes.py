#!/usr/bin/env python3
# fetch-runes.py
# Data Dragon から英語→日本語ルーン名マップを取得して runes-ja.json に保存 (L1)
#
# 使い方:
#   python3 scripts/fetch-runes.py
#   python3 scripts/fetch-runes.py --dry-run

import argparse
import json
import sys
import urllib.request
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
OUTPUT = SCRIPTS_DIR / "runes-ja.json"
VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
RUNES_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/{locale}/runesReforged.json"


def fetch_json(url: str) -> object:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; rune-fetcher/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise OSError(f"HTTP {resp.status}: {url}")
        return json.loads(resp.read().decode("utf-8"))


def collect_runes(data: list) -> dict:
    """runesReforged.json から {key: name} の辞書を返す"""
    result = {}
    for path in data:
        for slot in path.get("slots", []):
            for rune in slot.get("runes", []):
                result[rune["key"]] = rune["name"]
        # キーストーン（path直下にも name がある）
        result[path["key"]] = path["name"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Data Dragon からルーン名マップを生成")
    parser.add_argument("--dry-run", action="store_true", help="実際には保存しない")
    args = parser.parse_args()

    print("INFO: バージョン取得中...")
    versions = fetch_json(VERSIONS_URL)
    version = versions[0]
    print(f"INFO: 最新バージョン: {version}")

    print("INFO: en_US ルーンデータ取得中...")
    en_data = fetch_json(RUNES_URL.format(version=version, locale="en_US"))
    en_map = collect_runes(en_data)  # key → English name

    print("INFO: ja_JP ルーンデータ取得中...")
    ja_data = fetch_json(RUNES_URL.format(version=version, locale="ja_JP"))
    ja_map = collect_runes(ja_data)  # key → Japanese name

    # 英語名 → 日本語名のマップを構築
    result = {}
    for key, en_name in en_map.items():
        ja_name = ja_map.get(key)
        if ja_name and en_name != ja_name:
            result[en_name] = ja_name

    print(f"INFO: {len(result)}件のルーン名マップを生成")

    if args.dry_run:
        for en, ja in sorted(result.items()):
            print(f"  {en} → {ja}")
        print(f"[DRY-RUN] 保存先: {OUTPUT}")
        return

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"INFO: 保存完了: {OUTPUT}")


if __name__ == "__main__":
    main()
