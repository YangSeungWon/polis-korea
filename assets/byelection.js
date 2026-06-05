// 2026 국회의원 재·보궐선거 여론조사 — polis.ysw.kr/byelection
// 데이터: data/polls/byelection.json (build_byelection.py). 의존: parties.js, utils.js, Leaflet.

const BLACKOUT_START = new Date('2026-05-28T00:00:00+09:00');
const BLACKOUT_END = new Date('2026-06-03T18:00:00+09:00');

const state = { data: null, selected: null, map: null, markers: {} };
const $ = (s) => document.querySelector(s);

// district 첫 토큰("부산", "경기") → roster key용 정식 시도명
const SIDO_FROM_SHORT = {
  '서울': '서울특별시', '부산': '부산광역시', '대구': '대구광역시', '인천': '인천광역시',
  '광주': '광주광역시', '대전': '대전광역시', '울산': '울산광역시', '세종': '세종특별자치시',
  '경기': '경기도', '강원': '강원특별자치도', '충북': '충청북도', '충남': '충청남도',
  '전북': '전북특별자치도', '전남': '전라남도', '경북': '경상북도', '경남': '경상남도',
  '제주': '제주특별자치도',
};
const SIDO_TO_SHORT = Object.fromEntries(Object.entries(SIDO_FROM_SHORT).map(([k, v]) => [v, k]));

// 여론조사 없이 결과만 있는 선거구 좌표 (centroid 근사 — index 지도 패턴과 동일).
// chip/map에 합쳐서 표시. 새 회차마다 NEC 결과 비교해 갱신.
const RESULT_ONLY_LATLNG = {
  '인천 계양구을': [37.537, 126.738],
  '광주 광산구을': [35.135, 126.793],
  '울산 남구갑':   [35.544, 129.330],
  '경기 안산시갑': [37.300, 126.840],
  '충남 아산시을': [36.790, 127.002],
  '전북 군산김제부안을': [35.700, 126.700],
};

async function init() {
  let geo = null;
  try {
    const [bj, gj, rj, results] = await Promise.all([
      fetch('data/polls/byelection.json').then((r) => r.json()),
      fetch('data/geo/sido_simple.json').then((r) => r.json()).catch(() => null),
      fetch('data/raw/nec_roster_9th.json').then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch('data/results/9th-byelection-2026.json').then((r) => r.ok ? r.json() : null).catch(() => null),
    ]);
    state.data = bj;
    geo = gj;
    state.roster = rj;
    state.results = results;
  } catch (e) {
    state.data = { districts: [] };
  }
  // 결과만 있고 여론조사 없던 선거구를 stub districts로 합치기 (n_polls=0).
  mergeResultOnlyDistricts();
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
  // 초기 marker 강조 (페이지 로드 시 자동 scroll은 X)
  if (state.selected) selectDistrict(state.selected, { scroll: false });
}

// 여론조사 없고 결과만 있는 선거구를 districts에 추가 (stub, n_polls=0).
function mergeResultOnlyDistricts() {
  if (!state.results?.races || !state.data?.districts) return;
  const norm = (s) => (s || '').replace(/[시군구]/g, '');
  const pollByKey = new Map();
  for (const d of state.data.districts) {
    const [shortSido, ...rest] = d.district.split(' ');
    const full = SIDO_FROM_SHORT[shortSido];
    if (full) pollByKey.set(`${full}|${norm(rest.join(' '))}`, d);
  }
  for (const r of state.results.races) {
    const key = `${r.sido}|${norm(r.district)}`;
    if (pollByKey.has(key)) continue;
    // 결과만 — stub district 생성
    const short = SIDO_TO_SHORT[r.sido] || r.sido;
    // 결과 district 이름 정규화 — '군산시김제시부안군을' 같은 풀네임을 약어로
    // 시/군 suffix만 제거 — 이름 첫 글자(군산·시흥 등)는 lookbehind로 보호.
    const shortName = r.district.replace(/(?<=[가-힣])[시군](?=[가-힣])/g, '');
    const lookupKey = `${short} ${shortName}`;
    const latlng = RESULT_ONLY_LATLNG[lookupKey] || RESULT_ONLY_LATLNG[`${short} ${r.district}`];
    if (!latlng) {
      console.warn('[byelection] 좌표 없음:', lookupKey);
      continue;
    }
    state.data.districts.push({
      district: lookupKey,
      latlng,
      polls: [],
      n_polls: 0,
    });
  }
}

// 폴 district("경기 평택시을") → results race 매칭. 시·군·구 suffix 무시한 fuzzy.
function matchResult(pollDist) {
  if (!state.results?.races) return null;
  const [shortSido, ...rest] = pollDist.split(' ');
  const fullSido = SIDO_FROM_SHORT[shortSido];
  if (!fullSido) return null;
  const pollDistrict = rest.join(' ');
  const norm = (s) => (s || '').replace(/[시군구]/g, '');
  for (const r of state.results.races) {
    if (r.sido !== fullSido) continue;
    if (r.district === pollDistrict || norm(r.district) === norm(pollDistrict)) {
      return r;
    }
  }
  return null;
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
    // 폴 없으면 결과 색으로 fallback (실제 1위 정당색).
    const result = matchResult(d.district);
    const resultTop = result ? result.candidates.slice().sort((a, b) => (b.votes||0) - (a.votes||0))[0] : null;
    const color = top ? partyColor(top.party) : (resultTop ? partyColor(resultTop.party) : '#888');
    const isPollless = d.n_polls === 0;
    const marker = L.circleMarker(d.latlng, {
      radius: isPollless ? 7 : (8 + Math.min(d.n_polls, 8)),
      fillColor: color,
      fillOpacity: isPollless ? 0.5 : (top ? Math.max(0.6, gapOpacity(top.gap)) : 0.6),
      color: '#0a0e1a', weight: isPollless ? 1.2 : 1.6,
      dashArray: isPollless ? '2,2' : null,
    }).addTo(map);
    marker._districtName = d.district;  // 선택 강조용
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

function selectDistrict(name, { scroll = true } = {}) {
  state.selected = name;
  renderChips();
  renderCards();
  // 선택된 marker 강조 (굵은 노란 outline + radius +3)
  for (const [n, m] of Object.entries(state.markers)) {
    const isSel = n === name;
    m.setStyle({
      color: isSel ? '#f5b800' : '#0a0e1a',
      weight: isSel ? 3.5 : 1.6,
    });
    const baseR = m.options.radius;
    if (isSel) m.bringToFront();
  }
  // 재보궐 지도는 7개 marker 다 보이는 fit 상태 — panTo·zoom 변경 불요
  // 모바일: 지도 클릭 후 조사 결과 영역으로 자동 scroll (데스크탑은 옆에 있어 무의미)
  if (scroll && window.matchMedia('(max-width: 768px)').matches) {
    const cards = document.getElementById('cards-pane');
    if (cards) {
      // pane top에서 60px 정도 위 (헤더·라벨 안 가리게)
      const top = cards.getBoundingClientRect().top + window.scrollY - 60;
      window.scrollTo({ top, behavior: 'smooth' });
    }
  }
}

// 선거구 칩 (지도 위 필터)
function renderChips() {
  const wrap = $('#boe-chips');
  wrap.innerHTML = '';
  for (const d of state.data.districts) {
    const top = latestTop(d);
    const result = matchResult(d.district);
    const resultTop = result ? result.candidates.slice().sort((a, b) => (b.votes||0) - (a.votes||0))[0] : null;
    const color = top ? partyColor(top.party) : (resultTop ? partyColor(resultTop.party) : '#888');
    const isPollless = d.n_polls === 0;
    const btn = document.createElement('button');
    btn.className = 'seg-btn boe-chip' + (state.selected === d.district ? ' is-active' : '') + (isPollless ? ' is-pollless' : '');
    btn.style.borderLeft = `4px solid ${color}`;
    btn.textContent = isPollless ? `${d.district} · 결과만` : `${d.district} · ${d.n_polls}`;
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
  const result = matchResult(d.district);
  const countLabel = d.n_polls === 0 ? '국회의원 재·보궐 · 여론조사 미시행' : `국회의원 재·보궐 · 여론조사 ${d.n_polls}건`;
  let html = `<div class="detail-hdr">
    <h2>${d.district}</h2>
    <span class="count">${countLabel}</span>
  </div>`;
  // 실제 결과 (있으면) — 폴 위에 표시
  if (result?.candidates?.length) {
    const cs = result.candidates.slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
    const r1 = cs[0], r2 = cs[1];
    const margin = r2 ? (r1.pct - r2.pct) : null;
    const electors = result.electors || 0, voted = result.voters || 0;
    const turnout = electors ? (voted / electors * 100) : 0;
    const c1 = partyColor(r1.party);
    const hit = top && top.party === r1.party ? '여론조사 적중 ✓' : (top ? '여론조사 빗나감 ✗' : '');
    html += `<div class="boe-result">
      <div class="boe-result-hdr">
        <span class="boe-result-tag">실제 결과</span>
        <span class="boe-result-meta">투표율 ${turnout.toFixed(1)}% · ${hit}</span>
      </div>
      <div class="boe-result-row">
        <span class="boe-rank">1위</span>
        <span class="boe-name" style="color:${c1};font-weight:700">${r1.name}</span>
        <span class="boe-party" style="color:${c1}">${r1.party}</span>
        <span class="boe-pct">${(r1.pct || 0).toFixed(2)}%</span>
      </div>
      ${r2 ? `<div class="boe-result-row">
        <span class="boe-rank">2위</span>
        <span class="boe-name">${r2.name}</span>
        <span class="boe-party" style="color:${partyColor(r2.party)}">${r2.party}</span>
        <span class="boe-pct">${(r2.pct || 0).toFixed(2)}%</span>
      </div>` : ''}
      ${margin != null ? `<div class="boe-result-margin">격차 ${margin.toFixed(2)}pp</div>` : ''}
    </div>`;
  }
  if (top) {
    html += `<div class="latest-label">최신 ${fmtDate(top.period)} · 1위 <b style="color:${partyTextColor(top.party)}">${top.name}</b> (${top.party}) ${top.pct}%</div>`;
  }
  // 산점도 — 조사 2건 이상이면 시계열 시각화 (메인 폴과 동일)
  // roster 룩업은 "sido|name" 키. byelection.json poll엔 sido 없으니 district 첫 토큰에서 주입.
  if (d.polls.length >= 2) {
    const sido = SIDO_FROM_SHORT[(d.district || '').split(' ')[0]] || '';
    const pollsWithSido = d.polls.map((p) => ({ ...p, sido }));
    html += `<div class="scatter-wrap">${buildScatterSVG(pollsWithSido, state.roster || null)}</div>`;
  }
  for (const p of d.polls) {
    html += renderPollCard(p, '국회의원');  // renderPollCard → utils.js (공용)
  }
  pane.innerHTML = html;
}

init();
