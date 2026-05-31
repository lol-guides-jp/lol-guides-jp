#!/usr/bin/env python3
"""check-new-champions.py

Data Dragon の最新チャンピオン一覧と ddragon-keys.json を差分し、
ローカル未登録（＝新規追加された）チャンピオンを検出して JSON 配列で標準出力に返す。

呼び出し:
  python3 scripts/check-new-champions.py            # 新規があれば JSON 配列、無ければ []
  python3 scripts/check-new-champions.py --names     # 人間向けに新規名だけ表示（差分確認用）

出力（--names なし、新規ありの例）:
  [
    {"id": "yunara", "en": "Yunara", "ja": "ユナラ",
     "tags": ["Marksman"], "ddragonKey": "Yunara",
     "skills": "P(誓い: ...), Q(...), W(...), E(...), R(...)"}
  ]

設計メモ:
- 真実のソースは Data Dragon（versions.json → en_US/ja_JP champion.json）。
- 「未登録」の判定は ddragon-keys.json の **値（公式キー）集合** との差分で行う。
  slug（キー側）ではなく公式キーで突き合わせるのは、slug 表記揺れ（wukong 等）に
  影響されず「実体としてのチャンプ」を一意比較できるため。
- slug 生成は CamelCase → kebab-case + lower。既存170体中159体はこの規則で再現できる。
  規則で導けない例外（公式キーが短縮形/別名のチャンプ）は _SLUG_OVERRIDE に持つ。
  （wukong: 公式キー MonkeyKing / renata-glasc: 公式キー Renata。2026-05-31 実測で確認）
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

PROJECT_DIR = Path("/home/ojita/lol-guides-jp")
KEYS_FILE = PROJECT_DIR / "scripts" / "ddragon-keys.json"

# 公式キー → slug の例外マップ（規則で導けないもの）。
# 規則: CamelCase を kebab-case 化して lower。下記は規則から外れる既知の2体。
# 新規チャンプがこの型（公式キーが短縮形）の場合はここに追記する。
_SLUG_OVERRIDE = {
    "MonkeyKing": "wukong",
    "Renata": "renata-glasc",
}


def http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "lol-guides-jp/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        # チャンク結合してから一括デコード（build-json.js と同じく、境界での
        # マルチバイト文字化けを避けるため）。明示的に utf-8 を指定する。
        return json.loads(r.read().decode("utf-8"))


def to_slug(official_key: str) -> str:
    """公式キー（CamelCase）を slug（kebab-case + lower）に変換する。

    例: AurelionSol -> aurelion-sol / JarvanIV -> jarvan-iv / Yunara -> yunara
    """
    if official_key in _SLUG_OVERRIDE:
        return _SLUG_OVERRIDE[official_key]
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", official_key)   # camelCase 境界
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", s)            # 連続大文字の直後
    return s.lower()


def fetch_skills(version: str, official_key: str) -> str:
    """ja_JP の個別チャンピオンデータから P/Q/W/E/R の正式名と短い説明を組み立てる。"""
    url = (
        f"https://ddragon.leagueoflegends.com/cdn/{version}"
        f"/data/ja_JP/champion/{official_key}.json"
    )
    try:
        data = http_json(url)["data"]
        champ = next(iter(data.values()))
    except Exception as e:  # noqa: BLE001 - スキル取得失敗は致命的でない
        print(f"WARN: {official_key} のスキル取得失敗: {e}", file=sys.stderr)
        return ""

    def clean(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text or "")
        text = text.replace("\n", " ").strip()
        return text[:80]

    parts = []
    p = champ.get("passive", {})
    parts.append(f"P({p.get('name', '')}: {clean(p.get('description', ''))})")
    for key, spell in zip(["Q", "W", "E", "R"], champ.get("spells", [])):
        parts.append(f"{key}({spell.get('name', '')}: {clean(spell.get('description', ''))})")
    return ", ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", action="store_true", help="新規名だけ人間向けに表示")
    args = parser.parse_args()

    versions = http_json("https://ddragon.leagueoflegends.com/api/versions.json")
    version = versions[0]

    official = http_json(
        f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    )["data"]
    official_ja = http_json(
        f"https://ddragon.leagueoflegends.com/cdn/{version}/data/ja_JP/champion.json"
    )["data"]

    known_keys = set(json.loads(KEYS_FILE.read_text(encoding="utf-8")).values())
    new_keys = sorted(set(official.keys()) - known_keys)

    if args.names:
        if not new_keys:
            print("新規チャンピオンなし（ddragon-keys.json は最新）")
            return 0
        print(f"新規チャンピオン {len(new_keys)}体:")
        for k in new_keys:
            print(f"  - {k} ({official_ja.get(k, {}).get('name', '?')}) -> slug: {to_slug(k)}")
        return 0

    result = []
    for key in new_keys:
        result.append({
            "id": to_slug(key),
            "en": official[key]["name"],
            "ja": official_ja.get(key, {}).get("name", official[key]["name"]),
            "tags": official[key].get("tags", []),
            "ddragonKey": key,
            "skills": fetch_skills(version, key),
        })

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
