// 2026 국회의원 재·보궐선거 여론조사 — vote.ysw.kr/byelection
// 데이터: data/polls/byelection.json (build_byelection.py). 의존: parties.js, utils.js, Leaflet.

const BLACKOUT_START = new Date('2026-05-28T00:00:00+09:00');
const BLACKOUT_END = new Date('2026-06-03T18:00:00+09:00');

const state = { data: null, selected: null, map: null, markers: {} };
const $ = (s) => document.querySelector(s);

async function init() {
  let geo = null;
  try {
    const [bj, gj] = await Promise.all([
      fetch('data/polls/byelection.json').then((r) => r.json()),
      fetch('data/geo/sido_simple.json').then((r) => r.json()).catch(() => null),
    ]);
    state.data = bj;
    geo = gj;
  } catch (e) {
    state.data = { districts: [] };
  }
  const now = new Date();
  if (now >= BLACKOUT_START && now < BLACKOUT_END) {
    for (const d of state.data.districts) {
      d.polls = d.polls.filter((p) => p.period_end && p.period_end < '2026-05-28');
    }
    state.data.districts = state.data.districts.filter((d) => d.polls.length);
  }
  // 기본 선택 = 첫 선거구
  if (state.data.districts.length) state.selected = state.data.districts[0].district;
  $('#loading').hidden = true;
  renderMap(geo);
  renderChips();
  renderCards();
}

function latestTop(d) {
  if (!d.polls.length) return null;
  const latest = d.polls[0];
  if (!latest.candidates.length) return null;
  const top = latest.candidates.reduce((a, b) => (a.pct >= b.pct ? a : b));
  const sec = latest.candidates.filter((c) => c !== top).sort((a, b) => b.pct - a.pct)[0];
  return { ...top, gap: sec ? top.pct - sec.pct : null, period: latest.period_end };
}

function cssId(s) { return s.replace(/\s/g, '-'); }

// 한국 경계 — index 지도와 동일. 밖으로 패닝 잠금.
const KOREA_BOUNDS = [[32.5, 123.5], [39.5, 132.5]];

function renderMap(geo) {
  const map = L.map('boe-map', {
    zoomControl: true, attributionControl: false, maxZoom: 11,
    maxBounds: KOREA_BOUNDS, maxBoundsViscosity: 1.0,
  }).setView([36.3, 127.8], 7);
  state.map = map;
  // 베이스맵 — 시도 GeoJSON 외곽 (타일 없이 한국 모양)
  if (geo) {
    L.geoJSON(geo, {
      style: { fillColor: '#e6e9ef', fillOpacity: 0.7, color: '#b8bfce', weight: 0.8 },
      interactive: false,
    }).addTo(map);
  }
  const pts = [];
  for (const d of state.data.districts) {
    if (!d.latlng) continue;
    pts.push(d.latlng);
    const top = latestTop(d);
    const color = top ? partyColor(top.party) : '#888';
    const marker = L.circleMarker(d.latlng, {
      radius: 8 + Math.min(d.n_polls, 8),
      fillColor: color, fillOpacity: top ? Math.max(0.6, gapOpacity(top.gap)) : 0.6,
      color: '#0a0e1a', weight: 1.6,
    }).addTo(map);
    // 상시 라벨 — hover 없이 선거구명 바로 보이게
    marker.bindTooltip(d.district, {
      permanent: true, direction: 'right', offset: [6, 0],
      className: 'boe-label', opacity: 1,
    });
    marker.on('click', () => selectDistrict(d.district));
    state.markers[d.district] = marker;
  }
  // 7개 마커가 한 화면에 다 보이게 (제주 서귀포 남단까지 포함). 라벨 잘림 방지로 우측 여백 큼.
  if (pts.length) {
    map.fitBounds(L.latLngBounds(pts), { paddingTopLeft: [30, 30], paddingBottomRight: [120, 30] });
    // 초기 뷰보다 더 축소 못 하게 (회색 허공 방지) — index 지도와 동일 정책.
    map.once('moveend', () => map.setMinZoom(map.getZoom()));
  }
}

function selectDistrict(name) {
  state.selected = name;
  renderChips();
  renderCards();
  const m = state.markers[name];
  if (m && state.map) state.map.panTo(m.getLatLng());
}

// 선거구 칩 (지도 위 필터)
function renderChips() {
  const wrap = $('#boe-chips');
  wrap.innerHTML = '';
  for (const d of state.data.districts) {
    const top = latestTop(d);
    const btn = document.createElement('button');
    btn.className = 'seg-btn boe-chip' + (state.selected === d.district ? ' is-active' : '');
    btn.style.borderLeft = `4px solid ${top ? partyColor(top.party) : '#888'}`;
    btn.textContent = `${d.district} · ${d.n_polls}`;
    btn.addEventListener('click', () => selectDistrict(d.district));
    wrap.appendChild(btn);
  }
}

function renderCards() {
  const pane = $('#cards-pane');
  const d = state.data.districts.find((x) => x.district === state.selected);
  if (!d) {
    pane.innerHTML = '<div class="detail-empty">선거구를 선택하면 여론조사가 표시됩니다.</div>';
    return;
  }
  const top = latestTop(d);
  let html = `<div class="detail-hdr">
    <h2>${d.district}</h2>
    <span class="count">국회의원 재·보궐 · ${d.n_polls}건</span>
  </div>`;
  if (top) {
    html += `<div class="latest-label">최신 ${fmtDate(top.period)} · 1위 <b style="color:${partyTextColor(top.party)}">${top.name}</b> (${top.party}) ${top.pct}%</div>`;
  }
  for (const p of d.polls) {
    html += renderPollCard(p, '국회의원');  // renderPollCard → utils.js (공용)
  }
  pane.innerHTML = html;
}

init();
