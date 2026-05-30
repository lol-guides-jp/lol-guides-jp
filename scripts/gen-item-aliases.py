#!/usr/bin/env python3
"""gen-item-aliases.py — アイテム名の「誤表記 → 公式日本語名」辞書を Data Dragon から生成

目的:
  対面ガイド本文のアイテム名は生成AI(Sonnet)が書いており、英語ソース(Mobalytics等)
  からの英語直訳カタカナ（例: 「ブレード・オブ・ザ・ルインドキング」）が混入する。
  スキル名が build-json.js + lint-matchup.py で守られているのと同じ思想で、
  アイテム名にも「公式名マスタ → lint 正規化」の防御を与える。

  本スクリプトは Data Dragon (ja_JP/en_US) の item.json から
  「英語名 → 公式日本語名」マップを生成し、観測済みの誤表記 SEED と合体して
  scripts/item-aliases.json を出力する。lint-matchup.py がこれを読んで自動修正する。

使い方:
  python3 scripts/gen-item-aliases.py            # item-aliases.json を再生成
  python3 scripts/gen-item-aliases.py --dry-run  # 生成内容を stdout に出すだけ（書き込まない）

再生成は冪等。Data Dragon のバージョンが上がってアイテム名が変わっても再実行で追従する。
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "item-aliases.json")

# build-json.js と同じく Data Dragon バージョンは動的取得。fetch 失敗時の fallback。
FALLBACK_VERSION = "16.11.1"

# --- 観測済み誤表記 SEED ---
# カタカナ直訳は「人間/モデルがどう間違えるか」なので機械生成できない。
# Sonnet レビューや先輩の指摘で見つかった誤表記をここに蓄積する（learn サイクル）。
# 形式: 誤表記 → 公式日本語名（Data Dragon ja_JP に一致させること）
#       reason を明示したい場合は (公式名, 理由) のタプルで書く（旧名・連結形など直訳以外の誤り用）。
# 2026-05-30: 「ブレード・オブ・ザ・ルインドキング」を11ファイル36箇所で観測（先輩指摘）。
# 2026-05-30: 旧名「サンファイアケープ」(→サンファイア イージスへ改名) と
#             連結形「ヴォイドスタッフ」(区切りスペース欠落) を lint 訳語型チェックで観測。
SEED_ALIASES = {
    "ブレード・オブ・ザ・ルインドキング": "ルインドキング ブレード",
    "ブレードオブザルインドキング": "ルインドキング ブレード",
    "サンファイアケープ": ("サンファイア イージス", "旧アイテム名。改名後の公式名は「サンファイア イージス」"),
    "ヴォイドスタッフ": ("ヴォイド スタッフ", "区切りスペース欠落。公式は半角スペース区切り「ヴォイド スタッフ」"),
}

# 英語名ルールの誤爆防止しきい値。
# 短い1語名（Cull/Zeal/Boots 等）は日本語本文の他語と衝突しうるため、
# 「複数語（空白を含む）」または「8文字以上」のみを英語名ルールに採用する。
MIN_EN_NAME_LEN = 8


def fetch_version() -> str:
    """Data Dragon の最新バージョンを取得。失敗時は FALLBACK_VERSION。"""
    try:
        url = "https://ddragon.leagueoflegends.com/api/versions.json"
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.load(r)[0]
    except Exception as e:  # noqa: BLE001 — fallback で続行するため握りつぶす
        print(f"WARN: versions.json 取得失敗 ({e})。fallback {FALLBACK_VERSION} を使う", file=sys.stderr)
        return FALLBACK_VERSION


def fetch_items(version: str, lang: str) -> dict:
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/{lang}/item.json"
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)["data"]


def is_sr_purchasable(item: dict) -> bool:
    """サモナーズリフト(map 11)で購入可能な実アイテムだけを辞書対象にする。
    consumable・trinket・廃止アイテム・特殊マップ専用を除外して辞書ノイズを減らす。"""
    if not item.get("gold", {}).get("purchasable", False):
        return False
    if item.get("gold", {}).get("total", 0) <= 0:
        return False
    # maps は {"11": true, ...} 形式。SR(11) で使えないものは除外。
    if not item.get("maps", {}).get("11", False):
        return False
    return True


def build_en_rules(ja: dict, en: dict) -> list[dict]:
    """英語名 → 公式日本語名 の置換ルールを生成。
    本文に英字のアイテム名が混入したときの保険（カタカナ直訳の主防御は SEED）。"""
    rules = []
    seen_patterns = set()
    for item_id, en_item in en.items():
        ja_item = ja.get(item_id)
        if not ja_item:
            continue
        if not is_sr_purchasable(en_item):
            continue
        en_name = (en_item.get("name") or "").strip()
        ja_name = (ja_item.get("name") or "").strip()
        if not en_name or not ja_name:
            continue
        if not en_name.isascii():
            continue
        # 誤爆防止: 複数語 もしくは 一定長以上のみ採用
        if " " not in en_name and len(en_name) < MIN_EN_NAME_LEN:
            continue
        # 英語名と日本語名が同一になることはないが念のため
        if en_name == ja_name:
            continue
        # the/The の大小揺れを両対応（本文では小文字 the で書かれがち）
        variants = {en_name}
        if " The " in en_name:
            variants.add(en_name.replace(" The ", " the "))
        for pat in variants:
            if pat in seen_patterns:
                continue
            seen_patterns.add(pat)
            rules.append({
                "pattern": pat,
                "replacement": ja_name,
                "reason": f"アイテム英語名「{pat}」は公式日本語名「{ja_name}」に統一",
                "source": "ddragon",
            })
    return rules


def build_spacing_variants(ja: dict, en: dict) -> list[dict]:
    """公式名の区切り揺れ（中黒・全角スペース）を検出するルール。
    公式は半角スペース区切り（「ルインドキング ブレード」）だが、本文では中黒「・」が
    使われがち（例: 「ドラン・ブレード」）。中黒/全角スペース版は誤爆がほぼ無いので機械生成する。
    詰め版（スペース除去）は他語との衝突リスクが高いため、ここでは生成しない。"""
    rules = []
    seen = set()
    for item_id, ja_item in ja.items():
        en_item = en.get(item_id)
        if not en_item or not is_sr_purchasable(en_item):
            continue
        name = (ja_item.get("name") or "").strip()
        if " " not in name:
            continue
        tokens = name.split(" ")
        # 各トークン2文字以上（短語の誤爆回避）
        if any(len(t) < 2 for t in tokens):
            continue
        for sep in ("・", "　"):  # 中黒(U+30FB), 全角スペース(U+3000)
            variant = sep.join(tokens)
            if variant == name or variant in seen:
                continue
            seen.add(variant)
            rules.append({
                "pattern": variant,
                "replacement": name,
                "reason": f"アイテム名の区切り揺れ。公式は半角スペース区切り「{name}」",
                "source": "spacing",
            })
    return rules


def build_seed_rules(ja_names: set[str]) -> list[dict]:
    """SEED 誤表記ルールを生成。replacement が公式名リストに無ければ警告（typo 検知）。"""
    rules = []
    for wrong, val in SEED_ALIASES.items():
        # value は公式名のみ（直訳カタカナの既定 reason）か (公式名, 理由) のタプル。
        if isinstance(val, tuple):
            correct, reason = val
        else:
            correct, reason = val, f"英語直訳カタカナ。公式名は「{val}」"
        if correct not in ja_names:
            print(
                f"WARN: SEED の正名「{correct}」が Data Dragon 公式名に見つからない。"
                f"表記を確認すること（誤: {wrong}）",
                file=sys.stderr,
            )
        rules.append({
            "pattern": wrong,
            "replacement": correct,
            "reason": reason,
            "source": "seed",
        })
    return rules


def main():
    dry_run = "--dry-run" in sys.argv[1:]

    version = fetch_version()
    ja = fetch_items(version, "ja_JP")
    en = fetch_items(version, "en_US")
    ja_names = {(v.get("name") or "").strip() for v in ja.values()}

    seed_rules = build_seed_rules(ja_names)
    spacing_rules = build_spacing_variants(ja, en)
    en_rules = build_en_rules(ja, en)

    # 優先順位: SEED（手動の確定誤表記）> spacing（区切り揺れ）> en（英語名）。
    # 後段の pattern が前段と重複したら前段を優先（後段から除外）。
    used = {r["pattern"] for r in seed_rules}
    spacing_rules = [r for r in spacing_rules if r["pattern"] not in used]
    used |= {r["pattern"] for r in spacing_rules}
    en_rules = [r for r in en_rules if r["pattern"] not in used]
    aliases = seed_rules + spacing_rules + en_rules

    payload = {
        "_comment": "gen-item-aliases.py が生成。手で編集しない（誤表記の追加は SEED_ALIASES へ）。",
        "ddragon_version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(aliases),
        "aliases": aliases,
    }
    out = json.dumps(payload, ensure_ascii=False, indent=2)

    if dry_run:
        print(out)
        print(
            f"\n[dry-run] version={version} / SEED={len(seed_rules)}件 / "
            f"英語名={len(en_rules)}件 / 合計={len(aliases)}件",
            file=sys.stderr,
        )
        return

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(out + "\n")
    print(
        f"OK: {OUTPUT_PATH} に {len(aliases)}件 出力 "
        f"(version={version} / SEED={len(seed_rules)} / 英語名={len(en_rules)})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
