# lol-guides-jp — Claude Code 行動指針

## 基本
- コンテンツ方針は `POLICY.md` に従う
- ガイド作成は WebSearch で最新パッチ情報を取得してから行う

## 禁止
- 英語サイトの内容を丸コピしない（要約・再構成すること）
- `TODO.md` の完了チェックを飛ばさない（`- [ ]` → `- [x]` に更新する）

## 技術スタック
- コンテンツ: Markdown / champions/ ディレクトリに1体1ファイル
- 自動化: daily-guide.sh（毎日4時・cron）→ write-guide コマンド実行
- Git: git.exe 経由で push（WSL制約）
