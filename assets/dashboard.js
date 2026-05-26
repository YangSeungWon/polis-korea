// dashboard.js — 랜딩 대시보드. 3패널(광역단체장·기초단체장·재보궐) 레벨2 맛보기.
// 색칠 hex + 정당색 범례 + 한 줄 요약. 호버/드릴 없음 — "자세히 →" 풀뷰로.
// 의존: parties.js(partyColor, SIDO_HEX_LAYOUT), utils.js(summarizeLatest, canonSido), hexgrid.js.

const ELECTION = new Date('2026-06-03T00:00:00+09:00');
const BLACKOUT_START = new Date('2026-05-28T00:00:00+09:00');
const BLACKOUT_END = new Date('2026-06-03T18:00:00+09:00');
const NS = 'http://www.w3.org/2000/svg';
const $ = (s) => document.querySelector(s);

const seenParties = new Set();  // 범례용 — 패널에 등장한 정당

async function init() {
  const days = Math.ceil((ELECTION - Date.now()) / 86_400_000);
  const cd = $('#countdown');
  if (cd) cd.textContent = days > 0 ? `지선 D-${days}` : (days === 0 ? '선거 당일' : `선거 후 ${-days}일`);

  let polls = [], sgHex = [], boe = null;
  try {
    const [agg, sg, by] = await Promise.all([
      fetch('data/polls/aggregated.json').then((r) => r.json()),
      fetch('data/geo/sigungu_hex.json').then((r) => r.json()),
      fetch('data/polls/byelection.json').then((r) => r.json()).catch(() => null),
    ]);
    polls = (agg.polls || []).filter((p) => !p.is_self_poll);
    const now = new Date();
    if (now >= BLACKOUT_START && now < BLACKOUT_END) {
      polls = polls.filter((p) => p.period_end && p.period_end < '2026-05-28');
    }
    sgHex = sg; boe = by;
  } catch (e) { /* 빈 화면 */ }

  renderGovernor(polls);
  renderMayor(polls, sgHex);
  renderByelection(boe);
  renderLegend();
  $('#dash-loading')?.setAttribute('hidden', '');
}

// 한 패널 hex 그리기 (cells: {c,r,fill,label,dark,title})
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

// 광역단체장 — 17 시도 hex (라벨 포함)
function renderGovernor(polls) {
  const svg = $('#dash-governor');
  if (!svg) return;
  const gw = polls.filter((p) => p.office_level === '광역단체장' && !p.sigungu);
  const bySido = {};
  for (const p of gw) {
    const s = canonSido(p.sido);
    (bySido[s] = bySido[s] || []).push(p);
  }
  const seen = new Set();
  const cells = [];
  for (const [sido, pos] of Object.entries(SIDO_HEX_LAYOUT)) {
    const key = `${pos.col},${pos.row}`;
    if (seen.has(key)) continue;  // 전라북도 alias 등 중복 셀 skip
    seen.add(key);
    const top = summarizeLatest(bySido[canonSido(sido)] || []);
    if (top) seenParties.add(top.party);
    cells.push({
      c: pos.col, r: pos.row,
      fill: top ? partyColor(top.party) : '#e6e9ef',
      label: pos.label, dark: !!top,
      title: top ? `${pos.label} · ${top.party} ${top.pct}%` : `${pos.label} · 조사 없음`,
    });
  }
  drawHexPanel(svg, cells, 26, false);
}

// 기초단체장 — 250 시군구 hex (라벨 없음, 색 패턴)
function renderMayor(polls, sgHex) {
  const svg = $('#dash-mayor');
  if (!svg || !sgHex.length) return;
  const gc = polls.filter((p) => p.office_level === '기초단체장' && p.sigungu);
  const byKey = {};
  for (const p of gc) {
    const k = `${canonSido(p.sido)}|${p.sigungu}`;
    (byKey[k] = byKey[k] || []).push(p);
  }
  let covered = 0;
  const cells = sgHex.map((h) => {
    const top = summarizeLatest(byKey[`${canonSido(h.sido)}|${h.name}`] || []);
    if (top) { seenParties.add(top.party); covered++; }
    return {
      c: h.c, r: h.r, sido: h.sido,
      fill: top ? partyColor(top.party) : '#e6e9ef',
      title: top ? `${h.name} · ${top.party} ${top.pct}%` : `${h.name} · 조사 없음`,
    };
  });
  drawHexPanel(svg, cells, 8.5, true);
  const note = $('#dash-mayor-note');
  if (note) note.textContent = `시군구 ${covered}곳 조사`;
}

// 재보궐 — 7 선거구 리스트 (점 + 선거구 + 1위)
function renderByelection(boe) {
  const wrap = $('#dash-boe-list');
  if (!wrap) return;
  if (!boe || !boe.districts?.length) {
    wrap.innerHTML = '<div class="dash-empty">데이터 없음</div>';
    return;
  }
  wrap.innerHTML = boe.districts.map((d) => {
    const latest = d.polls?.[0];
    const top = latest?.candidates?.length
      ? latest.candidates.reduce((a, b) => (a.pct >= b.pct ? a : b)) : null;
    if (top) seenParties.add(top.party);
    const color = top ? partyColor(top.party) : '#888';
    return `<div class="dash-boe-item">
      <span class="dash-dot" style="background:${color}"></span>
      <span class="dash-boe-name">${d.district}</span>
      <span class="dash-boe-top" style="color:${color}">${top ? `${top.name} ${top.pct}%` : '—'}</span>
    </div>`;
  }).join('');
}

// 정당색 범례 — 패널에 등장한 정당 (의석 많을 법한 순서로 정렬은 생략, 주요당 우선)
function renderLegend() {
  const wrap = $('#dash-legend');
  if (!wrap) return;
  const ORDER = ['더불어민주당', '국민의힘', '조국혁신당', '개혁신당', '진보당', '무소속'];
  const CANON = { 민주당: '더불어민주당', 국힘: '국민의힘' };  // polls.js 범례와 동일 정규화
  const parties = [...new Set([...seenParties].map((p) => CANON[p] || p || '무소속'))]
    .sort((a, b) => {
      const ia = ORDER.indexOf(a), ib = ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
  wrap.innerHTML = parties.map((p) =>
    `<span class="dash-leg-item"><span class="dash-dot" style="background:${partyColor(p)}"></span>${p}</span>`
  ).join('') + '<span class="dash-leg-item"><span class="dash-dot" style="background:#e6e9ef"></span>조사 없음</span>';
}

init();
