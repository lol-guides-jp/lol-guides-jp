# lol-guides-jp — アーキテクチャリファレンス

> システム構成の参照用。行動指針は CLAUDE.md、コンテンツ方針は POLICY.md を参照。
> 最終更新: 2026-04-12

---

## ミッション

日本語の LoL チャンピオンガイド・対面ガイドを自動生成し、GitHub Pages で公開する。

---

## 機能 → アーティファクト対応表

### 対面ガイド生成パイプライン [ACTIVE — Gemini 移行中]

Gemini 2.5 Flash Lite でガイド生成 → Sonnet でレビュー。

- **dirs**: champions/\*/matchups.md, scripts/research-cache/ (旧、移行後に削除)
- **scripts**: add-matchups.sh, cron-add-matchups.sh, scrape-winrate.py, call-gemini.py, lint-matchup.py, scan-broken.py, replace-section.py, fix-guide-matchups.py, quality-fix.py, lib.sh
- **commands**: review-matchup.md
- **data**: missing-\*.txt（ロール別未生成リスト）, missing-matchups.json, lint-rules.json
- **cron**: cron-add-matchups.sh（一時停止中、Gemini 移行後に再開）

### パッチ更新 [ACTIVE]

パッチリリース検知 → ガイド更新。

- **scripts**: check-patch.sh, fetch-patch-notes.py
- **commands**: update-guides.md
- **cron**: 毎週月 04:00

### 品質チェック・改善サイクル [ACTIVE]

表現品質スキャン → 修正 → ルール学習のフィードバックループ。

- **scripts**: quality-check.py, quality-fix.py, scan-expressions.py, learn.py, check-coverage.py, check-skill-names.py
- **data**: expression-rules.json
- **config**: .claude/writing-rules.md
- **cron**: 毎週日 02:00 (scan-expressions.py)

### Lint・学習サイクル [ACTIVE]

Gemini 出力の L1 品質チェック + ルール蓄積。

- **scripts**: lint-matchup.py, learn-lint.py
- **data**: lint-rules.json

### 再生成パイプライン [ACTIVE]

品質不良エントリを検出して再生成。

- **scripts**: regen-matchups.sh, list-regen-targets.py, scan-broken.py

### OGP・静的サイト [ACTIVE]

GitHub Pages 用の JSON/HTML/OGP 画像生成。

- **scripts**: gen-ogp.mjs, build-json.js
- **dirs**: docs/
- **data**: docs/data.json, docs/champion-mechanics.json, docs/index.html, docs/ogp.png, docs/favicon.svg

### データファイル（共通参照） [ACTIVE]

複数スクリプトから参照される辞書・マッピングデータ。

- **data**: scripts/runes-ja.json (fetch-runes.py で更新), scripts/items-ja.json, scripts/ddragon-keys.json, scripts/beginner-picks.json

---

## 旧パイプライン [DEPRECATED — Gemini 移行完了時に削除]

Gemini 移行前の Sonnet ベースパイプライン。配線変更完了後に一括削除。

- **commands**: research-matchup.md, write-matchup.md, cross-check-matchup.md
- **scripts**: check-research-symmetry.py
- **dirs**: scripts/research-cache/

---

## ファイルフロー（Gemini 移行後）

```
missing-*.txt（ロール別未生成リスト）
  ↓
scrape-winrate.py（勝率取得）
  ↓
call-gemini.py（Gemini 2.5 Flash Lite × 2、A側+B側）
  ↓
lint-matchup.py --fix（L1 品質チェック + 自動修正）
  ↓
review-matchup.md（Sonnet レビュー + 修正）
  ↓ rejected → call-gemini.py --feedback で再生成（上限2回）
  ↓
Python 後処理:
  replace-section.py → champions/*/matchups.md に挿入
  fix-guide-matchups.py → guide.md の得意/苦手を同期
  quality-fix.py → 表記揺れ正規化
  build-json.js → docs/data.json 更新
```

## 人間の日常タスク

### 週1回
1. cron.log を確認（成功/失敗件数）
2. scan-expressions.py の結果を確認（scan.log）

### パッチリリース時
1. check-patch.sh が自動検知 → CLAUDE.local.md に通知
2. 必要に応じて update-guides.md を実行
