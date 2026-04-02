import sharp from 'sharp';

const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <radialGradient id="glow1" cx="30%" cy="20%" r="50%">
      <stop offset="0%" stop-color="#c89b3c" stop-opacity="0.15"/>
      <stop offset="100%" stop-color="#0a0e14" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glow2" cx="70%" cy="80%" r="50%">
      <stop offset="0%" stop-color="#2ecc71" stop-opacity="0.10"/>
      <stop offset="100%" stop-color="#0a0e14" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="goldLine" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#0a0e14"/>
      <stop offset="30%" stop-color="#c89b3c"/>
      <stop offset="70%" stop-color="#c89b3c"/>
      <stop offset="100%" stop-color="#0a0e14"/>
    </linearGradient>
    <linearGradient id="vertGold" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="transparent"/>
      <stop offset="50%" stop-color="#c89b3c"/>
      <stop offset="100%" stop-color="transparent"/>
    </linearGradient>
    <filter id="titleGlow">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>

  <!-- 背景 -->
  <rect width="1200" height="630" fill="#0a0e14"/>
  <rect width="1200" height="630" fill="url(#glow1)"/>
  <rect width="1200" height="630" fill="url(#glow2)"/>

  <!-- 上下ゴールドライン -->
  <rect x="0" y="0" width="1200" height="3" fill="url(#goldLine)"/>
  <rect x="0" y="627" width="1200" height="3" fill="url(#goldLine)"/>

  <!-- 左サイド装飾 -->
  <rect x="48" y="230" width="3" height="80" fill="url(#vertGold)" opacity="0.4"/>
  <rect x="48" y="330" width="3" height="40" fill="url(#vertGold)" opacity="0.25"/>

  <!-- 右サイド装飾 -->
  <rect x="1149" y="230" width="3" height="80" fill="url(#vertGold)" opacity="0.4"/>
  <rect x="1149" y="330" width="3" height="40" fill="url(#vertGold)" opacity="0.25"/>

  <!-- VSバッジ -->
  <rect x="564" y="155" width="72" height="72" rx="16" fill="#141a24" stroke="#c89b3c" stroke-width="2"/>
  <text x="600" y="202" text-anchor="middle" font-family="Noto Sans CJK JP,sans-serif" font-size="32" font-weight="bold" fill="#c89b3c" letter-spacing="2">VS</text>
  <!-- VSバッジのグロー -->
  <rect x="564" y="155" width="72" height="72" rx="16" fill="none" stroke="#c89b3c" stroke-width="1" opacity="0.3" filter="url(#titleGlow)"/>

  <!-- タイトル -->
  <text x="600" y="295" text-anchor="middle" font-family="Noto Sans CJK JP,sans-serif" font-size="60" font-weight="800" fill="#ffffff" letter-spacing="4" filter="url(#titleGlow)">LoL マッチアップガイド</text>

  <!-- サブタイトル -->
  <text x="600" y="345" text-anchor="middle" font-family="Noto Sans CJK JP,sans-serif" font-size="26" fill="#8895a7" letter-spacing="2">全チャンピオンの対面攻略を日本語で解説</text>

  <!-- ロールタグ -->
  <g transform="translate(600, 410)">
    <rect x="-280" y="-20" width="88" height="40" rx="20" fill="#141a24" stroke="#2a3545" stroke-width="1"/>
    <text x="-236" y="8" text-anchor="middle" font-family="Noto Sans CJK JP,sans-serif" font-size="18" font-weight="600" fill="#c89b3c">TOP</text>

    <rect x="-168" y="-20" width="76" height="40" rx="20" fill="#141a24" stroke="#2a3545" stroke-width="1"/>
    <text x="-130" y="8" text-anchor="middle" font-family="Noto Sans CJK JP,sans-serif" font-size="18" font-weight="600" fill="#c89b3c">JG</text>

    <rect x="-68" y="-20" width="80" height="40" rx="20" fill="#141a24" stroke="#2a3545" stroke-width="1"/>
    <text x="-28" y="8" text-anchor="middle" font-family="Noto Sans CJK JP,sans-serif" font-size="18" font-weight="600" fill="#c89b3c">MID</text>

    <rect x="36" y="-20" width="84" height="40" rx="20" fill="#141a24" stroke="#2a3545" stroke-width="1"/>
    <text x="78" y="8" text-anchor="middle" font-family="Noto Sans CJK JP,sans-serif" font-size="18" font-weight="600" fill="#c89b3c">ADC</text>

    <rect x="144" y="-20" width="80" height="40" rx="20" fill="#141a24" stroke="#2a3545" stroke-width="1"/>
    <text x="184" y="8" text-anchor="middle" font-family="Noto Sans CJK JP,sans-serif" font-size="18" font-weight="600" fill="#c89b3c">SUP</text>
  </g>

  <!-- 統計 -->
  <text x="600" y="490" text-anchor="middle" font-family="Noto Sans CJK JP,sans-serif" font-size="20" fill="#2ecc71" letter-spacing="1">170 Champions ・ 1,360+ Matchups</text>
</svg>`;

await sharp(Buffer.from(svg)).png().toFile('/home/ojita/lol-guides-jp/docs/ogp.png');
console.log('OGP画像を生成しました: docs/ogp.png');
