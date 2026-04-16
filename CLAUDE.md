# lol-guides-jp — Claude Code 行動指針

## 基本
- コンテンツ方針は `POLICY.md` に従う
- ガイド作成は WebSearch で最新パッチ情報を取得してから行う（バランス変更を反映するため）

## 禁止
- 英語サイトの内容を丸コピしない（著作権上の問題になるため。要約・再構成すること）
- `TODO.md` の完了チェックを飛ばさない（`- [ ]` → `- [x]` に更新する）（進捗追跡の信頼性を保つため）

## ディレクトリの役割（混在禁止）

| ディレクトリ | 役割 | 公開 |
|---|---|---|
| `docs/` | GitHub Pages の公開 Web アセット（index.html / data.json 等） | ◎ 公開 |
| `champions/` | チャンピオンガイド Markdown | ◎ 公開（Git管理） |
| `scripts/` | 自動化スクリプト | ◎ 公開（Git管理） |
| `notes/` | 内部メモ・調査ログ・設計検討 | ✕ .gitignore 除外 |

- `docs/` に `.md` を置かない。調査ログ・設計メモは必ず `notes/` へ
- `notes/` は .gitignore 除外済み。コミット不要

## 技術スタック
- コンテンツ: Markdown / champions/ ディレクトリに1体1ファイル
- 自動化: cron-add-matchups.sh → add-matchups.sh（Gemini 移行中、詳細は architecture.md 参照）
- Git: WSL側の git で push（HTTPS）
