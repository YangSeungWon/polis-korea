// nav.js — 상단 nav의 urgent slot 채움. evergreen 메뉴는 sync_nav_html.py가 inline.
// 활성 회차(data/elections/index.json의 active)를 today 기준 phase 산정해
// BLACKOUT/ELECTION/POST/RECENT 면 빨간 chip으로 노출. 그 외 phase는 슬롯 비움.

(async function fillNavUrgent() {
  const slot = document.querySelector('[data-nav-urgent]');
  if (!slot) return;
  let idx;
  try { idx = await fetch('/data/elections/index.json').then((r) => r.json()); }
  catch { return; }
  const today = new Date();
  const items = [];
  for (const id of (idx.active || [])) {
    let meta;
    try { meta = await fetch(`/data/elections/${id}.json`).then((r) => r.json()); }
    catch { continue; }
    if (!meta?.date) continue;
    // 선거일 18시(투표마감)를 기준점으로 — 그 전이 D-day, 그 후가 개표.
    const elDate = new Date(meta.date + 'T18:00:00+09:00');
    const dayMs = 86_400_000;
    const days = Math.floor((today - elDate) / dayMs);
    let phase;
    if (days < -6) continue;                     // CAMPAIGN 이하 — slot 안 띄움
    else if (days < 0) phase = 'BLACKOUT';       // D-6 ~ D-1
    else if (days === 0) phase = 'ELECTION';     // 투표마감 ~ 익일
    else if (days <= 7) phase = 'POST';          // D+1 ~ D+7
    else if (days <= 30) phase = 'RECENT';       // D+8 ~ D+30
    else continue;                               // 30일+ — slot 내림
    const short = shortName(meta);
    const label = labelFor(phase, short, days);
    // archive page 없으면 kind별 hub (재보궐 → byelection.html, 그 외 → home)
    const kind = meta.kind || meta.type;
    const href = meta.archive?.page
      || (kind === 'byelection' ? '/byelection.html' : '/');
    items.push({ phase, label, href });
  }
  if (!items.length) return;
  // 가장 urgent (날짜순 sort — 임박/방금 끝난 거 먼저)
  items.sort((a, b) => phaseOrder(a.phase) - phaseOrder(b.phase));
  slot.innerHTML = items.slice(0, 2).map((it) =>
    `<a href="${it.href}" class="hdr-link hdr-link-urgent hdr-link-urgent-${it.phase.toLowerCase()}">${it.label}</a>`
  ).join('');
})();

function shortName(meta) {
  // "제9회 전국동시지방선거" → "9회 지선", "제22대 국회의원선거" → "22대 총선" 등.
  const n = meta.n;
  const kind = meta.kind || meta.type;
  if (kind === 'local') return `${n}회 지선`;
  if (kind === 'presidential' || kind === 'pres') return `${n}대 대선`;
  if (kind === 'national_assembly' || kind === 'general') return `${n}대 총선`;
  if (kind === 'byelection') {
    const m = (meta.date || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[2]}·${m[3]} 재·보궐` : '재·보궐';
  }
  return meta.short_name || meta.name || '';
}

function labelFor(phase, short, days) {
  if (phase === 'BLACKOUT') return `🔴 ${short} D${days}`;  // days < 0
  if (phase === 'ELECTION') return `🔴 LIVE ${short} 개표`;
  if (phase === 'POST') return `${short} 결과`;
  if (phase === 'RECENT') return `${short} 결과`;
  return short;
}

function phaseOrder(p) {
  return { ELECTION: 0, BLACKOUT: 1, POST: 2, RECENT: 3 }[p] ?? 9;
}
