#!/usr/bin/env node
// assemble-subrole-targets.js
// normalize-subrole-result.js が吐いた正規エントリ JSONL を集約し、
// subrole-targets.json 形式 {_generated, _patch, champions:{id:{ja,en,main,sub,...}}} を書き出す L1。
//
//   argv[2] = 正規エントリ JSONL のパス
//   argv[3] = patch 文字列
//   argv[4] = 出力先パス（subrole-targets.json）
//   argv[5] = 最低チャンプ数（これ未満なら異常終了。--limit テスト時は小さい値を渡す）
//
// roleShares / note / sources も champions[*] に保持する。誤判定の機械監査（A の選別）に使うため。

const fs = require("fs");

const [, , jsonlPath, patch, outputPath, minCountArg] = process.argv;
const minCount = parseInt(minCountArg || "100", 10);

const lines = fs.readFileSync(jsonlPath, "utf-8").split("\n").filter((l) => l.trim());

const champions = {};
for (const line of lines) {
  let e;
  try { e = JSON.parse(line); } catch (err) {
    process.stderr.write("WARN: JSONL 行のパース失敗、スキップ: " + line.slice(0, 80) + "\n");
    continue;
  }
  if (!e.id || !Array.isArray(e.main) || e.main.length === 0) {
    process.stderr.write("WARN: 不正エントリをスキップ: " + JSON.stringify(e).slice(0, 80) + "\n");
    continue;
  }
  champions[e.id] = {
    ja: e.ja, en: e.en,
    main: e.main, sub: Array.isArray(e.sub) ? e.sub : [],
    roleShares: e.roleShares || {}, note: e.note || "", sources: e.sources || [],
  };
}

const count = Object.keys(champions).length;
if (count < minCount) {
  process.stderr.write(`ERROR: champions エントリ数が少なすぎる (${count} < ${minCount})\n`);
  process.exit(1);
}

const result = { _generated: new Date().toISOString(), _patch: patch, champions };
fs.writeFileSync(outputPath, JSON.stringify(result, null, 2) + "\n", "utf-8");
process.stderr.write(`INFO: ${count} 体を ${outputPath} に書き出し\n`);
