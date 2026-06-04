#!/usr/bin/env node
// normalize-subrole-result.js
// judge-subrole コマンド（claude --print）の生出力を、1チャンプぶんの正規エントリ
// (JSON 1行) に変換する L1。出力の揺れ（コードフェンス・前置き・エラー応答）を吸収し、
// 失敗時はフォールバック（メインロールのみ・sub 空）を返す。常に exit 0 で1行出力する。
//
//   stdin       : judge-subrole の生出力
//   argv[2]     : フォールバック用チャンプ JSON  {"id","ja","en","role"}
//   argv[3]     : （任意）前回判定エントリ {main,sub,roleShares,note,sources}
//   stdout      : 正規エントリ JSON 1行  {id,ja,en,main,sub,roleShares,note,sources}
//   stderr      : "OK" / "PRESERVE <理由>" / "FALLBACK <理由>"（呼び出し側の集計用）
//
// id/ja/en は data.json 由来（argv[2]）を正とする。モデルが id を取り違えても壊さないため。
//
// 判定失敗時の扱い（重要・2026-06-04 設計修正）:
//   レート上限・API エラー等で判定できなかったケースを「サブなし」と同じ空フォールバックに
//   落とすと、本物のサブ持ちチャンプが偽卒業し、キューと表示が破壊される（実際に85体で発生）。
//   → argv[3] で前回判定を渡された場合は、失敗時に前回値を「保持」する（PRESERVE）。
//     前回値が無い場合のみメインロールのみの空フォールバック（FALLBACK）に落とす。
//   「判定できなかった（保持）」と「判定した結果サブが無い（success・sub空）」を区別する。
// 単体テスト: scripts/__tests__ は持たないので、echo でサンプルを流して確認する（README はスクリプト冒頭）。

const fs = require("fs");

const ROLES = ["トップレーン", "ジャングル", "ミッドレーン", "ADC", "サポート"];

let fb;
try {
  fb = JSON.parse(process.argv[2]);
} catch (e) {
  process.stderr.write("FATAL: argv[2] のフォールバック JSON が不正\n");
  process.exit(1);
}

// argv[3]（前回判定）は任意。壊れていても無視して空フォールバックに落とすだけ。
let prev = null;
if (process.argv[3]) {
  try {
    const p = JSON.parse(process.argv[3]);
    if (p && Array.isArray(p.main) && p.main.length > 0) prev = p;
  } catch (e) { /* prev 無効 → null のまま */ }
}

function fallbackEntry(reason) {
  // 前回判定があれば保持（偽卒業を防ぐ）。無ければメインのみの空フォールバック。
  if (prev) {
    process.stderr.write("PRESERVE " + reason + "\n");
    return {
      id: fb.id, ja: fb.ja, en: fb.en,
      main: prev.main,
      sub: Array.isArray(prev.sub) ? prev.sub : [],
      roleShares: prev.roleShares && typeof prev.roleShares === "object" ? prev.roleShares : {},
      note: "preserved (judge失敗): " + reason,
      sources: Array.isArray(prev.sources) ? prev.sources : [],
    };
  }
  process.stderr.write("FALLBACK " + reason + "\n");
  return { id: fb.id, ja: fb.ja, en: fb.en, main: [fb.role], sub: [], roleShares: {}, note: "fallback: " + reason, sources: [] };
}

// 生出力から最初の { ... } を bracket-match で抜き出す（文字列内の波括弧は無視）。
function extractJson(raw) {
  if (!raw) return null;
  let s = raw.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
  const start = s.indexOf("{");
  if (start < 0) return null;
  let depth = 0, inStr = false, esc = false;
  for (let j = start; j < s.length; j++) {
    const ch = s[j];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') inStr = true;
    else if (ch === "{") depth++;
    else if (ch === "}") { depth--; if (depth === 0) { try { return JSON.parse(s.slice(start, j + 1)); } catch (e) { return null; } } }
  }
  return null;
}

const obj = extractJson(fs.readFileSync(0, "utf-8"));

let out;
if (!obj || obj.status === "error" || !Array.isArray(obj.main)) {
  out = fallbackEntry(obj && obj.reason ? obj.reason : "parse/main 不正");
} else {
  const cleanMain = obj.main.filter((r) => ROLES.includes(r));
  if (cleanMain.length === 0) {
    out = fallbackEntry("main にロール名なし（検証後）");
  } else {
    const cleanSub = (Array.isArray(obj.sub) ? obj.sub : [])
      .filter((r) => ROLES.includes(r) && !cleanMain.includes(r));
    out = {
      id: fb.id, ja: fb.ja, en: fb.en,
      main: [...new Set(cleanMain)],
      sub: [...new Set(cleanSub)],
      roleShares: obj.roleShares && typeof obj.roleShares === "object" ? obj.roleShares : {},
      note: typeof obj.note === "string" ? obj.note : "",
      sources: Array.isArray(obj.sources) ? obj.sources : [],
    };
    process.stderr.write("OK\n");
  }
}

process.stdout.write(JSON.stringify(out) + "\n");
