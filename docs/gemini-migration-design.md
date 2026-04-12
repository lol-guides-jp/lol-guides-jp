# パイプライン移行設計書

> 最終更新: 2026-04-13
> ステータス: 実装中・モデル移行済み

## 背景

対面ガイド生成パイプラインのコスト削減と品質向上を同時に実現する。

- 現行: research-matchup(Sonnet) → write-matchup(Sonnet) → Python後処理
- 問題1: Sonnet×4コール/ペアで $0.79。月額 $300超の見込み
- 問題2: LLMによる品質レビュー工程がない（Python機械チェックのみ）

## 新パイプライン

```
Python: Lolalytics スクレイプ（勝率取得、$0）
  ↓
generate-matchup (Gemini 3.1 Flash Lite × 2)
  A側・B側を各1回。勝率 + モデル知識で執筆
  ↓
lint-matchup.py --fix（L1 品質チェック + 自動修正）
  ↓
review-matchup (Sonnet × 1)
  A側 + B側を同時に読み、1回でチェック + 修正
  ↓
Python 後処理
  dispatch_ops → quality-fix → guide同期 → build-json
```

### 設計判断

| 判断 | 理由 |
|---|---|
| 勝率取得を Python に分離 | LolalyticsはSSRで勝率がHTML内に埋まっている。curl + 正規表現で取れる（検証済み）。LLMに検索させる必要がない |
| research と write を統合 | 分離はSonnetのコスト管理のためだった。Geminiなら分ける意味がない |
| レビューでA/B同時チェック | 品質レビュー + 整合性チェック（旧cross-check-matchup）を1コールに統合 |
| レビューは修正も行う | 小修正（スキル名、表記揺れ）はSonnetが直して返す。根本的な問題のみreject |
| Gemini API 直接呼び出し | cronバッチなのでMCP不要。`google-genai` SDK のPythonスクリプト |

## Gemini モデル選定

### 確認済み事実（2026-04-13）

| モデル | 無料枠RPD | RPM | TPM | 備考 |
|---|---|---|---|---|
| gemini-2.0-flash-lite | **0**（終了） | 0 | 0 | 使用不可 |
| gemini-2.0-flash | **0**（終了） | 0 | 0 | 使用不可 |
| gemini-2.5-flash-lite | **20** | 10 | 250K | 旧モデル。テスト通過済み |
| gemini-2.5-flash | **20** | 5 | 250K | RPD 同じ |
| gemini-3 flash | **20** | 5 | 250K | preview |
| gemini-3.1-flash-lite | **500** | 15 | 250K | **preview・採用** |
| Gemma 3 27B | 14,400 | 30 | **15K** | TPM が低すぎて不適 |
| Gemma 4 31B | 1,500 | 15 | 無制限 | 品質未検証 |

### 選定: gemini-3.1-flash-lite-preview（2026-04-13 変更）

旧選定 gemini-2.5-flash-lite（RPD 20）から移行。

- **RPD 500**: 旧モデルの 25 倍。batch=250 ペア/日が可能
- **品質**: 2.5 Flash Lite 以上。形態変化スキルの mismatch が 3→1 に改善（テスト実績）
- **速度**: 2.5 Flash 比で 2.5 倍高速
- **文体の「です/ます」混入**: プロンプトに「する体」指示を追加 + lint-matchup.py の polite_ending auto_fix で対応
- **preview リスク**: 制限変更・API 挙動変更の可能性あり。lint で検出できる範囲。個人プロジェクトでは許容

### 運用モード

**無料枠運用（推奨）**: batch=250（A+B で 500コール/日）。RPD 500 に収まり $0。全 3,417 件を約 7 日で完了可能。

**有料運用（将来オプション）**: Google Cloud billing を有効にすれば RPD 制限が緩和。月 $30 程度。

## SDK

- パッケージ: `google-genai`（新SDK）。旧 `google-generativeai` は非推奨
- venv: `/home/ojita/lol-guides-jp/.venv/`
- API キー: `~/.secrets/.env` の `GEMINI_API_KEY`

## コスト

| | 現行 | 新（無料枠） | 新（有料） |
|---|---|---|---|
| 勝率取得 | Sonnet WebSearch内 | Python curl $0 | $0 |
| 執筆 | Sonnet×4 $0.79 | Gemini×2 $0 | ~$0.02 |
| レビュー | なし | Sonnet×1 $0.12 | $0.12 |
| **合計/ペア** | **$0.79** | **$0.12** | **$0.14** |
| **削減率** | — | **85%** | **82%** |

## review-matchup の検査項目

1. スキル名の正確性（champ_skills / opp_skills との照合）
2. ハルシネーション（処刑ライン数値、スキル仕様、存在しない効果）
3. 視点の一貫性（main チャンプ視点で書かれているか）
4. A↔B の対称性（verdict が逆、数値の矛盾がないか）
5. writing-rules.md 準拠（表記揺れ、禁止表現）
6. リワーク済みチャンプの古い情報検知（後述のパッチトラッキングと連動）

出力:
- `approved`: 修正済みの A/B エントリ（そのまま書き込める状態）
- `rejected`: 理由付き。Gemini に再生成させる（リトライ上限あり）

## 実装コンポーネント

| ファイル | 役割 | 新規/改修 |
|---|---|---|
| `scripts/scrape-winrate.py` | Lolalytics から勝率を curl + 正規表現で取得 | 新規 ✅ |
| `scripts/call-gemini.py` | Gemini 3.1 Flash Lite API 呼び出し | 新規 ✅ |
| `scripts/lint-matchup.py` | L1 品質チェック + 自動修正（文体・禁止語・形態名） | 新規 ✅ |
| `scripts/lint-rules.json` | lint ルール定義（learn-lint.py で蓄積） | 新規 ✅ |
| `.claude/commands/review-matchup.md` | Sonnet レビュープロンプト | 新規 ✅ |
| `scripts/add-matchups.sh` | パイプライン本体の配線変更 | 改修（未着手） |
| `scripts/lib.sh` | 変更なし（Gemini は run_cmd を通さない） | — |

### scrape-winrate.py の仕様

- 入力: `champ_en`, `opp_en`
- 処理: `https://lolalytics.com/lol/{champ}/vs/{opp}/build/?tier=all` を curl → HTML から勝率を正規表現で抽出
- 出力: `46.9`（数値のみ、stdout）
- 検証済み: Aatrox vs Garen → 46.9%（実際の値 46.91% と一致）

### call-gemini.py の仕様

- 入力: `champ_id|champ_ja|champ_en|opp_id|opp_ja|opp_en|type|winrate|champ_skills|opp_skills`
- 処理: 勝率（引数で渡される）+ モデルの LoL 知識で matchups.md 形式のエントリを生成
- 出力: matchup エントリのテキスト（`## vs ...` で始まる1エントリ分）
- 検索不要（勝率は Python が取得済み、tips はモデル知識）
- エラー時: exit 1（呼び出し側でスキップ）

### review-matchup.md の仕様

- 入力: A側エントリ + B側エントリ + champ_skills + opp_skills（JSON）
- ツール: Read のみ（writing-rules.md を参照）
- 出力: JSON（status: approved/rejected + 修正済みエントリ or 理由）

## リスクと対策

| リスク | 対策 |
|---|---|
| 3.1 Flash Lite の文体が「です/ます」混入 | プロンプトに「する体」指示追加 + lint polite_ending auto_fix + Sonnet レビュー |
| 3.1 Flash Lite が preview で API 変更 | lint-matchup.py で出力フォーマット検証。壊れたらモデル名を戻すだけ |
| Lolalytics の HTML 構造変更 | scrape-winrate.py が空を返す → スキップ + ログ。正規表現を更新 |
| reject 無限ループ | リトライ上限2回。超えたらスキップしてログ記録 |
| 無料枠 RPD のさらなる削減 | 有料に切り替え（月 $30）。設計上はモデル名変更だけ |
| リワーク済みチャンプの古い情報 | パッチトラッキング（後述）で検知。該当チャンプは Sonnet レビューで reject |

## 移行手順

1. ~~`google-genai` インストール + API キー取得~~ ✅ 完了
2. ~~`scrape-winrate.py` 実装~~ ✅ 完了
3. ~~`call-gemini.py` 実装~~ ✅ 完了
4. ~~`lint-matchup.py` + `lint-rules.json` 実装~~ ✅ 完了
5. ~~`review-matchup.md` 実装~~ ✅ 完了（未テスト）
6. ~~モデルを gemini-3.1-flash-lite-preview に移行~~ ✅ 2026-04-13
7. review-matchup.md を Sonnet でテスト
8. `add-matchups.sh` を新パイプラインに配線変更
9. 10件テスト: パイプライン全体を通して品質確認
10. OK なら cron 再開

## 廃止対象

移行完了後に削除:
- `.claude/commands/research-matchup.md`（Gemini に移行）
- `.claude/commands/write-matchup.md`（Gemini に移行）
- `.claude/commands/cross-check-matchup.md`（review-matchup に統合済み）
- `scripts/check-research-symmetry.py`（review-matchup に統合済み）
- `scripts/research-cache/`（不要）

---

## パッチトラッキング（別タスクとして実装）

新パッチリリース時にチャンピオンデータの更新とリワーク検知を自動化する。

### 目的

1. **data.json のスキルデータ更新**: パッチごとに CD・マナコスト等が変わる可能性がある
2. **リワーク検知**: スキルの性質が変わったチャンプを特定し、ガイド再生成の対象としてフラグを立てる

### パイプライン

```
パッチノート検知（patchbot.io or rito-news-feeds）
  ↓
Data Dragon 更新チェック
  ↓
data.json スキルデータ再取得（build-json.js）
  ↓
差分検知: description が大幅に変わったチャンプ = リワーク候補
  ↓
リワーク候補リストを出力 → 該当チャンプのガイド再生成トリガー
```

### 設計ポイント

| 項目 | 方針 |
|---|---|
| パッチノート検知 | patchbot.io を定期チェック、または rito-news-feeds の RSS を監視 |
| Data Dragon 更新 | Riot 公式 API（ddragon.leagueoflegends.com）からスキルデータ取得 |
| リワーク判定 | data.json の旧 description と新 description を比較。大幅変更（編集距離が閾値超）→ リワーク |
| 数値調整の扱い | CD・コスト等の数値変更は data.json 更新のみ。guide.md / matchups.md は変更不要（POLICY.md で具体値を書かない方針） |
| リワーク時の対応 | 該当チャンプの guide.md + 全 matchups を再生成キューに入れる |
| 実行頻度 | 2週間に1回（パッチサイクルに合わせる） |
| リワーク判定の LLM 利用 | パッチノート1件を Sonnet に読ませて「リワークか数値調整か」を判定。2週に1回なので数セント |

### 実装コンポーネント（予定）

| ファイル | 役割 |
|---|---|
| `scripts/check-patch.py` | パッチ番号の更新チェック + Data Dragon 差分取得 |
| `scripts/detect-rework.py` | description 差分からリワーク候補を抽出 |
| `scripts/cron-patch-check.sh` | cron 用ラッパー（2週間に1回） |
