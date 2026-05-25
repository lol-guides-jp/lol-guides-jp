#!/usr/bin/env node
// build-json.js
// 全チャンピオンガイド(Markdown)をJSONに変換する
//
// 使い方: node scripts/build-json.js

const fs = require("fs");
const path = require("path");
const https = require("https");

const CHAMPIONS_DIR = path.join(__dirname, "..", "champions");
const OUTPUT_FILE = path.join(__dirname, "..", "docs", "data.json");
const DDRAGON_KEYS = JSON.parse(
  fs.readFileSync(path.join(__dirname, "ddragon-keys.json"), "utf-8")
);
const BEGINNER_PICKS = JSON.parse(
  fs.readFileSync(path.join(__dirname, "beginner-picks.json"), "utf-8")
);

// サブロール判定（フェーズ4で導入、2026-05-25）
// ファイルが無い場合は空オブジェクトを返し、既存挙動を維持する。
const SUBROLE_TARGETS_FILE = path.join(__dirname, "subrole-targets.json");
const SUBROLE_TARGETS = fs.existsSync(SUBROLE_TARGETS_FILE)
  ? JSON.parse(fs.readFileSync(SUBROLE_TARGETS_FILE, "utf-8"))
  : { champions: {} };

// Data Dragon API から動的取得（main() 冒頭で更新）。fetch 失敗時の fallback として既知値を残す。
let DDRAGON_VERSION = "16.7.1";

function parseGuide(markdown) {
  const sections = {};
  let currentSection = null;
  let currentContent = [];

  for (const line of markdown.split("\n")) {
    if (line.startsWith("## ")) {
      if (currentSection) {
        sections[currentSection] = currentContent.join("\n").trim();
      }
      currentSection = line.replace("## ", "").trim();
      currentContent = [];
    } else if (line.startsWith("# ")) {
      sections._title = line.replace("# ", "").trim();
    } else {
      currentContent.push(line);
    }
  }
  if (currentSection) {
    sections[currentSection] = currentContent.join("\n").trim();
  }
  return sections;
}

function parseMatchupsList(text) {
  if (!text) return [];
  return text
    .split("\n")
    .filter((l) => l.startsWith("- **"))
    .map((l) => {
      const match = l.match(/- \*\*(.+?)\*\*:\s*(.+)/);
      if (!match) return null;
      return { name: match[1], description: match[2] };
    })
    .filter(Boolean);
}

function parseTitleLine(title) {
  const match = title.match(/^(.+?)（(.+?)）(.+?)\s*パッチ(.+)$/);
  if (!match) return { en: title, ja: "", role: "", patch: "" };
  return {
    en: match[1].trim(),
    ja: match[2].trim(),
    role: match[3].trim(),
    patch: match[4].trim(),
  };
}

// matchups.md パーサー
function parseMatchupsFile(markdown, nameToId) {
  const matchups = [];
  const blocks = markdown.split(/^## /m).slice(1);

  for (const block of blocks) {
    const lines = block.split("\n");
    const headerLine = lines[0].trim();

    // ヘッダパース: "vs Syndra（シンドラ）" or "vs ガレン（Garen）"
    const headerMatch = headerLine.match(
      /^vs\s+(.+?)（(.+?)）/
    );
    if (!headerMatch) continue;

    const name1 = headerMatch[1].trim();
    const name2 = headerMatch[2].trim();

    // opponentId解決: 英名→ID or 日名→ID
    const opponentId =
      nameToId[name1] || nameToId[name2] || name1.toLowerCase();

    // 難易度行パース（最初のbullet）
    let difficulty = "";
    let winrate = null;
    const bullets = [];

    for (const line of lines.slice(1)) {
      const bulletMatch = line.match(/^- \*\*(.+?)\*\*:\s*(.+)/);
      if (!bulletMatch) continue;

      const label = bulletMatch[1];
      const text = bulletMatch[2];

      // 最初のbulletは難易度行
      if (!difficulty) {
        const diffMatch = label.match(/^(.+?)（勝率[約]?(\d+\.?\d*)%）$/);
        if (diffMatch) {
          difficulty = diffMatch[1];
          winrate = parseFloat(diffMatch[2]);
        } else {
          difficulty = label;
        }
        bullets.push({ label: "概要", text });
      } else {
        bullets.push({ label, text });
      }
    }

    matchups.push({
      opponentId,
      difficulty,
      winrate,
      bullets,
    });
  }
  return matchups;
}

// 名前→IDの逆引きマップ構築
function buildNameToIdMap(champions) {
  const map = {};
  for (const c of champions) {
    if (c.en) map[c.en] = c.id;
    if (c.ja) map[c.ja] = c.id;
    // 日本語名のバリエーション（「リー・シン」→「lee-sin」など）
    if (c.ja) map[c.ja.replace(/・/g, "")] = c.id;
  }
  return map;
}

// Data Dragon からチャンピオン詳細JSONを取得
function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error(`JSON parse error: ${url}`)); }
      });
    }).on("error", reject);
  });
}

async function fetchSpells(ddragonKey) {
  const url = `https://ddragon.leagueoflegends.com/cdn/${DDRAGON_VERSION}/data/ja_JP/champion/${ddragonKey}.json`;
  try {
    const json = await fetchJSON(url);
    const champData = Object.values(json.data)[0];
    const passive = {
      key: "P",
      name: champData.passive.name,
      description: champData.passive.description.replace(/<[^>]+>/g, ""),
      image: champData.passive.image.full,
    };
    const keys = ["Q", "W", "E", "R"];
    const spells = champData.spells.map((s, i) => ({
      key: keys[i],
      name: s.name,
      description: s.description.replace(/<[^>]+>/g, ""),
      image: s.image.full,
      cooldown: s.cooldownBurn || "",
      cost: s.costBurn || "",
      range: s.rangeBurn || "",
      leveltip: (s.leveltip?.label || []).map((l) =>
        l.replace(/@AbilityResourceName@/g, "マナ")
      ),
    }));
    return [passive, ...spells];
  } catch (e) {
    console.error(`WARN: ${ddragonKey} のスペル取得失敗: ${e.message}`);
    return null;
  }
}

// --- メイン処理 ---
const champions = [];
const dirs = fs.readdirSync(CHAMPIONS_DIR).filter((d) => d !== "_template");

// Phase 1: guide.md を全て読み込み
for (const dir of dirs) {
  const guidePath = path.join(CHAMPIONS_DIR, dir, "guide.md");
  if (!fs.existsSync(guidePath)) continue;

  const md = fs.readFileSync(guidePath, "utf-8");
  const sections = parseGuide(md);
  const info = parseTitleLine(sections._title || "");

  champions.push({
    id: dir,
    en: info.en,
    ja: info.ja,
    ddragonKey: DDRAGON_KEYS[dir] || dir,
    role: info.role,
    patch: info.patch,
    beginnerRating: BEGINNER_PICKS[dir] || 3,
    summary: sections["一言まとめ"] || "",
    skillOrder: sections["スキルオーダー"] || "",
    powerSpikes: sections["主要パワースパイク"] || "",
    gamePlan: sections["ゲームプラン"] || "",
    teamfight: sections["集団戦の立ち回り"] || "",
    favorableMatchups: parseMatchupsList(sections["得意マッチアップ"]),
    unfavorableMatchups: parseMatchupsList(sections["苦手マッチアップ"]),
    counters:
      sections[Object.keys(sections).find((k) => k.startsWith("対策"))] || "",
    matchups: [],
  });
}

// Phase 2: 名前→IDマップ構築後、matchups.md / matchups-sub.md をパース
const nameToId = buildNameToIdMap(champions);

for (const champ of champions) {
  // メインロール対面（既存）
  const matchupsPath = path.join(CHAMPIONS_DIR, champ.id, "matchups.md");
  if (fs.existsSync(matchupsPath)) {
    const md = fs.readFileSync(matchupsPath, "utf-8");
    champ.matchups = parseMatchupsFile(md, nameToId);
  }

  // サブロール対面（matchups-sub.md、2026-05-25 追加）
  // matchups-sub.md は「## vs <name>」が並ぶフォーマット（matchups.md と同じ）。
  // ロール別の構造化は将来対応。今は1リストとして matchupsSub に格納する。
  const matchupsSubPath = path.join(CHAMPIONS_DIR, champ.id, "matchups-sub.md");
  champ.matchupsSub = fs.existsSync(matchupsSubPath)
    ? parseMatchupsFile(fs.readFileSync(matchupsSubPath, "utf-8"), nameToId)
    : [];

  // サブロール判定（subrole-targets.json 由来）
  const subroleEntry = SUBROLE_TARGETS.champions?.[champ.id] || {};
  champ.mainRole = champ.role; // 既存 role を mainRole として明示
  champ.subRoles = Array.isArray(subroleEntry.sub) ? subroleEntry.sub : [];
}

champions.sort((a, b) => a.ja.localeCompare(b.ja, "ja"));

// Phase 3: Data Dragon からスペルデータを並列フェッチ
async function main() {
  // Data Dragon の最新バージョンを動的取得（失敗時は冒頭の fallback 値を使う）
  try {
    const versions = await fetchJSON("https://ddragon.leagueoflegends.com/api/versions.json");
    if (Array.isArray(versions) && versions.length > 0) {
      DDRAGON_VERSION = versions[0];
      console.log(`Data Dragon バージョン: ${DDRAGON_VERSION} (動的取得)`);
    }
  } catch (e) {
    console.warn(`WARN: Data Dragon バージョン取得失敗、fallback ${DDRAGON_VERSION} を使用: ${e.message}`);
  }

  console.log(`${champions.length}体のスペルデータを取得中...`);
  const BATCH_SIZE = 20;
  for (let i = 0; i < champions.length; i += BATCH_SIZE) {
    const batch = champions.slice(i, i + BATCH_SIZE);
    const results = await Promise.all(
      batch.map((c) => fetchSpells(c.ddragonKey))
    );
    for (let j = 0; j < batch.length; j++) {
      batch[j].skills = results[j] || [];
    }
  }
  const skillCount = champions.filter((c) => c.skills.length > 0).length;
  console.log(`スペル取得完了: ${skillCount}/${champions.length}体`);

  const output = {
    meta: {
      ddragonVersion: DDRAGON_VERSION,
      buildDate: new Date().toISOString().split("T")[0],
      championCount: champions.length,
      matchupCount: champions.filter((c) => c.matchups.length > 0).length,
      subroleMatchupCount: champions.filter((c) => c.matchupsSub.length > 0).length,
    },
    champions,
  };

  fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true });
  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2), "utf-8");
  console.log(
    `${output.meta.championCount}体のデータ（matchups: ${output.meta.matchupCount}体）を ${OUTPUT_FILE} に出力しました`
  );
}

main().catch((e) => {
  console.error("ERROR:", e);
  process.exit(1);
});
