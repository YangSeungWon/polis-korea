// 9회 지선 여론조사 페이지 메인 스크립트.
// 데이터: data/polls/aggregated.json (build_polls.py 산출물).
// 의존: regions.js, parties.js, utils.js, Leaflet.

const ELECTION = new Date('2026-06-03T00:00:00+09:00');
const BLACKOUT_START = new Date('2026-05-28T00:00:00+09:00');
const BLACKOUT_END = new Date('2026-06-03T18:00:00+09:00');

const state = {
  data: null,
  view: 'hex',   // 메인이 hex이므로 세부 페이지도 격자 기본 (지도는 토글)
  office: '광역단체장',
  scope: '시도',  // 시도 / 시군구 — 정당지지/국정평가/투표의향에 해당
  selectedSido: null,
  selectedSigungu: null,
  blackoutActive: false,
};

const $ = (sel) => document.querySelector(sel);

function setCountdown() {
  const now = new Date();
  const ms = ELECTION - now;
  const days = Math.ceil(ms / 86400000);
  $('#countdown').textContent = days > 0 ? `선거 D-${days}` : (days === 0 ? '선거 당일' : `선거 후 ${-days}일`);
  // 블랙아웃 판정
  state.blackoutActive = now >= BLACKOUT_START && now < BLACKOUT_END;
  $('#blackout-tag').hidden = !state.blackoutActive;
  $('#legal-banner').hidden = !state.blackoutActive;
}

async function loadData() {
  try {
    const r = await fetch('data/polls/aggregated.json');
    if (!r.ok) throw new Error('데이터 없음');
    state.data = await r.json();
  } catch (e) {
    state.data = { _meta: {}, polls: [] };
  }
  // 블랙아웃이면 5/28 이전 조사만 노출
  if (state.blackoutActive) {
    state.data.polls = state.data.polls.filter((p) => {
      if (!p.period_end) return false;
      return p.period_end < '2026-05-28';
    });
  }
  // 정당·후보 자체 의뢰 제외
  state.data.polls = state.data.polls.filter((p) => !p.is_self_poll);
  // 셀별로 조사 시점 다르므로 헤더에는 일반 안내만 (init time에 이미 박혀있음)
  $('#loading').hidden = true;
}

function pollsByOffice(office) {
  return state.data.polls.filter((p) => p.office_level === office);
}

function pollsByRegion(sido, sigungu = null) {
  let arr = state.data.polls;
  if (sido) arr = arr.filter((p) => p.sido === sido);
  if (sigungu) arr = arr.filter((p) => p.sigungu === sigungu);
  return arr.sort((a, b) => (b.period_end || '').localeCompare(a.period_end || ''));
}

// summarizeLatest (시간감쇠 가중 1위 집계) → utils.js (대시보드와 공용)

function sidoLastWinningParty(sido, office) {
  return summarizeLatest(pollsByOffice(office).filter((p) => p.sido === sido && !p.sigungu));
}

// 시군구 단위 — 기초단체장은 office_level='기초단체장', 그외 메트릭(정당지지/국정평가/투표의향)은
// office_level이 메트릭 자체. sigungu 필드가 있는 polls만 사용.
function sigunguLastWinningParty(sido, sigungu, office = '기초단체장') {
  return summarizeLatest(pollsByOffice(office).filter(
    (p) => p.sido === sido && p.sigungu === sigungu
  ));
}

// === HEX 격자 ===
// hexPoints·nbrs·NBR_TO_EDGE·corner → assets/hexgrid.js (공용)

function renderHex() {
  const svg = $('#hex');
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  const r = 56; // hex radius — 6행 4컬럼 그리드
  const colW = r * Math.sqrt(3);  // ≈ 97
  const rowH = r * 1.5;            // = 84
  // col 1~4 사용. col 1을 x ≈ 75에 배치.
  const offsetX = 75 - colW;
  const offsetY = 70;

  // 빈 자리 dummy 먼저 (z-order 하단)
  for (const blank of (SIDO_HEX_BLANKS || [])) {
    const [cx, cy] = hexCenter(blank.col, blank.row, colW, rowH, offsetX, offsetY);
    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', 'hex-cell no-data');
    poly.setAttribute('points', hexPoints(cx, cy, r - 2));
    svg.appendChild(poly);
  }

  for (const [sido, pos] of Object.entries(SIDO_HEX_LAYOUT)) {
    // skip 전라북도 duplicate (사용은 전북특별자치도)
    if (sido === '전라북도') continue;
    const [cx, cy] = hexCenter(pos.col, pos.row, colW, rowH, offsetX, offsetY);
    const result = sidoLastWinningParty(sido, state.office);
    const fill = result ? partyColor(result.party) : '#e6e9ef';
    const cls = result ? 'hex-cell has-data' : 'hex-cell no-data';
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('data-sido', sido);
    g.setAttribute('transform', `translate(0,0)`);

    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', cls + (state.selectedSido === sido ? ' is-selected' : ''));
    poly.setAttribute('points', hexPoints(cx, cy, r - 2));
    poly.setAttribute('fill', fill);
    poly.setAttribute('stroke', '#0a0e1a');
    poly.setAttribute('stroke-width', '1.2');
    poly.setAttribute('fill-opacity', result ? gapOpacity(result.gap) : '1');
    g.appendChild(poly);

    const t1 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t1.setAttribute('class', 'hex-label');
    t1.setAttribute('x', cx);
    t1.setAttribute('y', cy + 2);
    t1.setAttribute('fill', result ? '#fff' : '#1b2237');
    t1.textContent = pos.label;
    g.appendChild(t1);

    if (result) {
      const t2 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t2.setAttribute('class', 'hex-pct');
      t2.setAttribute('x', cx);
      t2.setAttribute('y', cy + 20);
      t2.setAttribute('fill', '#fff');
      const lbl = result.name || result.party || '';
      // 긴 정당명·후보명일 때 폰트 동적 축소 (시도 hex radius 56 안에 맞춤)
      const total = lbl.length + String(result.pct).length + 2;
      const fs = total >= 14 ? '7px' : total >= 11 ? '9px' : '11px';
      t2.style.fontSize = fs;  // CSS .hex-pct 덮음
      t2.textContent = `${lbl} ${result.pct}%`;
      g.appendChild(t2);
    }

    g.style.cursor = result ? 'pointer' : 'default';
    g.addEventListener('click', () => {
      state.selectedSido = sido;
      state.selectedSigungu = null;
      renderHex();
      renderDetail();
    });
    svg.appendChild(g);
  }
}

// === 지리 지도 (Leaflet) ===

let leafletMap = null;
let sidoLayer = null;
let sigunguLayer = null;
let sidoOutlineLayer = null;  // 시군구 모드에서 위에 오버레이되는 시도 외곽선 전용
let miniMapCtrl = null;
let initialZoom = null;  // sidoLayer 로드 후 fitBounds로 결정
// 한국 경계 — 제주(33) ~ 강원북 (39), 백령(124) ~ 독도(132). 패닝 제한.
const KOREA_BOUNDS = [[32.5, 123.5], [39.5, 132.5]];

function setupMiniMap(sidoData) {
  if (miniMapCtrl || typeof L.Control.MiniMap === 'undefined') return;
  const miniLayer = L.geoJSON(sidoData, {
    style: { color: '#999', weight: 0.6, fillColor: '#e0e3ea', fillOpacity: 0.85 },
    interactive: false,
  });
  // 한반도 본토 위주 — 독도/울릉 등 동쪽 outlier 제외해 세로 비율 유지.
  const MAINLAND = L.latLngBounds([32.8, 125.6], [38.8, 130.0]);
  const TARGET_H = 170;
  let miniZoom = initialZoom;
  let sw, ne, miniW, miniH;
  for (let i = 0; i < 8; i++) {
    sw = leafletMap.project(MAINLAND.getSouthWest(), miniZoom);
    ne = leafletMap.project(MAINLAND.getNorthEast(), miniZoom);
    miniH = sw.y - ne.y;
    if (miniH > TARGET_H * 1.4 && miniZoom > 0) { miniZoom--; continue; }
    if (miniH < TARGET_H * 0.7) { miniZoom++; continue; }
    break;
  }
  miniW = Math.ceil(ne.x - sw.x) + 12;
  miniH = Math.ceil(miniH) + 12;
  miniMapCtrl = new L.Control.MiniMap(miniLayer, {
    position: 'bottomleft',
    width: miniW,
    height: miniH,
    toggleDisplay: false,
    zoomLevelFixed: miniZoom,
    centerFixed: MAINLAND.getCenter(),
    aimingRectOptions: {
      color: '#e61e2b',
      weight: 2,
      fillColor: '#e61e2b',
      fillOpacity: 0.15,
    },
  }).addTo(leafletMap);
  // 미니맵 자체는 늘 표시. 빨간 viewport rect은 확대 시에만 노출.
  const updateMini = () => {
    const path = miniMapCtrl._aimingRect && miniMapCtrl._aimingRect._path;
    if (!path) return;
    path.style.display = leafletMap.getZoom() > initialZoom ? '' : 'none';
  };
  leafletMap.on('zoomend', updateMini);
  leafletMap.on('moveend', updateMini);
  setTimeout(updateMini, 0);
}

async function renderMap() {
  if (!leafletMap) {
    leafletMap = L.map('map', {
      zoomControl: true,
      attributionControl: false,
      maxBounds: KOREA_BOUNDS,
      maxBoundsViscosity: 1.0,        // 경계 밖으로 못 끌리게
    });
    // setView는 일단 임시값. sidoLayer 로드 후 fitBounds로 진짜 초기 뷰 잡음.
    leafletMap.setView([35.9, 127.8], 6);
    window.leafletMap = leafletMap;  // debug
  }
  const sigungu = isSigunguMode();

  // GeoJSON 로드 (시도·시군구) — 제주·울릉·서해5도 포함 전체
  if (!sidoLayer) {
    const sidoData = await (await fetch('data/geo/sido_simple.json')).json();
    sidoLayer = L.geoJSON(sidoData, {
      style: (f) => sidoStyle(f),
      onEachFeature: (f, l) => attachSidoClick(f, l),
    });
    // fitBounds → maxBounds 자동 보정까지 다 끝난 뒤 zoom 확정.
    leafletMap.invalidateSize();
    leafletMap.fitBounds(sidoLayer.getBounds(), { padding: [12, 12] });
    const finalize = () => {
      leafletMap.off('moveend', finalize);
      initialZoom = leafletMap.getZoom();
      leafletMap.setMinZoom(initialZoom);
      setupMiniMap(sidoData);
    };
    leafletMap.on('moveend', finalize);
  }
  if (!sigunguLayer) {
    const sigunguData = await (await fetch('data/geo/sigungu_simple.json')).json();
    sigunguLayer = L.geoJSON(sigunguData, {
      style: (f) => sigunguStyle(f),
      onEachFeature: (f, l) => attachSigunguClick(f, l),
    });
  }

  // 시도 외곽 전용 layer (시군구 모드 오버레이용) — 한 번만 생성
  if (!sidoOutlineLayer) {
    const sidoData = sidoLayer.toGeoJSON();
    sidoOutlineLayer = L.geoJSON(sidoData, { style: sidoOutlineStyle, interactive: false });
  }

  // 레이어 swap
  if (sigungu) {
    if (leafletMap.hasLayer(sidoLayer)) leafletMap.removeLayer(sidoLayer);
    if (!leafletMap.hasLayer(sigunguLayer)) sigunguLayer.addTo(leafletMap);
    sigunguLayer.setStyle((f) => sigunguStyle(f));
    sigunguLayer.eachLayer(updateSigunguTooltip);
    if (!leafletMap.hasLayer(sidoOutlineLayer)) sidoOutlineLayer.addTo(leafletMap);
    sidoOutlineLayer.bringToFront();
  } else {
    if (leafletMap.hasLayer(sigunguLayer)) leafletMap.removeLayer(sigunguLayer);
    if (leafletMap.hasLayer(sidoOutlineLayer)) leafletMap.removeLayer(sidoOutlineLayer);
    if (!leafletMap.hasLayer(sidoLayer)) sidoLayer.addTo(leafletMap);
    sidoLayer.setStyle((f) => sidoStyle(f));
    sidoLayer.eachLayer(updateSidoTooltip);
  }

  setTimeout(() => leafletMap.invalidateSize(), 50);
}

function attachSidoClick(feat, layer) {
  const sido = canonSido((feat.properties.name || '').trim());
  layer.on('click', () => {
    state.selectedSido = sido;
    state.selectedSigungu = null;
    renderMap();
    renderDetail();
  });
}

function attachSigunguClick(feat, layer) {
  const code = feat.properties.code || '';
  const sido = sigunguSidoFromCode(code);
  const name = feat.properties.name || '';
  layer.on('click', () => {
    state.selectedSido = sido;
    state.selectedSigungu = name;
    renderMap();
    renderDetail();
  });
}

function updateSidoTooltip(layer) {
  const sido = canonSido((layer.feature.properties.name || '').trim());
  const result = sidoLastWinningParty(sido, state.office);
  const lbl = result ? (result.name || result.party || '') : '';
  const tip = result
    ? `<b>${sido}</b><br>${lbl}${result.name && result.party ? ' (' + result.party + ')' : ''} ${result.pct}%<br>${fmtDate(result.period)} 조사`
    : `<b>${sido}</b><br>조사 없음`;
  layer.bindTooltip(tip, { className: 'sigungu-tooltip', sticky: true });
}

function updateSigunguTooltip(layer) {
  const code = layer.feature.properties.code || '';
  const sido = sigunguSidoFromCode(code);
  const name = layer.feature.properties.name || '';
  const result = sigunguLastWinningParty(sido, name, state.office);
  const tip = result
    ? `<b>${sido} ${name}</b><br>${result.name} (${result.party}) ${result.pct}%<br>${fmtDate(result.period)} 조사`
    : `<b>${sido} ${name}</b><br>조사 없음`;
  layer.bindTooltip(tip, { className: 'sigungu-tooltip', sticky: true });
}

function sidoStyle(feat) {
  const sido = canonSido((feat.properties.name || '').trim());
  const result = sidoLastWinningParty(sido, state.office);
  const sel = state.selectedSido === sido && !state.selectedSigungu;
  return {
    fillColor: result ? partyColor(result.party) : '#d8dce4',
    fillOpacity: result ? gapOpacity(result.gap) : 0.55,
    color: sel ? '#0a0e1a' : '#2a2f3c',
    weight: sel ? 2.5 : 1.4,
    opacity: sel ? 1 : 0.7,
  };
}

function sigunguStyle(feat) {
  const code = feat.properties.code || '';
  const sido = sigunguSidoFromCode(code);
  const name = feat.properties.name || '';
  const result = sigunguLastWinningParty(sido, name, state.office);
  const selected = state.selectedSido === sido && state.selectedSigungu === name;
  return {
    fillColor: result ? partyColor(result.party) : '#d8dce4',
    fillOpacity: result ? gapOpacity(result.gap) : 0.55,
    color: selected ? '#0a0e1a' : '#7a8090',
    weight: selected ? 2.5 : 0.6,
  };
}

// 시도 외곽선 전용 스타일 (시군구 모드에서 위에 오버레이) — fill 없이 굵은 line
function sidoOutlineStyle() {
  return { fill: false, color: '#3a4050', weight: 1.6, opacity: 0.55, interactive: false };
}

// === 디테일 패널 ===

function renderDetail() {
  const pane = $('#detail-pane');
  if (!state.selectedSido) {
    pane.innerHTML =
      '<div class="detail-empty">시도·시군구를 선택하면 그 지역의 모든 여론조사가 여기에 표시됩니다.</div>';
    return;
  }
  const polls = pollsByRegion(state.selectedSido, state.selectedSigungu);
  const officePolls = polls.filter((p) => p.office_level === state.office);

  const titleParts = [state.selectedSido];
  if (state.selectedSigungu) titleParts.push(state.selectedSigungu);

  let html = `<div class="detail-hdr">
    <h2>${titleParts.join(' · ')}</h2>
    <span class="count">${state.office} · ${officePolls.length}건</span>
  </div>`;
  if (!officePolls.length) {
    html += `<div class="detail-empty">${state.office} 관련 조사가 아직 없습니다.</div>`;
    pane.innerHTML = html;
    return;
  }

  // 시계열 산점도 SVG (조사 ≥ 2건일 때만)
  if (officePolls.length >= 2) {
    html += `<div class="scatter-wrap">${buildScatterSVG(officePolls)}</div>`;
  }
  // 첫 카드 위 라벨
  const latest = officePolls[0];
  if (latest) {
    html += `<div class="latest-label">조사 ${officePolls.length}건 · 최신 ${formatPeriod(latest.period_start, latest.period_end)}</div>`;
  }
  for (const p of officePolls) {
    html += renderPollCard(p, p.office_label);  // renderPollCard → utils.js (공용)
  }
  pane.innerHTML = html;
}

// === 토글 ===

// view는 'map' 또는 'hex' 두 가지. office에 따라 자동 분기:
//   기초단체장 + map → 시군구 chloropleth
//   기초단체장 + hex → 시군구 hex (#hex2)
//   광역/교육감/정당지지/국정평가/투표의향 + map → 시도 chloropleth (기본)
//   다만 위 메트릭들도 시군구 데이터 있으면 scope='시군구'로 강제 가능 (state.scope)
function isSigunguMode() {
  if (state.office === '기초단체장') return true;
  if (state.scope === '시군구') return true;
  return false;
}

// 현재 office에 시군구 데이터가 있는지
function hasSigunguData() {
  return state.data.polls.some((p) => p.office_level === state.office && p.sigungu);
}

function setView(v) {
  state.view = v;
  const sigungu = isSigunguMode();
  $('#map').toggleAttribute('hidden', v !== 'map');
  $('#hex').toggleAttribute('hidden', !(v === 'hex' && !sigungu));
  $('#hex2').toggleAttribute('hidden', !(v === 'hex' && sigungu));
  document.querySelectorAll('[data-view]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.view === v);
  });
  if (v === 'map') renderMap();
  else if (sigungu) renderSigunguHex();
  else renderHex();
  renderLegend();
}

// 색 범례 — 현재 office의 지도/격자에 실제 등장하는 정당(또는 메트릭 카테고리).
function legendData() {
  const o = state.office;
  if (o === '국정평가') {
    return [['긍정 평가', '긍정평가'], ['부정 평가', '부정평가'], ['모름·무응답', '모름/무응답']]
      .map(([label, k]) => ({ label, color: METRIC_COLORS[k] }));
  }
  if (o === '투표의향') {
    return [['투표 의향', '투표함'], ['의향 없음', '투표안함'], ['모름·무응답', '모름/무응답']]
      .map(([label, k]) => ({ label, color: METRIC_COLORS[k] }));
  }
  // 정당 기반 office (광역·기초·교육감·정당지지) — 지역별 1위 정당 수집
  const sg = isSigunguMode();
  const polls = state.data.polls.filter(
    (p) => p.office_level === o && !p.is_self_poll && (sg ? p.sigungu : !p.sigungu));
  const groups = {};
  for (const p of polls) {
    const k = sg ? `${p.sido}|${p.sigungu}` : p.sido;
    (groups[k] = groups[k] || []).push(p);
  }
  // 정당명 변형 정규화 (민주당→더불어민주당 등). 색은 partyColor가 이미 동일.
  const CANON = { '민주당': '더불어민주당', '국힘': '국민의힘', '국민의 힘': '국민의힘' };
  const parties = new Set();
  for (const k in groups) {
    const t = summarizeLatest(groups[k]);
    if (t) parties.add(CANON[t.party] || t.party || '무소속');  // 빈 정당·무소속 합침
  }
  const ORDER = ['더불어민주당', '국민의힘', '조국혁신당', '개혁신당', '진보당', '새로운미래', '무소속'];
  const sorted = [...parties].sort((a, b) => {
    const ia = ORDER.indexOf(a), ib = ORDER.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  return sorted.map((raw) => ({ label: raw, color: partyColor(raw) }));
}

function renderLegend() {
  const el = $('#poll-legend');
  if (!el) return;
  const items = legendData();
  el.innerHTML = items.map((it) =>
    `<span class="leg-item"><span class="leg-dot" style="background:${it.color}"></span>${it.label}</span>`
  ).join('') + '<span class="leg-item"><span class="leg-dot" style="background:#e6e9ef"></span>조사 없음</span>';
}

let sigunguHexData = null;
async function loadSigunguHex() {
  if (sigunguHexData) return sigunguHexData;
  try {
    const r = await fetch('data/geo/sigungu_hex.json');
    sigunguHexData = await r.json();
  } catch (e) {
    sigunguHexData = [];
  }
  return sigunguHexData;
}

async function renderSigunguHex() {
  const svg = $('#hex2');
  const data = await loadSigunguHex();
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  if (!data.length) return;
  const cs = data.map((d) => d.c);
  const rs = data.map((d) => d.r);
  const minC = Math.min(...cs);
  const minR = Math.min(...rs);
  const maxC = Math.max(...cs);
  const maxR = Math.max(...rs);
  const r = 22; // hex radius — 라벨 공간 확보
  const colW = r * Math.sqrt(3);
  const rowH = r * 1.5;
  // SVG viewBox 자동 맞춤
  const w = (maxC - minC + 2) * colW;
  const h = (maxR - minR + 2) * rowH;
  svg.setAttribute('viewBox', `0 0 ${Math.ceil(w)} ${Math.ceil(h)}`);
  const offX = -minC * colW + colW / 2;
  const offY = -minR * rowH + rowH;

  // 시군구별 마지막 기초단체장 조사 1위
  for (const d of data) {
    const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
    const result =
      isSigunguMode()
        ? sigunguLastWinningParty(d.sido, d.name, state.office)
        : sidoLastWinningParty(d.sido, state.office);
    const fill = result ? partyColor(result.party) : '#e6e9ef';
    const cls = result ? 'hex-cell has-data' : 'hex-cell no-data';
    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', cls + (state.selectedSido === d.sido && state.selectedSigungu === d.name ? ' is-selected' : ''));
    poly.setAttribute('points', hexPoints(cx, cy, r - 0.7));
    poly.setAttribute('fill', fill);
    poly.setAttribute('stroke', '#0a0e1a');
    poly.setAttribute('stroke-width', '0.7');
    poly.setAttribute('fill-opacity', result ? gapOpacity(result.gap) : '1');
    poly.style.cursor = 'pointer';
    poly.addEventListener('click', () => {
      state.selectedSido = d.sido;
      state.selectedSigungu = state.office === '기초단체장' ? d.name : null;
      renderSigunguHex();
      renderDetail();
    });
    // 툴팁
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    const lbl = result ? (result.name || result.party || '') : '';
    title.textContent = result
      ? `${d.sido} ${d.name} · ${lbl}${result.name && result.party ? ' (' + result.party + ')' : ''} ${result.pct}% · ${fmtDate(result.period)}`
      : `${d.sido} ${d.name} · 조사 없음`;
    poly.appendChild(title);
    svg.appendChild(poly);

    // 라벨 — prefix 있으면 두 줄
    const label = shortSigunguLabel(d.name, d.sido);
    if (label.short) {
      const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      txt.setAttribute('x', cx);
      txt.setAttribute('text-anchor', 'middle');
      txt.setAttribute('font-weight', '600');
      txt.setAttribute('fill', result ? '#fff' : '#0a0e1a');
      txt.setAttribute('pointer-events', 'none');
      txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      if (label.prefix) {
        // 두 줄: prefix 위 (작게·옅게), short 아래
        const tp1 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        tp1.setAttribute('x', cx);
        tp1.setAttribute('y', cy - 2);
        tp1.setAttribute('font-size', '6');
        tp1.setAttribute('opacity', '0.75');
        tp1.textContent = label.prefix;
        txt.appendChild(tp1);
        const tp2 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        tp2.setAttribute('x', cx);
        tp2.setAttribute('y', cy + 8);
        tp2.setAttribute('font-size', label.short.length > 3 ? '7' : '9');
        tp2.textContent = label.short;
        txt.appendChild(tp2);
      } else {
        txt.setAttribute('y', cy + 3);
        txt.setAttribute('font-size', label.short.length > 3 ? '7' : '9');
        txt.textContent = label.short;
      }
      svg.appendChild(txt);
    }
  }

  // 시도 경계 굵은 선 + 한반도 외곽 — drawHexBorders (hexgrid.js)
  const cellAt = new Map();
  for (const d of data) cellAt.set(`${d.c},${d.r}`, d);
  drawHexBorders(svg, data, cellAt, colW, rowH, offX, offY, r, '1.6', true);
}

function setOffice(o) {
  state.office = o;
  document.querySelectorAll('[data-office]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.office === o);
  });
  // scope 토글 — 정당지지/국정평가/투표의향만 의미. 시도/시군구 데이터 둘 다 있는 경우 노출.
  const scopeSeg = $('#scope-seg');
  const showScope = ['정당지지', '국정평가', '투표의향'].includes(o) && hasSigunguData();
  scopeSeg.toggleAttribute('hidden', !showScope);
  if (!showScope) state.scope = '시도';  // reset
  setView(state.view);
  renderDetail();
  recalcSegFades();  // scope seg 노출 변화 → 페이드 재계산
}

function setScope(s) {
  state.scope = s;
  document.querySelectorAll('[data-scope]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.scope === s);
  });
  setView(state.view);
  renderDetail();
}

// === 초기화 ===

// 가로 스크롤되는 컨트롤(.seg)에 "더 있다" 페이드 — 끝에 닿으면 해제.
let recalcSegFades = () => {};
function setupSegFades() {
  const segs = [...document.querySelectorAll('.controls .seg')];
  const update = (el) => {
    const more = el.scrollWidth - el.clientWidth;
    if (more <= 1) { el.classList.remove('fade-left', 'fade-right'); return; }
    el.classList.toggle('fade-left', el.scrollLeft > 1);
    el.classList.toggle('fade-right', el.scrollLeft < more - 1);
  };
  segs.forEach((el) => {
    update(el);
    el.addEventListener('scroll', () => update(el), { passive: true });
  });
  recalcSegFades = () => segs.forEach(update);
  window.addEventListener('resize', recalcSegFades, { passive: true });
}

async function init() {
  setCountdown();
  setInterval(setCountdown, 60_000);
  await loadData();
  document.querySelectorAll('[data-view]').forEach((b) => {
    b.addEventListener('click', () => setView(b.dataset.view));
  });
  document.querySelectorAll('[data-office]').forEach((b) => {
    b.addEventListener('click', () => setOffice(b.dataset.office));
  });
  document.querySelectorAll('[data-scope]').forEach((b) => {
    b.addEventListener('click', () => setScope(b.dataset.scope));
  });
  setupSegFades();
  // 정적 prerender가 주입한 초기 상태 (URL 기반)
  const init0 = (typeof window !== 'undefined' && window.__INITIAL_STATE__) || {};
  if (init0.office) setOffice(init0.office);
  setView(init0.view || state.view);  // 기본 hex (prerender가 view 주입 시 그것)
}

init();
