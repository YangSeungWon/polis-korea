// dashboard.js — 랜딩 대시보드. 3패널(광역단체장·기초단체장·재보궐) 레벨2 맛보기.
// 색칠 hex + 정당색 범례 + 한 줄 요약. 호버/드릴 없음 — "자세히 →" 풀뷰로.
// 시간 phase 따라 데이터 source 자동 전환 (폴 ↔ 잠정 결과 ↔ 확정 결과).

const ELECTION = new Date('2026-06-03T00:00:00+09:00');
const BLACKOUT_START = new Date('2026-05-28T00:00:00+09:00');
const BLACKOUT_END = new Date('2026-06-03T18:00:00+09:00');
const NS = 'http://www.w3.org/2000/svg';
const $ = (s) => document.querySelector(s);

const seenParties = new Set();

// === Phase 판단 — D-day 기준 offset 일수 ===
function getPhase() {
  const days = Math.floor((Date.now() - ELECTION.getTime()) / 86_400_000);
  if (days < -180) return 'PRE';        // 6개월+ 전
  if (days < -7) return 'CAMPAIGN';     // 6개월 ~ D-8
  if (days < 0) return 'BLACKOUT';      // D-7 ~ D-1 공표금지
  if (days === 0) return 'ELECTION';    // 선거 당일
  if (days <= 7) return 'POST';         // D+1 ~ D+7
  if (days <= 180) return 'RECENT';     // D+8 ~ D+180
  return 'ARCHIVED';                    // D+180+
}

const PHASE_META = {
  PRE:       { title: '활성 · 9회 지선 · 1년 이전', subtitle: '여론조사 본격 수집 전', source: null },
  CAMPAIGN:  { title: '활성 · 9회 지선 + 재·보궐', subtitle: '17개 시·도 · 마지막 조사 1위', source: 'polls' },
  BLACKOUT:  { title: '활성 · 9회 지선 · 공표금지 중', subtitle: '5/27 이전 등록 조사만 표시', source: 'polls' },
  ELECTION:  { title: '9회 지선 · 개표 중', subtitle: '17개 시·도 · 잠정 1위', source: 'results' },
  POST:      { title: '9회 지선 · 결과', subtitle: '17개 시·도 · 1위 정당', source: 'results', dateNote: true },
  RECENT:    { title: '최근 회차 · 9회 지선', subtitle: '17개 시·도 · 1위 정당', source: 'results' },
  ARCHIVED:  { title: '다음 회차 준비 중', subtitle: '10회 지선 ~2030', source: null },
};

async function init() {
  const phase = getPhase();
  const meta = PHASE_META[phase];

  // countdown 라벨
  const days = Math.floor((Date.now() - ELECTION.getTime()) / 86_400_000);
  const cd = $('#countdown');
  if (cd) cd.textContent = days < 0 ? `지선 D${days}` : (days === 0 ? '선거 당일' : `선거 후 ${days}일`);

  // 섹션 title 갱신
  const titleEl = document.querySelector('.dash-section .dash-section-title');
  if (titleEl) titleEl.textContent = meta.title;

  // ARCHIVED·PRE는 데이터 fetch X — 대신 안내 표시
  if (!meta.source) {
    renderEmpty(meta);
    $('#dash-loading')?.setAttribute('hidden', '');
    return;
  }

  let polls = [], sgHex = [], boe = null, results = null, byResults = null;
  try {
    const [sg, by, agg] = await Promise.all([
      fetch('data/geo/sigungu_hex.json').then((r) => r.json()),
      fetch('data/polls/byelection.json').then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch('data/polls/aggregated.json').then((r) => r.ok ? r.json() : null).catch(() => null),
    ]);
    sgHex = sg; boe = by;
    polls = (agg?.polls || []).filter((p) => !p.is_self_poll);
    if (phase === 'BLACKOUT') {
      polls = polls.filter((p) => p.period_end && p.period_end < '2026-05-28');
    }
    if (meta.source === 'results') {
      results = await fetch('data/results/9th-local-2026.json').then((r) => r.ok ? r.json() : null).catch(() => null);
      byResults = await fetch('data/results/9th-byelection-2026.json').then((r) => r.ok ? r.json() : null).catch(() => null);
    }
  } catch (e) { /* graceful */ }

  // sub-line
  const govSub = document.querySelector('[data-slot-sub="governor"]');
  if (govSub) govSub.textContent = `17개 시·도 · ${meta.source === 'results' ? '1위 정당' : '마지막 조사 1위'}`;
  const mayorSub = document.querySelector('[data-slot-sub="mayor"]');
  if (mayorSub) mayorSub.textContent = `${meta.source === 'results' ? '시군구 결과 1위' : '시군구 단위'} · ${meta.source === 'results' ? '1위 정당' : '마지막 조사 1위'}`;
  const boeSub = document.querySelector('[data-slot-sub="byelection"]');
  if (boeSub) boeSub.textContent = `${meta.source === 'results' ? '14 선거구 결과' : '7 선거구 · 마지막 조사 1위'}`;

  renderGovernor(polls, results);
  renderMayor(polls, sgHex, results);
  renderByelectionPanel(boe, byResults);
  renderLegend();
  $('#dash-loading')?.setAttribute('hidden', '');
}

function renderEmpty(meta) {
  // PRE / ARCHIVED — section 전체 텅 빈 안내
  const subEl = document.querySelectorAll('.dash-panel .dash-sub');
  subEl.forEach((e) => { e.textContent = meta.subtitle; });
  // hex svg 비우기
  for (const id of ['#dash-governor', '#dash-mayor']) {
    const svg = $(id); if (svg) svg.innerHTML = '';
  }
  const wrap = $('#dash-boe-list'); if (wrap) wrap.innerHTML = '';
}

function drawHexPanel(svg, cells, r, drawBorders) {
  svg.innerHTML = '';
  const cs = cells.map((c) => c.c), rs = cells.map((c) => c.r);
  const minC = Math.min(...cs), maxC = Math.max(...cs), minR = Math.min(...rs), maxR = Math.max(...rs);
  const colW = r * Math.sqrt(3), rowH = r * 1.5;
  const offX = -minC * colW + colW / 2 + 2, offY = -minR * rowH + rowH + 2;
  svg.setAttribute('viewBox', `0 0 ${Math.ceil((maxC - minC + 2) * colW)} ${Math.ceil((maxR - minR + 2) * rowH)}`);
  const cellAt = new Map();
  for (const c of cells) cellAt.set(`${c.c},${c.r}`, c);
  for (const cell of cells) {
    const [cx, cy] = hexCenter(cell.c, cell.r, colW, rowH, offX, offY);
    const poly = document.createElementNS(NS, 'polygon');
    poly.setAttribute('points', hexPoints(cx, cy, r - 0.5));
    poly.setAttribute('fill', cell.fill);
    poly.setAttribute('stroke', '#fff');
    poly.setAttribute('stroke-width', '0.6');
    if (cell.title) {
      const tt = document.createElementNS(NS, 'title');
      tt.textContent = cell.title;
      poly.appendChild(tt);
    }
    svg.appendChild(poly);
    if (cell.label) {
      const t = document.createElementNS(NS, 'text');
      t.setAttribute('x', cx); t.setAttribute('y', cy + r * 0.18);
      t.setAttribute('text-anchor', 'middle');
      t.setAttribute('font-size', (r * 0.5).toFixed(1));
      t.setAttribute('font-weight', '700');
      t.setAttribute('fill', cell.dark ? '#fff' : '#4d5570');
      t.setAttribute('pointer-events', 'none');
      t.textContent = cell.label;
      svg.appendChild(t);
    }
  }
  if (drawBorders) drawHexBorders(svg, cells, cellAt, colW, rowH, offX, offY, r, '1.2', true);
}

// 광역단체장 — 17 시도 hex (라벨 포함). 폴 vs 결과 source 자동 전환.
function renderGovernor(polls, results) {
  const svg = $('#dash-governor');
  if (!svg) return;
  // source: results 우선 (결과 데이터 있으면), 아니면 폴
  const useResults = !!results;
  let bySido = {};  // sido → { party, pct }
  if (useResults) {
    const sidoRaces = (results.races || []).filter((r) => r.scope === 'sido' && r.sg_typecode === '3');
    for (const r of sidoRaces) {
      const top = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0))[0];
      if (top) bySido[canonSido(r.sido)] = { party: top.party, pct: top.pct };
    }
  } else {
    const gw = polls.filter((p) => p.office_level === '광역단체장' && !p.sigungu);
    const sidoPolls = {};
    for (const p of gw) (sidoPolls[canonSido(p.sido)] = sidoPolls[canonSido(p.sido)] || []).push(p);
    for (const [s, ps] of Object.entries(sidoPolls)) {
      const top = summarizeLatest(ps);
      if (top) bySido[s] = top;
    }
  }
  const seen = new Set();
  const cells = [];
  for (const [sido, pos] of Object.entries(SIDO_HEX_LAYOUT)) {
    const key = `${pos.col},${pos.row}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const top = bySido[canonSido(sido)];
    if (top) seenParties.add(top.party);
    cells.push({
      c: pos.col, r: pos.row,
      fill: top ? partyColor(top.party) : '#e6e9ef',
      label: pos.label, dark: !!top,
      title: top
        ? `${pos.label} · ${top.party} ${typeof top.pct === 'number' ? top.pct.toFixed(1) : top.pct}%`
        : `${pos.label} · 데이터 없음`,
    });
  }
  drawHexPanel(svg, cells, 26, false);
}

// 기초단체장 — 250 시군구 hex
function renderMayor(polls, sgHex, results) {
  const svg = $('#dash-mayor');
  if (!svg || !sgHex.length) return;
  const useResults = !!results;
  let byKey = {};  // 'sido|name' → { party, pct }
  if (useResults) {
    const sigunguRaces = (results.races || []).filter((r) => r.scope === 'sigungu' && r.sg_typecode === '4');
    for (const r of sigunguRaces) {
      const top = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0))[0];
      if (top) byKey[`${canonSido(r.sido)}|${r.sigungu}`] = { party: top.party, pct: top.pct };
    }
  } else {
    const gc = polls.filter((p) => p.office_level === '기초단체장' && p.sigungu);
    const kPolls = {};
    for (const p of gc) {
      const k = `${canonSido(p.sido)}|${p.sigungu}`;
      (kPolls[k] = kPolls[k] || []).push(p);
    }
    for (const [k, ps] of Object.entries(kPolls)) {
      const top = summarizeLatest(ps);
      if (top) byKey[k] = top;
    }
  }
  let covered = 0;
  const cells = sgHex.map((h) => {
    const top = byKey[`${canonSido(h.sido)}|${h.name}`];
    if (top) { seenParties.add(top.party); covered++; }
    return {
      c: h.c, r: h.r, sido: h.sido,
      fill: top ? partyColor(top.party) : '#e6e9ef',
      title: top
        ? `${h.name} · ${top.party} ${typeof top.pct === 'number' ? top.pct.toFixed(1) : top.pct}%`
        : `${h.name} · 데이터 없음`,
    };
  });
  drawHexPanel(svg, cells, 8.5, true);
  const note = $('#dash-mayor-note');
  if (note) note.textContent = useResults ? `시군구 ${covered}곳 결과` : `시군구 ${covered}곳 조사`;
}

// 재보궐 — 폴 vs 결과 자동 전환
function renderByelectionPanel(boe, byResults) {
  const wrap = $('#dash-boe-list');
  if (!wrap) return;
  const useResults = !!byResults;
  let items = [];
  if (useResults) {
    const districts = (byResults.races || []).filter((r) => r.scope === 'district' && r.sg_typecode === '2');
    items = districts.map((r) => {
      const top = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0))[0];
      return { name: `${r.sido} ${r.district || ''}`, party: top?.party, label: top ? `${top.name} ${top.pct?.toFixed(1)}%` : '—' };
    });
  } else if (boe?.districts?.length) {
    items = boe.districts.map((d) => {
      const latest = d.polls?.[0];
      const top = latest?.candidates?.length
        ? latest.candidates.reduce((a, b) => (a.pct >= b.pct ? a : b)) : null;
      return { name: d.district, party: top?.party, label: top ? `${top.name} ${top.pct}%` : '—' };
    });
  }
  if (!items.length) {
    wrap.innerHTML = '<div class="dash-empty">데이터 없음</div>';
    return;
  }
  wrap.innerHTML = items.map((d) => {
    if (d.party) seenParties.add(d.party);
    const color = d.party ? partyColor(d.party) : '#888';
    return `<div class="dash-boe-item">
      <span class="dash-dot" style="background:${color}"></span>
      <span class="dash-boe-name">${d.name}</span>
      <span class="dash-boe-top" style="color:${color}">${d.label}</span>
    </div>`;
  }).join('');
}

function renderLegend() {
  const wrap = $('#dash-legend');
  if (!wrap) return;
  const ORDER = ['더불어민주당', '국민의힘', '조국혁신당', '개혁신당', '진보당', '무소속'];
  const CANON = { 민주당: '더불어민주당', 국힘: '국민의힘' };
  const parties = [...new Set([...seenParties].map((p) => CANON[p] || p || '무소속'))]
    .sort((a, b) => {
      const ia = ORDER.indexOf(a), ib = ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
  wrap.innerHTML = parties.map((p) =>
    `<span class="dash-leg-item"><span class="dash-dot" style="background:${partyColor(p)}"></span>${p}</span>`
  ).join('') + '<span class="dash-leg-item"><span class="dash-dot" style="background:#e6e9ef"></span>데이터 없음</span>';
}

init();
