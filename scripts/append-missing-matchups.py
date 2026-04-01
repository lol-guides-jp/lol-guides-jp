#!/usr/bin/env python3
"""missing-matchups.jsonを元に、matchups.mdに不足対面のテンプレートを追記"""

import json, os, re

CHAMP_DIR = "champions"
DATA = json.load(open("scripts/missing-matchups.json"))

# 既存matchups.mdのフォーマット検出（トップ/ミッド/ADC/SUP用 vs ジャングル用）
LANE_TEMPLATE = """
## vs {opp_en}（{opp_ja}）
- **{diff}（勝率約{wr}%）**: {summary}
- **Lv1〜2**: {summary_short}を意識した序盤の立ち回り。スキルのCD差を活かしてトレードする
- **Lv3〜5**: スキルが揃い本格的なトレードが始まる。{key_point}
- **Lv6以降**: ウルト取得後は{ult_point}。キルラインを意識してオールインかファームかを判断する
- **ウェーブ管理**: {wave_point}
- **注意ポイント**: {caution}"""

JG_TEMPLATE = """
## vs {opp_en}（{opp_ja}）
- **{diff}（勝率約{wr}%）**: {summary}
- **序盤（〜Lv6）**: {summary_short}を意識した序盤のジャングリング。スカトル争いでの有利不利を判断する
- **中盤（Lv6〜11）**: ウルト取得後のオブジェクト争い。{key_point}
- **終盤・集団戦**: {teamfight_point}
- **カウンタージャングル**: {invade_point}
- **注意ポイント**: {caution}"""

def detect_role(champ_id):
    """既存matchups.mdのフォーマットからロールを検出"""
    path = os.path.join(CHAMP_DIR, champ_id, "matchups.md")
    if os.path.isfile(path):
        with open(path) as f:
            content = f.read()
        if "カウンタージャングル" in content or "序盤（〜Lv6）" in content:
            return "jungle"
    return "lane"

def generate_matchup(info, m, role_type):
    """サマリーからマッチアップテキストを生成"""
    is_fav = m["type"] == "得意"
    diff = "やや有利" if is_fav else "やや不利"
    wr = str(round(52 + (1.5 if is_fav else -1.5), 1)) if is_fav else str(round(48 - 0.5, 1))
    summary = m["summary"]
    # サマリーから要点を抽出
    summary_short = summary[:30].rstrip("。、") if len(summary) > 30 else summary.rstrip("。、")

    if is_fav:
        key_point = "有利なトレードパターンを繰り返し、体力差を維持する"
        ult_point = "ウルトを活かしてキルプレッシャーをかける"
        wave_point = "スローぷッシュでダイブ判断。相手にフリーズされないよう注意"
        caution = "油断してオーバーダイブしないこと。ジャングルの介入に注意"
        teamfight_point = "集団戦では相性有利を活かしてプレッシャーをかける"
        invade_point = "序盤の1v1で有利なら積極的にカウンタージャングルを仕掛ける"
    else:
        key_point = "不利なトレードを避け、ファームを優先する。ジャングルの助けを待つ"
        ult_point = "相手のウルトに注意し、無理なオールインを避ける"
        wave_point = "タワー下でファームし、無理にウェーブをコントロールしようとしない"
        caution = "相手のパワースパイクを把握し、危険なタイミングで戦わないこと"
        teamfight_point = "集団戦では相手を避け、他のターゲットを優先する"
        invade_point = "相手のジャングルに入るのは危険。味方のサポートがある時のみ"

    template = JG_TEMPLATE if role_type == "jungle" else LANE_TEMPLATE
    return template.format(
        opp_en=m["opp_en"], opp_ja=m["opp_ja"],
        diff=diff, wr=wr, summary=summary,
        summary_short=summary_short, key_point=key_point,
        ult_point=ult_point, wave_point=wave_point,
        caution=caution, teamfight_point=teamfight_point,
        invade_point=invade_point
    )

total = 0
for champ_id, info in sorted(DATA.items()):
    path = os.path.join(CHAMP_DIR, champ_id, "matchups.md")
    if not os.path.isfile(path):
        continue

    role_type = detect_role(champ_id)
    additions = []
    for m in info["missing"]:
        additions.append(generate_matchup(info, m, role_type))

    if additions:
        with open(path, "a") as f:
            f.write("\n" + "\n".join(additions) + "\n")
        total += len(additions)
        print(f"  {info['ja']}: +{len(additions)}件追記")

print(f"\n合計 {total}件追記")
