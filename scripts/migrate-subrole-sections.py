#!/usr/bin/env python3
"""migrate-subrole-sections.py
既存のフラットな matchups-sub.md（「## vs X」が並ぶだけ）を、ロールセクション構造
（「## {role}」→「### vs X」）に移行する救済スクリプト（2026-06-04 構造改修）。

背景:
  サブロール対面の初期実装は matchups-sub.md をフラットリストで書いていたため、
  どのレーンの対面か区別できなかった。複数サブ持ち（brand=MID/ADC 等）が出ると破綻する。
  構造改修でレーンセクション化したので、生成済み21体を新フォーマットへ移行する。

レーン推定（C vs O の対面が「どのレーンで起きたか」）:
  生成主体（A面）基準で決める。A面 = matchups-sub.md のエントリ数が多い側。
  サブロール対面は A面チャンプが自分のサブレーンで全相手と総当たりして生成され、
  各相手（B面）には「vs A」が1件だけ書き戻される。だから:
    - 主体 = エントリ数が多い側（イレリア20件 vs 相手1件 → イレリアが主体）
    - レーン = 主体のサブロール（生成時のレーンを最も忠実に表す）
  ロールはパッチ追従（refresh-subrole-targets.py）で変動するが、エントリ数ベースの
  主体判定はドリフトの影響を受けない（heimer のように生成後にサブロールが
  変わったケースでも、生成時レーン＝主体イレリアの MID を正しく拾える）。

  主体のサブロールが複数（将来の brand=MID/ADC 等）なら相手の所属レーンで絞る。
  それでも絞れなければスキップして手動確認に回す。

レーン基準マージ方針:
  B面エントリ（相手チャンプ側に書かれた「vs イレリア」等）も、起きたレーンで分類する。
  そのレーンが相手にとってメインロールなら、build-json.js が matchups.md と同じ
  matchupsByRole[role] に統合する。移行はファイルをセクション化するだけでよい。

Usage:
  python3 scripts/migrate-subrole-sections.py            # dry-run（差分プレビューのみ）
  python3 scripts/migrate-subrole-sections.py --apply    # 実書き込み
"""
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CHAMPIONS_DIR = os.path.join(PROJECT_DIR, "champions")
DATA_FILE = os.path.join(PROJECT_DIR, "docs", "data.json")

sys.path.insert(0, SCRIPT_DIR)
from sub_matchup_io import ROLE_NAMES, opp_header, serialize  # noqa: E402


def load_champ_roles():
    """id -> {mainRole, subRoles, ja, id} のマップを data.json から作る。"""
    data = json.load(open(DATA_FILE, encoding="utf-8"))
    m = {}
    for c in data["champions"]:
        m[c["id"]] = {
            "id": c["id"],
            "ja": c.get("ja"),
            "mainRole": c.get("mainRole") or c.get("role"),
            "subRoles": c.get("subRoles") or [],
        }
    return m


def parse_flat(content: str):
    """フラット matchups-sub.md を [(opp_ja, opp_en, block_text), ...] に分解する。"""
    blocks = re.split(r"(?m)^(?=## vs )", content)
    out = []
    for b in blocks:
        b = b.strip()
        if not b.startswith("## vs "):
            continue
        m = re.match(r"^## vs (.+?)（(.+?)）", b)
        if not m:
            continue
        out.append((m.group(1).strip(), m.group(2).strip(), b))
    return out


def is_already_sectioned(content: str) -> bool:
    """「## {role}」見出しが既にあるか（移行済み判定）。"""
    for role in ROLE_NAMES:
        if re.search(r"(?m)^## " + re.escape(role) + r"\s*$", content):
            return True
    return False


def name_to_id(roles_map):
    m = {}
    for cid, c in roles_map.items():
        if c["ja"]:
            m[c["ja"]] = cid
    return m


def infer_lane(c_id, opp_ja, opp_en, roles_map, n2id, counts):
    """対面 (c_id vs opp) のレーンを推定する。(lane, reason) を返す。lane=None なら曖昧。

    生成主体（matchups-sub エントリ数が多い側）のサブロールをレーンとする。
    主体のサブロールが複数なら相手の所属レーンで絞る。
    """
    c = roles_map[c_id]
    opp_id = n2id.get(opp_ja) or opp_en.lower()
    o = roles_map.get(opp_id)
    if o is None:
        return None, f"相手 {opp_ja}({opp_en}) を data.json で解決できず"

    # A面（生成主体）= エントリ数が多い側。同数ならサブロールを持つ側を優先。
    c_cnt, o_cnt = counts.get(c_id, 0), counts.get(opp_id, 0)
    if c_cnt != o_cnt:
        protag = c if c_cnt > o_cnt else o
    elif c["subRoles"] and not o["subRoles"]:
        protag = c
    elif o["subRoles"] and not c["subRoles"]:
        protag = o
    else:
        protag = c  # 同数かつ両方サブ持ち → C 基準で進め、下で相手レーン絞り込みに委ねる
    other = o if protag is c else c

    protag_subs = protag["subRoles"]
    if len(protag_subs) == 1:
        return protag_subs[0], f"protagonist={protag['id']} sub"
    if len(protag_subs) > 1:
        other_roles = {other["mainRole"]} | set(other["subRoles"])
        narrowed = [r for r in protag_subs if r in other_roles]
        if len(narrowed) == 1:
            return narrowed[0], f"protagonist={protag['id']} sub∩相手レーン"
        return None, f"主体 {protag['id']} のサブ複数 {protag_subs} を相手レーンで絞れず"

    # 主体にサブロールが無い（サブ卒業後の orphan）→ 共通レーンで救済
    common = ({c["mainRole"]} | set(c["subRoles"])) & ({o["mainRole"]} | set(o["subRoles"]))
    if len(common) == 1:
        return next(iter(common)), "common-fallback(orphan)"
    return None, f"主体にサブ無し・common 曖昧: {sorted(common)}"


def order_roles(role_keys, main_role):
    """セクション順: メインロールを先頭、残りを ROLE_NAMES 順に。"""
    ordered = []
    if main_role in role_keys:
        ordered.append(main_role)
    for r in ROLE_NAMES:
        if r in role_keys and r not in ordered:
            ordered.append(r)
    return ordered


def main():
    apply = "--apply" in sys.argv
    roles_map = load_champ_roles()
    n2id = name_to_id(roles_map)

    paths = sorted(
        p
        for p in (
            os.path.join(CHAMPIONS_DIR, d, "matchups-sub.md")
            for d in os.listdir(CHAMPIONS_DIR)
        )
        if os.path.isfile(p)
    )

    # 生成主体判定用に、各チャンプの matchups-sub エントリ数を先に数える。
    counts = {}
    for path in paths:
        cid = os.path.basename(os.path.dirname(path))
        counts[cid] = len(parse_flat(open(path, encoding="utf-8").read()))

    total = migrated = skipped = flagged = 0
    for path in paths:
        cid = os.path.basename(os.path.dirname(path))
        content = open(path, encoding="utf-8").read()
        total += 1

        if is_already_sectioned(content):
            skipped += 1
            continue
        if cid not in roles_map:
            print(f"FLAG  {cid}: data.json に未登録 → スキップ")
            flagged += 1
            continue

        flat = parse_flat(content)
        if not flat:
            print(f"SKIP  {cid}: 対面ブロックなし")
            skipped += 1
            continue

        by_lane = {}
        ambiguous = []
        for opp_ja, opp_en, block in flat:
            lane, reason = infer_lane(cid, opp_ja, opp_en, roles_map, n2id, counts)
            if lane is None:
                ambiguous.append((opp_ja, reason))
                continue
            by_lane.setdefault(lane, []).append("### vs " + block[len("## vs "):])

        if ambiguous:
            print(f"FLAG  {cid}: レーン推定不能 {ambiguous} → 手動確認（このファイルは未変更）")
            flagged += 1
            continue

        main_role = roles_map[cid]["mainRole"]
        ordered = order_roles(list(by_lane.keys()), main_role)
        sections = [[r, by_lane[r]] for r in ordered]
        new_content = serialize(sections)

        lane_summary = ", ".join(f"{r}:{len(by_lane[r])}件" for r in ordered)
        print(f"MIGR  {cid}: {lane_summary}")

        if apply:
            open(path, "w", encoding="utf-8").write(new_content)
        migrated += 1

    print(
        f"\n===== {'適用' if apply else 'dry-run'}: 対象{total} 移行{migrated} "
        f"スキップ{skipped} 要確認{flagged} ====="
    )
    if not apply and migrated:
        print("※ dry-run です。--apply で実書き込みします。")


if __name__ == "__main__":
    main()
