# lol-guides-jp — Claude Code 行動指針

## 基本
- コンテンツ方針は `POLICY.md` に従う
- ガイド作成は WebSearch で最新パッチ情報を取得してから行う（バランス変更を反映するため）

## 禁止
- 英語サイトの内容を丸コピしない（著作権上の問題になるため。要約・再構成すること）
- `TODO.md` の完了チェックを飛ばさない（`- [ ]` → `- [x]` に更新する）（進捗追跡の信頼性を保つため）

## 技術スタック
- コンテンツ: Markdown / champions/ ディレクトリに1体1ファイル
- 自動化: cron-add-matchups.sh → add-matchups.sh（Gemini 移行中、詳細は architecture.md 参照）
- Git: WSL側の git で push（HTTPS）
