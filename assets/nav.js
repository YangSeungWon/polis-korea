// nav.js — 상단 nav의 urgent slot + 헤더 검색 주입. evergreen 메뉴는 sync_nav_html.py가 inline.
// 활성 회차(data/elections/index.json의 active)를 today 기준 phase 산정해
// BLACKOUT/ELECTION/POST/RECENT 면 빨간 chip으로 노출. 그 외 phase는 슬롯 비움.

// 헤더 우측 검색 — 전 페이지 공통(단일 소스). HTML 복제 없이 여기서 .hdr-meta에 1회 주입.
// 데스크톱=입력창, 모바일=🔍 아이콘만(빈 제출 → /search.html). CSS: .hdr-search (common.css).
(function injectHeaderSearch() {
  const meta = document.querySelector('.hdr-meta');
  if (!meta || meta.querySelector('.hdr-search')) return;
  const form = document.createElement('form');
  form.className = 'hdr-search';
  form.action = '/search.html';
  form.method = 'get';
  form.setAttribute('role', 'search');
  form.setAttribute('aria-label', '검색');
  form.innerHTML =
    '<input type="search" name="q" placeholder="검색" autocomplete="off" aria-label="당선인·지역·정당 검색">'
    + '<button type="submit" class="hdr-search-btn" aria-label="검색">'
    + '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M11 4a7 7 0 1 1 0 14 7 7 0 0 1 0-14zm5.3 12.3l4 4"/></svg>'
    + '</button>';
  meta.insertBefore(form, meta.firstChild);
})();

// 모바일 nav 더보기 — 폭 좁으면(≤640px) nav 링크를 드롭다운으로 접음. CSS: .nav-toggle/.is-open.
// nav.js가 전 페이지 공통이라 89개 HTML 안 건드리고 여기서 토글만 주입.
(function injectNavToggle() {
  const hdr = document.querySelector('.site-hdr');
  const nav = document.querySelector('.hdr-nav');
  const meta = document.querySelector('.hdr-meta');
  if (!hdr || !nav || !meta || meta.querySelector('.nav-toggle')) return;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'nav-toggle';
  btn.setAttribute('aria-label', '메뉴');
  btn.setAttribute('aria-expanded', 'false');
  btn.textContent = '더보기';
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = hdr.classList.toggle('is-open');
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  nav.addEventListener('click', () => hdr.classList.remove('is-open'));        // 항목 선택 시 닫기
  document.addEventListener('click', (e) => {                                  // 바깥 클릭 닫기
    if (!hdr.contains(e.target)) hdr.classList.remove('is-open');
  });
  meta.appendChild(btn);
})();

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
  // 모바일 더보기 안에 긴급 칩이 숨으므로 토글에 빨간 점 표시(선거 임박/개표).
  document.querySelector('.nav-toggle')?.classList.add('has-urgent');
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
