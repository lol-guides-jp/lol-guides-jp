#!/usr/bin/env python3
"""call-gemini.py — Gemini 3.1 Flash Lite で対面ガイドエントリを生成する

使い方:
  python3 scripts/call-gemini.py 'champ_id|champ_ja|...|opp_skills'
  python3 scripts/call-gemini.py --feedback 'レビュー理由' 'champ_id|champ_ja|...|opp_skills'

出力:
  matchups.md 形式の1エントリ（## vs ... で始まるテキスト）を stdout に出力。
  エラー時は exit 1。

--feedback: Sonnet レビューで reject された理由を渡すと、プロンプトに追加して再生成する。
"""

import os
import sys

# venv の google-genai を使う
VENV_SITE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".venv", "lib", "python3.12", "site-packages",
)
if os.path.isdir(VENV_SITE):
    sys.path.insert(0, VENV_SITE)

from google import genai  # noqa: E402


def load_api_key() -> str:
    env_file = os.path.expanduser("~/.secrets/.env")
    if not os.path.isfile(env_file):
        print("ERROR: ~/.secrets/.env not found", file=sys.stderr)
        sys.exit(1)
    for line in open(env_file):
        line = line.strip()
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    print("ERROR: GEMINI_API_KEY not found in ~/.secrets/.env", file=sys.stderr)
    sys.exit(1)


def parse_input(arg: str) -> dict:
    parts = arg.split("|")
    if len(parts) != 10:
        print(f"ERROR: expected 10 pipe-separated fields, got {len(parts)}", file=sys.stderr)
        sys.exit(1)
    return {
        "champ_id": parts[0],
        "champ_ja": parts[1],
        "champ_en": parts[2],
        "opp_id": parts[3],
        "opp_ja": parts[4],
        "opp_en": parts[5],
        "type": parts[6],
        "winrate": parts[7],
        "champ_skills": parts[8],
        "opp_skills": parts[9],
    }


def winrate_to_verdict(winrate_str: str) -> str:
    try:
        wr = round(float(winrate_str))
    except ValueError:
        return "五分"
    if wr >= 57:
        return "有利"
    elif wr >= 53:
        return "やや有利"
    elif wr >= 48:
        return "五分"
    elif wr >= 44:
        return "やや不利"
    else:
        return "不利"


def build_prompt(data: dict, feedback: str = "") -> str:
    verdict = winrate_to_verdict(data["winrate"])
    winrate_int = str(round(float(data["winrate"]))) if data["winrate"] else "50"

    feedback_section = ""
    if feedback:
        feedback_section = f"""

## 前回のレビュー結果（再生成の理由）

前回の出力はレビューで reject されました。以下の指摘を踏まえて再生成してください。

{feedback}

上記の問題を必ず修正すること。同じ間違いを繰り返さないこと。
"""

    return f"""あなたはLoL対面ガイドライターです。以下の情報を元に、対面ガイドエントリを1件生成してください。
{feedback_section}

## 対面情報

- メインチャンプ（ガイドを読むプレイヤーが使う）: {data["champ_ja"]}（{data["champ_en"]}）
- 対戦相手: {data["opp_ja"]}（{data["opp_en"]}）
- 勝率（All Ranks）: {data["winrate"]}%
- verdict: {verdict}
- メインチャンプのスキル: {data["champ_skills"]}
- 対戦相手のスキル: {data["opp_skills"]}

## 出力フォーマット（厳守）

以下の形式のテキストのみを出力する。説明文・前置き・コードフェンスは不要。

## vs {data["opp_ja"]}（{data["opp_en"]}）
- **{verdict}（勝率約{winrate_int}%）**: （この対面の要約を1文で）
- **Lv1〜2**: （序盤の立ち回り）
- **Lv3〜5**: （中盤序盤の立ち回り）
- **Lv6以降**: （R取得後の立ち回り）
- **ウェーブ管理**: （ウェーブの扱い方）
- **注意ポイント**: （特に気をつけるべきこと）

## 必須ルール

### 視点
全文を{data["champ_ja"]}プレイヤー視点で書く。「自分がどう動くか」の説明にする。

### スキル名（最重要）
- メインチャンプのスキル: 上記 champ_skills の値のみ使う（例: Q（ダーキンブレード））
- 対戦相手のスキル: 上記 opp_skills の値のみ使う（例: Q（断固たる一撃））
- 英語名・通称・推測した名前は絶対に使わない
- スキル名に `/` が含まれている場合は形態変化チャンプ。どちらの形態のスキルか文脈で確認してから使う

### 形態変化チャンピオンの呼び方（厳守）

以下のチャンピオンは形態ごとにスキル名が異なる。スキルを書くときは必ず形態名を明示する（例: 「キャノンモードQ（ショックブラスト）」）。

| チャンピオン | 形態A | 形態B | R |
|---|---|---|---|
| ジェイス | キャノンモード（遠距離）: Q=ショックブラスト, W=ハイパーチャージ, E=アクセルゲート | ハンマーモード（近接）: Q=スカイバスター, W=ライトニング, E=サンダーブロー | マーキュリーキャノン/マーキュリーハンマー（形態切替） |
| ニダリー | 人間形態: Q=槍投げ, W=虎挟み, E=高揚 | クーガー形態: Q=テイクダウン, W=ジャンプ, E=クロウ | クーガーの心（形態切替、Lv1から使用可） |
| エリス | 人間形態: Q=神経毒, W=子蜘蛛爆弾, E=繭化 | クモ形態: Q=毒牙, W=猛食, E=蜘蛛の糸 | 蜘蛛形態（形態切替、Lv1から使用可） |
| ナー | ミニナー: Q=ブーメラン, W=ごきげん, E=ぴょんぴょん | メガナー: Q=ぽいっ, W=こてんぱん, E=ドーン！ | ナー！（メガナー時のみ発動） |

- 「メカ形態」「メガス形態」「虎形態」「スパイダー形態」→ 存在しない呼び方。上の表の名称を使う
- エリス・ニダリーの R は Lv1 から使用可能。Lv6パワースパイクはない
- ケイン: 赤ケイン（ダーキン形態）/ 青ケイン（シャドウアサシン形態）
- ウディア: スタンス（形態変化ではない）
- カ＝ジックス: 進化（形態変化ではない）

### 文体（最重要）
- 「する」体（常体）で書く。「です」「ます」「しましょう」「ください」は使わない
- 体言止めまたは動詞終止形で文を終える（例: 「距離を取る」「ポークが主力」）

### 表記統一
- HP割合は%表記（HP5割 → HP50%）
- 通常攻撃は AA
- クールダウンは CD
- ラストヒットは CS
- 範囲は「〜」（全角波ダッシュ）
- オールインは「オールイン」
- 「ミニオン波」→「ミニオンウェーブ」
- 「フルキット」は使わない → 「Lv6以降」「スキルがそろった後」
- 「〜の窓」→「〜のチャンス」「〜の隙」

### CD秒数を書かない
スキルのCD秒数はパッチで変わるため書かない。ただしサモナースペルは共通値のため書いてよい:
- フラッシュ: 300秒 / ゴースト: 240秒 / テレポート: 360秒

### 処刑スキルの正確な記述
- アーゴット R: HP25%以下で処刑
- アンベッサ R: 処刑効果なし（CC技）
- パイク R: 固定HP値で処刑（%ではない）
- チョ＝ガス R: 処刑ではなくバースト
- ガレン R: 処刑ではなく失ったHP比例ダメージ

### 禁止事項
- "AD carry" を使わない → 「ダメージディーラー」「後衛アタッカー」
- 「処刑」をゲームメカニクス以外の意味で使わない
- CCの複合仕様を推測で書かない（スタン・スローの区別が不確かなら「CCに注意」とだけ書く）

## 出力
上記フォーマットのテキストのみ。前置き・補足・コードフェンスは一切不要。"""


def generate(data: dict, feedback: str = "") -> str:
    api_key = load_api_key()
    client = genai.Client(api_key=api_key)

    prompt = build_prompt(data, feedback)

    # 503 UNAVAILABLE 用バックオフ（tenacity が諦めた後に追加リトライ）
    # 503（UNAVAILABLE）はリトライせず即 exit 3 で返す。
    # Flex 枠では混雑時に叩き続けても解消しないため、次の cron に委ねる設計（2026-04-15 変更）。
    # exit 2 = RPD上限、exit 3 = 503。呼び出し元（add-matchups.sh）でバッチ終了を判断する。
    response = None
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt,
        )
    except Exception as e:
        err_str = str(e)
        if "RESOURCE_EXHAUSTED" in err_str:
            print("ERROR: Gemini RPD上限に達した (RESOURCE_EXHAUSTED)", file=sys.stderr)
            sys.exit(2)
        if "UNAVAILABLE" in err_str:
            print(f"ERROR: Gemini 503 UNAVAILABLE - 次のcronに委ねる", file=sys.stderr)
            sys.exit(3)
        print(f"ERROR: Gemini API error: {e}", file=sys.stderr)
        sys.exit(1)
    if response is None:
        sys.exit(1)

    text = response.text.strip()
    if not text:
        print("ERROR: empty response from Gemini", file=sys.stderr)
        sys.exit(1)

    # コードフェンスが付いている場合は除去
    if text.startswith("```"):
        lines = text.split("\n")
        # 先頭の ```markdown や ``` を除去
        if lines[0].startswith("```"):
            lines = lines[1:]
        # 末尾の ``` を除去
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # ## vs で始まることを検証
    if not text.startswith("## vs "):
        print("ERROR: output does not start with '## vs '", file=sys.stderr)
        print(f"Got: {text[:100]}", file=sys.stderr)
        sys.exit(1)

    return text


if __name__ == "__main__":
    feedback = ""
    args = sys.argv[1:]

    if len(args) >= 2 and args[0] == "--feedback":
        feedback = args[1]
        args = args[2:]

    if len(args) != 1:
        print(f"Usage: {sys.argv[0]} [--feedback 'reason'] 'champ_id|champ_ja|...'", file=sys.stderr)
        sys.exit(1)

    data = parse_input(args[0])
    entry = generate(data, feedback)
    print(entry)
