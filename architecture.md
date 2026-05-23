# lol-guides-jp — アーキテクチャリファレンス

> システム構成の参照用。行動指針は CLAUDE.md、コンテンツ方針は POLICY.md を参照。
> 最終更新: 2026-05-24（案A→案B 移行完了）

---

## ミッション

日本語の LoL チャンピオンガイド・対面ガイドを自動生成し、GitHub Pages で公開する。

---

## 機能 → アーティファクト対応表

### 対面ガイド生成パイプライン [ACTIVE — 案B Sonnet 4.6 + WebSearch]

Sonnet 4.6 が WebSearch で最新パッチ情報を調査して A/B 同時生成。`--cost-mode quality|lite` で切替可能。

- **dirs**: champions/\*/matchups.md
- **scripts**: scripts/add-matchups.sh, scripts/cron-add-matchups.sh, scripts/validate-matchup-format.py, scripts/lint-matchup.py, scripts/scan-broken.py, scripts/replace-section.py, scripts/replace-section-text.py, scripts/fix-guide-matchups.py, scripts/quality-fix.py, scripts/lib.sh
- **commands**: gen-matchup.md (quality), gen-matchup-lite.md (cost-optimized)
- **data**: missing-\*.txt（ロール別未生成リスト）, missing-matchups.json, lint-rules.json
- **cron**: cron-add-matchups.sh（毎日16回、90分間隔）
- **詳細設計**: notes/migration-2026-05-24-gen-matchup.md

### パッチ更新 [ACTIVE]

パッチリリース検知 → ガイド更新。

- **scripts**: scripts/check-patch.sh, scripts/fetch-patch-notes.py
- **commands**: update-guides.md
- **cron**: 毎週月 04:00

### 品質チェック・改善サイクル [ACTIVE]

表現品質スキャン → 修正 → ルール学習のフィードバックループ。

- **scripts**: scripts/quality-check.py, scripts/quality-fix.py, scripts/scan-expressions.py, scripts/learn.py, scripts/check-coverage.py, scripts/check-skill-names.py
- **data**: expression-rules.json
- **config**: .claude/writing-rules.md
- **cron**: 毎週日 02:00 (scan-expressions.py)

### Lint・学習サイクル [ACTIVE]

gen-matchup 出力の L1 品質チェック + ルール蓄積（保険）。

- **scripts**: scripts/lint-matchup.py, scripts/learn-lint.py
- **data**: lint-rules.json

### 再生成パイプライン [ACTIVE]

品質不良エントリを検出して再生成。

- **scripts**: scripts/regen-matchups.sh, scripts/list-regen-targets.py, scripts/scan-broken.py

### OGP・静的サイト [ACTIVE]

GitHub Pages 用の JSON/HTML/OGP 画像生成。

- **scripts**: gen-ogp.mjs, build-json.js
- **dirs**: docs/
- **data**: docs/data.json, docs/champion-mechanics.json, docs/index.html, docs/ogp.png, docs/favicon.svg

### データファイル（共通参照） [ACTIVE]

複数スクリプトから参照される辞書・マッピングデータ。

- **data**: scripts/runes-ja.json (scripts/fetch-runes.py で更新), scripts/items-ja.json, scripts/ddragon-keys.json, scripts/beginner-picks.json

---

## 旧パイプライン [DEPRECATED]

### 案A: Gemini パイプ（2026-05-24 廃止）

Gemini 3.1 Flash Lite が内部知識のみで生成していたためパッチ追従できず、案B に置換。

- **scripts**: scripts/call-gemini.py（削除済み）, scripts/scrape-winrate.py（削除済み）
- **dirs**: .venv/（削除済み）
- **commands**: review-matchup.md（残置、廃止フローでのみ呼ばれていたため運用上は不要）
- **詳細**: notes/migration-2026-05-24-gen-matchup.md

### 案前段: 旧 Sonnet パイプ（要削除判断）

案A 以前の Sonnet ベース手法。

- **commands**: research-matchup.md, write-matchup.md, cross-check-matchup.md
- **scripts**: check-research-symmetry.py
- **dirs**: scripts/research-cache/

---

## ファイルフロー（案B、現行）

```
missing-*.txt / requeue-*.txt（生成キュー）
  ↓
Data Dragon API（patch 番号取得、fallback で data.json）
  ↓
gen-matchup{,-lite}.md（Sonnet 4.6 + WebSearch、A/B 同時生成）
  ↓ 出力: JSON {status, entry_a, entry_b, sources, used_patch}
validate-matchup-format.py（フォーマット検証 / extract）
  ↓
lint-matchup.py --fix（保険として表記揺れ修正）
  ↓
Python 後処理:
  replace-section.py / printf 追記 → champions/*/matchups.md に挿入
  fix-guide-matchups.py → guide.md の得意/苦手を同期
  quality-fix.py → 表記揺れ正規化
  build-json.js → docs/data.json 更新
  auto_commit + auto_push（3段コミット: feat → fix → chore）
```

## 人間の日常タスク

### 週1回
1. cron.log を確認（成功/失敗件数）
2. scan-expressions.py の結果を確認（scan.log）

### パッチリリース時
1. check-patch.sh が自動検知 → CLAUDE.local.md に通知
2. 必要に応じて update-guides.md を実行
