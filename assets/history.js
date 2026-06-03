// 역대 선거 결과 페이지 — vote.ysw.kr/history
// 데이터: data/elections.json (회차 목록), data/results/{type}_{n}.json (결과)
// 의존: regions.js, parties.js (SIDO_HEX_LAYOUT 포함), utils.js

const TYPE_LABEL = {
  presidential:      { ko: '대통령선거', short: '대선' },
  national_assembly: { ko: '국회의원선거', short: '총선' },
  local:             { ko: '지방선거',     short: '지선' },
};

// 데이터 단위에 따라 자동으로 시도/시군구/지역구 hex 선택
function activeUnit(type, office, results) {
  if (type === 'local') {
    return office === '기초단체장' ? 'sigungu' : 'sido';
  }
  // 총선: 지역구 데이터 있으면 지역구 hex 우선
  if (type === 'national_assembly' && results?.district?.length) {
    return 'district';
  }
  // 21대 총선처럼 broadcast 데이터는 시도만 의미
  if (results?._meta?.granularity === 'sido_broadcast') return 'sido';
  return 'sigungu';
}

const state = {
  type: 'presidential',
  n: null,
  office: '기초단체장',
  sizing: '격자',
  display: 'hex',  // hex | geo — 22대 총선에 한해 실제 지리 polygon 지도 view 가능 (OhmyNews GeoJSON)
  elections: null,
  hexData: null,            // sigungu_hex.json (9회 기준 통합도시)
  hexLegacy: null,          // sigungu_hex_legacy.json (옛 회차 — 일반구 분할)
  districtHex: {},          // {22: [...]} 지역구별 hex layout
  results: null,
  selected: null,
  geoCache: {},       // {21: geo, 22: geo} GeoJSON
  geoMapCache: {},    // {21: map, 22: map} sido|name → SGG_Code
  geoSido: null,      // 시도 경계 overlay 데이터
};

const $ = (s) => document.querySelector(s);

// CSS variable resolver — SVG에 inline 색 부여할 때 라이트·다크 자동
function themeVar(name, fallback) {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  } catch (e) { return fallback; }
}
function inkAlpha(a) {
  // --ink가 light면 어둠, dark면 밝음 — alpha rgba 직접 만들기 어려워서 currentColor 활용 또는 hex+a hack
  // 단순화: themeVar('--ink') 색에 opacity는 별도 attr로
  return themeVar('--ink', '#0a0e1a');
}

async function loadJson(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

// === 새 schema (data/results/{id}.json) → 옛 format adapter ===
// 새 schema: { _meta, races: [{sg_typecode, sido, sigungu/district, scope, candidates, electors, voters, ...}] }
// 옛 format: { _meta, national/sigungu/district 또는 offices[level]={national, sigungu} }

function _ordinal(n) {
  if (n >= 11 && n <= 13) return `${n}th`;
  const last = n % 10;
  return `${n}${last === 1 ? 'st' : last === 2 ? 'nd' : last === 3 ? 'rd' : 'th'}`;
}

function newSchemaPath(type, n) {
  const el = state.elections?.[type]?.elections?.find((x) => x.n === n);
  if (!el?.date) return null;
  const year = el.date.split('-')[0];
  const kind = { presidential: 'pres', national_assembly: 'general', local: 'local' }[type];
  if (!kind) return null;
  return `data/results/${_ordinal(n)}-${kind}-${year}.json`;
}

function _raceToOldRow(race) {
  return {
    sido: race.sido,
    name: race.sigungu || '',
    electors: race.electors || 0,
    voted: race.voters || 0,
    turnout: race.electors ? +(race.voters / race.electors * 100).toFixed(2) : 0,
    invalid: race.invalid_votes || 0,
    candidates: race.candidates || [],
  };
}

function _raceToOldDistrict(race) {
  const winner = race.candidates?.[0];
  return {
    sido: race.sido,
    name: race.district || '',
    winner: winner?.name || '',
    winner_party: winner?.party || '',
    electors: race.electors || 0,
    voted: race.voters || 0,
    invalid: race.invalid_votes || 0,
    turnout: race.electors ? +(race.voters / race.electors * 100).toFixed(2) : 0,
    candidates: race.candidates || [],
  };
}

function _raceToOldNation(race) {
  return {
    electors: race.electors || 0,
    voted: race.voters || 0,
    invalid: race.invalid_votes || 0,
    turnout: race.electors ? +(race.voters / race.electors * 100).toFixed(2) : 0,
    candidates: race.candidates || [],
  };
}

// 시도 race들 합산 → nation fallback (nation race 없을 때만)
function _aggSidoToNation(sidoRaces) {
  const electors = sidoRaces.reduce((s, r) => s + (r.electors || 0), 0);
  const voted = sidoRaces.reduce((s, r) => s + (r.voters || 0), 0);
  const candMap = new Map();
  for (const r of sidoRaces) {
    for (const c of r.candidates || []) {
      const k = `${c.party}|${c.name}`;
      const prev = candMap.get(k) || { name: c.name, party: c.party, votes: 0 };
      prev.votes += c.votes || 0;
      candMap.set(k, prev);
    }
  }
  const total = [...candMap.values()].reduce((s, c) => s + c.votes, 0);
  return {
    electors, voted,
    turnout: electors ? +(voted / electors * 100).toFixed(2) : 0,
    candidates: [...candMap.values()]
      .map((c) => ({ ...c, pct: total ? +(c.votes / total * 100).toFixed(2) : 0 }))
      .sort((a, b) => b.votes - a.votes),
  };
}

function adaptNewSchema(raw, type) {
  const out = { _meta: raw._meta };
  const races = raw.races || [];
  if (type === 'presidential') {
    const nation = races.find((r) => r.scope === 'nation' && r.sg_typecode === '1');
    const sidoRaces = races.filter((r) => r.scope === 'sido' && r.sg_typecode === '1');
    out.national = nation ? _raceToOldNation(nation) : _aggSidoToNation(sidoRaces);
    out.sigungu = races.filter((r) => r.scope === 'sigungu' && r.sg_typecode === '1')
                       .map(_raceToOldRow);
  } else if (type === 'national_assembly') {
    // 옛 schema의 national은 비례 전국 합계
    const nation = races.find((r) => r.scope === 'nation' && r.sg_typecode === '7');
    const sidoProp = races.filter((r) => r.scope === 'sido' && r.sg_typecode === '7');
    out.national = nation ? _raceToOldNation(nation) : _aggSidoToNation(sidoProp);
    // 비례 의석 — _meta.proportional_seats (NEC API fetch 결과를 새 schema에 백필)
    if (raw._meta?.proportional_seats) {
      out.national.proportional_seats = raw._meta.proportional_seats;
    }
    out.district = races.filter((r) => r.scope === 'district' && r.sg_typecode === '2')
                        .map(_raceToOldDistrict);
    // 시군구는 비례 시군구별 (총선 시군구 hex 대안)
    out.sigungu = races.filter((r) => r.scope === 'sigungu' && r.sg_typecode === '7')
                       .map(_raceToOldRow);
  } else if (type === 'local') {
    out.offices = {};
    const officeTc = { '광역단체장': '3', '기초단체장': '4', '교육감': '11' };
    for (const [office, tc] of Object.entries(officeTc)) {
      const sidoRaces = races.filter((r) => r.scope === 'sido' && r.sg_typecode === tc);
      out.offices[office] = {
        national: _aggSidoToNation(sidoRaces),
        sigungu: races.filter((r) => r.scope === 'sigungu' && r.sg_typecode === tc)
                      .map(_raceToOldRow),
      };
    }
  }
  return out;
}

async function init() {
  const [elections, hex, hexLegacy, manifest] = await Promise.all([
    loadJson('data/elections.json'),
    loadJson('data/geo/sigungu_hex.json'),
    loadJson('data/geo/sigungu_hex_legacy.json').catch(() => null),
    loadJson('data/results/manifest.json').catch(() => ({ presidential: [], national_assembly: [], local: [] })),
  ]);
  state.elections = elections;
  state.elections._available = manifest;
  state.hexData = hex;
  state.hexLegacy = hexLegacy;

  document.querySelectorAll('[data-type]').forEach((b) => {
    b.addEventListener('click', () => setType(b.dataset.type));
  });
  document.querySelectorAll('[data-office]').forEach((b) => {
    b.addEventListener('click', () => setOffice(b.dataset.office));
  });
  document.querySelectorAll('[data-sizing]').forEach((b) => {
    b.addEventListener('click', () => setSizing(b.dataset.sizing));
  });
  document.querySelectorAll('[data-display]').forEach((b) => {
    b.addEventListener('click', () => setDisplay(b.dataset.display));
  });

  // 초기 상태 — path 우선 (prerender path 호환), 쿼리스트링·INITIAL_STATE fallback
  // path: /history/presidential/16/ or /history/local/8/governor/
  const init0 = parseInitialState();
  const type0 = init0.type || 'presidential';
  setType(type0, /*skipDefaultRound=*/ init0.n != null);
  if (init0.office && init0.office !== state.office) setOffice(init0.office);
  // URL ?sizing= 가 있으면 type 기본을 override (setType이 이미 type 기본 적용)
  if (init0.sizing && init0.sizing !== state.sizing) setSizing(init0.sizing);
  if (init0.n != null) setRound(init0.n);

  // popstate (브라우저 뒤·앞) — path 우선
  window.addEventListener('popstate', () => {
    const s = parseInitialState();
    if (s.type && s.type !== state.type) setType(s.type, s.n != null);
    if (s.office && s.office !== state.office) setOffice(s.office);
    if (s.n != null && s.n !== state.n) setRound(s.n);
  });

  $('#loading').hidden = true;
}

// URL ↔ state — path-based (prerender 호환, SEO 최적)
//   대선:   /history/presidential/{n}/
//   총선:   /history/national-assembly/{n}/
//   지선:   /history/local/{n}/{governor|mayor|superintendent}/
const TYPE_TO_SLUG = { presidential: 'presidential', national_assembly: 'national-assembly', local: 'local' };
const SLUG_TO_TYPE = { presidential: 'presidential', 'national-assembly': 'national_assembly', local: 'local' };
const OFFICE_TO_SLUG = { '광역단체장': 'governor', '기초단체장': 'mayor', '교육감': 'superintendent' };
const SLUG_TO_OFFICE = { governor: '광역단체장', mayor: '기초단체장', superintendent: '교육감' };

function parseInitialState() {
  // path: /history/presidential/16/ or /history/local/8/governor/
  const path = location.pathname.replace(/^\/+|\/+$/g, '').split('/');
  const params = new URLSearchParams(location.search);
  const init = (typeof window !== 'undefined' && window.__INITIAL_STATE__) || {};
  let type, n, office;
  if (path[0] === 'history' && path[1]) {
    type = SLUG_TO_TYPE[path[1]];
    if (path[2]) n = +path[2];
    if (type === 'local' && path[3]) office = SLUG_TO_OFFICE[path[3]];
  }
  // 쿼리스트링·INITIAL_STATE fallback
  return {
    type: type || params.get('type') || init.type,
    n: n != null ? n : (params.get('n') ? +params.get('n') : init.n),
    office: office || params.get('office') || init.office,
    sizing: params.get('sizing') || init.sizing,
  };
}

function buildPath() {
  const tSlug = TYPE_TO_SLUG[state.type];
  if (!tSlug || state.n == null) return '/history.html';
  let path = `/history/${tSlug}/${state.n}/`;
  if (state.type === 'local' && state.office) {
    const oSlug = OFFICE_TO_SLUG[state.office];
    if (oSlug) path += `${oSlug}/`;
  }
  return path;
}

function updateURL() {
  const newPath = buildPath();
  const params = new URLSearchParams();
  if (state.sizing && state.sizing !== typeDefaultSizing(state.type)) params.set('sizing', state.sizing);
  const q = params.toString();
  const newUrl = q ? `${newPath}?${q}` : newPath;
  if (newUrl !== location.pathname + location.search) {
    history.replaceState(null, '', newUrl);
  }
}

// 대선만 격자 hex 기본 (전국 표심을 면적으로 공평하게). 총선·지선은 동일.
function typeDefaultSizing(type) {
  return type === 'presidential' ? '격자' : '동일';
}

function setType(type, skipDefaultRound = false) {
  const prevType = state.type;
  state.type = type;
  document.querySelectorAll('[data-type]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.type === type);
  });
  $('#offices-seg').hidden = type !== 'local';
  // office button visual을 state.office와 동기 — HTML default와 state.office가 어긋날 때 보정
  // (예: URL ↔ default mismatch, 캐시된 옛 HTML)
  document.querySelectorAll('[data-office]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.office === state.office);
  });
  // type 전환 시 sizing 기본 재적용 (같은 type 안에서는 사용자 선택 유지)
  if (prevType !== type) {
    const def = typeDefaultSizing(type);
    state.sizing = def;
    document.querySelectorAll('[data-sizing]').forEach((b) => {
      b.classList.toggle('is-active', b.dataset.sizing === def);
    });
  }
  renderRoundsSeg();
  updateURL();
  if (skipDefaultRound) return;
  const available = state.elections._available?.[type] || [];
  const list = state.elections[type]?.elections || [];
  let target;
  if (available.length) target = Math.max(...available);
  else if (list.length) target = list[list.length - 1].n;
  if (target != null) setRound(target);
}

function setOffice(office) {
  state.office = office;
  document.querySelectorAll('[data-office]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.office === office);
  });
  updateURL();
  renderAll();
}

function setSizing(s) {
  state.sizing = s;
  document.querySelectorAll('[data-sizing]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.sizing === s);
  });
  updateURL();
  renderAll();
}

function setDisplay(d) {
  state.display = d;
  document.querySelectorAll('[data-display]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.display === d);
  });
  renderAll();
}

// 현재 결과에 등장한 1위 정당 모아 색 범례 — hex/지도 공통
function renderHistoryLegend() {
  const el = $('#history-legend');
  if (!el) return;
  const type = state.type;
  // 총선은 범례 안 보임 (지역구 색 자체로 충분)
  if (type === 'national_assembly') {
    el.hidden = true; el.innerHTML = '';
    return;
  }
  // 대선은 detail-pane(우측 그래프) 아래로 이동, 그 외는 viz 안 기본 위치
  const detailPane = $('#detail-pane');
  const vizParent = detailPane?.parentElement;
  if (type === 'presidential' && detailPane && el.parentElement !== detailPane) {
    detailPane.appendChild(el);
  } else if (type !== 'presidential' && vizParent && el.parentElement !== vizParent) {
    vizParent.insertBefore(el, detailPane);
  }
  const parties = new Set();
  if (type === 'presidential') {
    // 시군구별 1위 정당
    for (const r of (state.results?.sigungu || [])) {
      const w = (r.candidates || [])[0];
      if (w?.party) parties.add(w.party);
    }
  } else if (type === 'local') {
    // 광역단체장은 sido, 기초단체장은 sigungu
    const list = (state.results?.sido || []).concat(state.results?.sigungu || []);
    for (const r of list) {
      const w = (r.candidates || [])[0];
      if (w?.party) parties.add(w.party);
    }
  }
  if (!parties.size) {
    el.hidden = true; el.innerHTML = ''; return;
  }
  // 등장 순 정렬 (가나다순)
  const sorted = [...parties].sort((a, b) => a.localeCompare(b, 'ko'));
  el.hidden = false;
  el.innerHTML = sorted.map((p) =>
    `<span class="leg-item"><span class="leg-dot" style="background:${partyColor(p)}"></span>${p}</span>`
  ).join('') + '<span class="leg-item"><span class="leg-dot" style="background:#9aa3b3"></span>데이터 없음</span>';
}

// 현재 단위에 맞는 hex 렌더 + detail
async function renderAll() {
  const unit = activeUnit(state.type, state.office, state.results);
  // 21·22대 총선만 진짜 지도 view 지원 (OhmyNews GeoJSON, MIT)
  const geoSupported = state.type === 'national_assembly' && (state.n === 21 || state.n === 22);
  // 요소 누락(캐시된 옛 HTML 등)에도 깨지지 않게 null guard
  const toggle = (sel, hide) => { const el = $(sel); if (el) el.toggleAttribute('hidden', hide); };
  toggle('#display-seg', !geoSupported);
  const showGeo = geoSupported && state.display === 'geo';
  toggle('#hex', showGeo || unit !== 'sido');
  toggle('#hex2', showGeo || unit === 'sido');
  toggle('#geomap', !showGeo);
  // 사이즈 토글은 시군구 hex + 표심 분포 의미 있는 type만 (대선·옛 총선). 지선·geo 모드는 숨김.
  toggle('#sizing-seg', showGeo || unit !== 'sigungu' || state.type === 'local');
  if (showGeo) await renderGeoMap();
  else if (unit === 'sido') renderSidoHex();
  else if (unit === 'district') await renderDistrictHex();
  else renderSigunguHex();
  renderDetail();
  renderHistoryLegend();
}

async function loadDistrictHex(n) {
  if (state.districtHex[n]) return state.districtHex[n];
  try {
    state.districtHex[n] = await loadJson(`data/geo/district_hex_${n}.json`);
  } catch {
    state.districtHex[n] = null;
  }
  return state.districtHex[n];
}

function renderRoundsSeg() {
  const seg = $('#rounds-seg');
  seg.innerHTML = '';
  const list = state.elections[state.type]?.elections || [];
  const available = state.elections._available?.[state.type] || [];
  for (const e of list) {
    const btn = document.createElement('button');
    btn.className = 'seg-btn';
    if (!available.includes(e.n)) btn.classList.add('no-data');
    btn.dataset.n = e.n;
    btn.textContent = `${e.n}`;
    btn.title = `${e.date}${e.note ? ' · ' + e.note : ''}${available.includes(e.n) ? '' : ' · 데이터 미수집'}`;
    btn.addEventListener('click', () => setRound(e.n));
    seg.appendChild(btn);
  }
}

async function setRound(n) {
  state.n = n;
  state.selected = null;
  updateURL();
  document.querySelectorAll('#rounds-seg [data-n]').forEach((b) => {
    b.classList.toggle('is-active', +b.dataset.n === n);
  });
  const el = (state.elections[state.type]?.elections || []).find((x) => x.n === n);
  if (el) {
    $('#election-date').textContent = `${el.date}${el.note ? ' · ' + el.note : ''}`;
  }
  state.results = null;
  // 1차: 새 schema (통일 path) — data/results/{Nth}-{kind}-{year}.json
  const newPath = newSchemaPath(state.type, n);
  if (newPath) {
    try {
      const raw = await loadJson(newPath);
      state.results = adaptNewSchema(raw, state.type);
    } catch (e) {
      // 2차 fallback: 옛 path
      try {
        state.results = await loadJson(`data/results/${state.type}_${n}.json`);
      } catch {
        state.results = null;
      }
    }
  } else {
    try {
      state.results = await loadJson(`data/results/${state.type}_${n}.json`);
    } catch {
      state.results = null;
    }
  }
  renderAll();
}

// === 데이터 접근 ===

function activeOfficeData() {
  if (!state.results) return null;
  if (state.type === 'local') return state.results.offices?.[state.office] || null;
  return state.results;
}

// 시도 이동 시군구 — 현재 hex sido와 다른 옛 sido 데이터 fallback.
// 군위: 2023.7.1 경북 → 대구. 8회까지 경북 데이터.
const SIGUNGU_SIDO_HISTORY = {
  '군위군': ['대구광역시', '경상북도'],
};
// 행정구역 변경 — hex name → 데이터 name 후보들 (list).
const SIGUNGU_NAME_HISTORY = {
  '세종시':         ['세종특별자치시', '연기군'],  // 데이터 name 형식 차이 + 옛 충남 연기군
  '당진시':         ['당진군'],          // 2012 시 승격 전 (5회)
  '여주시':         ['여주군'],          // 2013 시 승격 전 (5회)
  '청주시청원구':   ['청원군'],          // 2014.7 통합 전 (5/6회)
  '미추홀구':       ['남구'],            // 인천 2018 개명 전 (5/6/7회 → '남구')
  '남구':           ['미추홀구'],        // 인천 — hex가 옛 vuski GeoJSON '남구', 8회+ 데이터엔 '미추홀구'
  // 인천 2026-07 신설 분구: 옛 회차에선 cell 자체 hide (SIGUNGU_HEX_HISTORY 참조).
};
// 1 hex ↔ N 데이터 합산 (분할구 → 통합 시 vote 합산).
// hex는 이제 통합도시 1 cell — 옛 역대 데이터(일반구 분할)는 합산해서 표시.
const SIGUNGU_MERGE = {
  '부천시': ['부천시원미구', '부천시소사구', '부천시오정구'],
  '수원시': ['수원시장안구', '수원시권선구', '수원시팔달구', '수원시영통구'],
  '용인시': ['용인시처인구', '용인시기흥구', '용인시수지구'],
  '고양시': ['고양시덕양구', '고양시일산동구', '고양시일산서구'],
  '성남시': ['성남시수정구', '성남시중원구', '성남시분당구'],
  '안양시': ['안양시만안구', '안양시동안구'],
  '안산시': ['안산시상록구', '안산시단원구'],
  '청주시': ['청주시상당구', '청주시서원구', '청주시흥덕구', '청주시청원구'],
  '천안시': ['천안시동남구', '천안시서북구'],
  '전주시': ['전주시완산구', '전주시덕진구'],
  '창원시': ['창원시의창구', '창원시성산구', '창원시마산합포구', '창원시마산회원구', '창원시진해구'],
  '포항시': ['포항시남구', '포항시북구'],
};

function mergeSigunguResults(parts) {
  // 합산 — candidates votes·electors·voted 합. pct 재계산.
  if (!parts.length) return null;
  const ec = parts.reduce((s, p) => s + (p.electors || 0), 0);
  const vt = parts.reduce((s, p) => s + (p.voted || 0), 0);
  const byCand = new Map();
  for (const p of parts) {
    for (const c of p.candidates || []) {
      const key = `${c.party}|${c.name}`;
      const prev = byCand.get(key) || { name: c.name, party: c.party, votes: 0 };
      prev.votes += (c.votes || 0);
      byCand.set(key, prev);
    }
  }
  const totalV = [...byCand.values()].reduce((s, c) => s + c.votes, 0);
  const cands = [...byCand.values()]
    .map((c) => ({ ...c, pct: totalV ? +(c.votes / totalV * 100).toFixed(2) : 0 }))
    .sort((a, b) => b.votes - a.votes);
  return {
    sido: parts[0].sido,
    name: parts[0].name,
    electors: ec,
    voted: vt,
    turnout: ec ? +(vt / ec * 100).toFixed(2) : 0,
    candidates: cands,
    _merged: parts.map(p => p.name),
  };
}

function resultForSigungu(sido, name) {
  const data = activeOfficeData();
  if (!data?.sigungu) return null;
  const exact = data.sigungu.find((r) => canonSido(r.sido) === sido && r.name === name);
  if (exact) return exact;
  // disambig 자동 처리: 옛 NEC 데이터 '동구(대전)'·'고성군(강원)' → hex 'name'
  // 시도 일치 + name+'(...)'로 시작하는 데이터 찾음
  const disambig = data.sigungu.find((r) =>
    canonSido(r.sido) === sido && r.name.replace(/\([^)]+\)$/, '') === name
  );
  if (disambig) return disambig;
  // 데이터 sigungu='세종특별자치시' (시도와 동일) → hex '세종시' 매칭
  if (name === '세종시' && sido === '세종특별자치시') {
    const r = data.sigungu.find((rr) => rr.sido === '세종특별자치시');
    if (r) return r;
  }
  // 시도 이동 fallback (예: 군위군 대구↔경북)
  const altSidos = SIGUNGU_SIDO_HISTORY[name];
  if (altSidos && altSidos.includes(sido)) {
    for (const alt of altSidos) {
      if (alt === sido) continue;
      const r = data.sigungu.find((rr) => canonSido(rr.sido) === alt && rr.name === name);
      if (r) return r;
    }
  }
  // 행정구역 변경 alias (당진군·여주군·청원군·세종특별자치시·미추홀구↔남구)
  const oldNames = SIGUNGU_NAME_HISTORY[name];
  if (oldNames) {
    for (const old of oldNames) {
      const r = data.sigungu.find((rr) => canonSido(rr.sido) === sido && rr.name === old);
      if (r) return r;
    }
  }
  // 1 hex ↔ N 데이터 합산 (부천 5/6회)
  const partNames = SIGUNGU_MERGE[name];
  if (partNames) {
    const parts = partNames
      .map((pn) => data.sigungu.find((rr) => canonSido(rr.sido) === sido && rr.name === pn))
      .filter(Boolean);
    if (parts.length) return mergeSigunguResults(parts);
  }
  // 분할구 fallback — '고양시덕양구' → '고양시' (모도시 데이터 broadcast)
  const m = name.match(/^([가-힣]+시)[가-힣]+(구|군)$/);
  if (m) {
    const parent = m[1];
    return data.sigungu.find((r) => canonSido(r.sido) === sido && r.name === parent) || null;
  }
  // Reverse-merge — hex name이 통합 시(name이 '○○시')인데 데이터에 분구만 있음.
  // 21대 대선의 '화성시'(데이터: 화성시갑/을), '부천시'(부천시오정/원미/소사구) 케이스.
  // name+자치구/선거구 분구 entries 자동 합산.
  if (/^[가-힣]+시$/.test(name)) {
    const escape = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const subRe = new RegExp(`^${escape}(?:[가-힣]+(?:구|군)|[갑을병정무])$`);
    const parts = data.sigungu.filter((r) => canonSido(r.sido) === sido && subRe.test(r.name));
    if (parts.length) return mergeSigunguResults(parts);
  }
  return null;
}

// 지역구 결과 (총선만)
function resultForDistrict(sido, name) {
  if (!state.results?.district) return null;
  return state.results.district.find((r) => canonSido(r.sido) === sido && r.name === name) || null;
}

// 시도 단위 합산 — 시군구 결과를 시도별 합산해서 1위 정당 결정
function resultForSido(sido) {
  const data = activeOfficeData();
  if (!data?.sigungu) return null;
  const matched = data.sigungu.filter((r) => canonSido(r.sido) === sido);
  if (!matched.length) return null;
  // broadcast (같은 시도 시군구 모두 동일) 인 경우는 첫 결과 그대로
  if (data._meta?.granularity === 'sido_broadcast' || state.results?._meta?.granularity === 'sido_broadcast') {
    const r = matched[0];
    return {
      sido,
      electors: r.electors,
      voted: r.voted,
      turnout: r.turnout,
      candidates: r.candidates,
    };
  }
  // 시군구 합산
  let electors = 0, voted = 0;
  const cands = new Map(); // key=`${party}|${name}` → {party,name,votes}
  for (const r of matched) {
    electors += r.electors || 0;
    voted += r.voted || 0;
    for (const c of r.candidates || []) {
      const k = `${c.party}|${c.name}`;
      const prev = cands.get(k) || { party: c.party, name: c.name, votes: 0 };
      prev.votes += c.votes || 0;
      cands.set(k, prev);
    }
  }
  const total = [...cands.values()].reduce((s, c) => s + c.votes, 0);
  const list = [...cands.values()]
    .map((c) => ({ ...c, pct: total ? (c.votes / total * 100) : 0 }))
    .sort((a, b) => b.votes - a.votes);
  return {
    sido,
    electors, voted,
    turnout: electors ? (voted / electors * 100) : 0,
    candidates: list,
  };
}

function topCandidate(result) {
  if (!result?.candidates?.length) return null;
  return result.candidates[0];
}

// 투표율 표시: 0 또는 null이면 elections.json의 회차 메타 fallback, 그것도 없으면 '—'
function turnoutLabel(value, elMeta) {
  if (value != null && value > 0) return value.toFixed(1) + '%';
  if (elMeta?.turnout != null && elMeta.turnout > 0) return elMeta.turnout.toFixed(1) + '% (전국)';
  return '—';
}

// 후보 라벨: name이 '비례'·빈값이거나 정당과 같으면 정당명만, 아니면 후보명.
function candLabel(c) {
  if (!c) return '';
  if (!c.name || c.name === '비례' || c.name === c.party) return c.party || '';
  return c.name;
}

// hexPoints·nbrs·NBR_TO_EDGE·corner → assets/hexgrid.js (공용)

// === 시도 17셀 hex (메인 페이지와 동일 layout) ===

// 회차 date 기준 시도 cell 표시 여부 (시도 신설·통합 처리).
//   세종특별자치시: 2012-07-01 신설 (그 이전 회차에선 cell 자체 없음)
//   전남광주특별시: 2026-06-03 신설 (9회 지선 이전 회차에선 광주·전남 별개)
const SIDO_HEX_SINCE = {
  '세종특별자치시': '2012-07-01',
  '전남광주특별시': '2026-06-03',
};
// 9회 이전 layout — 5 row, row 2가 5 cell (광주 추가), row 3 3 cell (전남 추가).
//   row 2: 광주(1) 전북(2) 대전(3) 대구(4) 울산(5)
//   row 3: 전남(1) 경남(2) 부산(3)
//   row 4: 제주(2)
// parties.js 9회 active에 광주(전남광주 자리)·전남(전남광주 자리) cell 추가, row 3 부산 그대로.
const SIDO_HEX_LAYOUT_LEGACY = {
  '광주광역시':     { col: 1, row: 2, label: '광주' },  // 전북 col 2 좌측 추가
  '전라남도':       { col: 1, row: 3, label: '전남' },  // 9회 전남광주 자리에 전남 (광주는 row 2로)
};
// 세종 신설 전 layout — row 1 충남·충북·경북 col 2·3·4 가운데 정렬 (빈 자리 0).
const SIDO_HEX_LAYOUT_PRE_SEJONG = {
  '충청남도': { col: 2, row: 1, label: '충남' },
  '충청북도': { col: 3, row: 1, label: '충북' },
  '경상북도': { col: 4, row: 1, label: '경북' },
};

function getActiveSidoLayout(electionDate) {
  let layout = { ...SIDO_HEX_LAYOUT };
  // 9회 이전 — 광주·전남 별개
  if (electionDate && electionDate < '2026-06-03') {
    layout = { ...layout, ...SIDO_HEX_LAYOUT_LEGACY };
    delete layout['전남광주특별시'];
  }
  // 세종 신설 전 — row 1 가운데 정렬, 세종 cell 자체 제거
  if (electionDate && electionDate < '2012-07-01') {
    layout = { ...layout, ...SIDO_HEX_LAYOUT_PRE_SEJONG };
    delete layout['세종특별자치시'];
  }
  return layout;
}

function renderSidoHex() {
  const svg = $('#hex');
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  const r = 56;
  const colW = r * Math.sqrt(3);
  const rowH = r * 1.5;
  const offsetX = 75 - colW;
  const offsetY = 70;

  const el = (state.elections[state.type]?.elections || []).find((x) => x.n === state.n);
  const electionDate = el?.date || '';
  const layout = getActiveSidoLayout(electionDate);

  for (const [sido, pos] of Object.entries(layout)) {
    if (sido === '전라북도') continue; // 전북특별자치도와 중복 alias
    const since = SIDO_HEX_SINCE[sido];
    if (since && electionDate && electionDate < since) continue;
    const [cx, cy] = hexCenter(pos.col, pos.row, colW, rowH, offsetX, offsetY);
    const result = resultForSido(sido);
    const top = topCandidate(result);
    const sec = result?.candidates?.length >= 2 ? result.candidates[1] : null;
    const gap = top && sec ? top.pct - sec.pct : null;
    const fill = top ? partyColor(top.party) : '#e6e9ef';
    const opacity = top ? gapOpacity(gap) : 1;
    const isSelected = state.selected?.sido === sido && !state.selected?.name;

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.style.cursor = result ? 'pointer' : 'default';
    g.addEventListener('click', () => {
      state.selected = { sido };
      renderAll();
      renderDetail();
    });

    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', 'hex-cell ' + (top ? 'has-data' : 'no-data') + (isSelected ? ' is-selected' : ''));
    poly.setAttribute('points', hexPoints(cx, cy, r - 2));
    poly.setAttribute('fill', fill);
    poly.setAttribute('stroke', '#0a0e1a');
    poly.setAttribute('stroke-width', isSelected ? '2.2' : '1.2');
    poly.setAttribute('fill-opacity', opacity);
    g.appendChild(poly);

    const t1 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t1.setAttribute('class', 'hex-label');
    t1.setAttribute('x', cx);
    t1.setAttribute('y', cy + 2);
    t1.setAttribute('text-anchor', 'middle');
    t1.setAttribute('fill', top ? '#fff' : '#1b2237');
    t1.setAttribute('font-weight', '700');
    t1.setAttribute('font-size', '15');
    t1.setAttribute('pointer-events', 'none');
    t1.textContent = pos.label;
    g.appendChild(t1);

    if (top) {
      const t2 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t2.setAttribute('class', 'hex-pct');
      t2.setAttribute('x', cx);
      t2.setAttribute('y', cy + 20);
      t2.setAttribute('text-anchor', 'middle');
      t2.setAttribute('fill', '#fff');
      t2.setAttribute('font-size', '11');
      t2.setAttribute('pointer-events', 'none');
      const lbl = candLabel(top);
      // 라벨+pct 총 길이로 폰트 동적 축소 (CSS 덮기 위해 style 사용)
      const total = lbl.length + (top.pct?.toFixed(1) || '').length + 2;
      t2.style.fontSize = total >= 14 ? '7px' : total >= 11 ? '9px' : '11px';
      t2.textContent = `${lbl} ${top.pct?.toFixed(1)}%`;
      g.appendChild(t2);
    }
    svg.appendChild(g);
  }
}

// === 지역구 hex (총선 전용) ===

// 지역구명 축약: '동해시태백시삼척시정선군' → '동해/태백/삼척/정선' (길면)
// 시도 prefix는 SIDO_HEX_LAYOUT.label에서 추출하여 별도로 추가 (시군구 hex 라벨 패턴과 동일).
function shortDistrictLabel(name, sido) {
  // 분할 suffix 분리
  const m = name.match(/^(.+?)([갑을병정무])$/);
  const base = m ? m[1] : name;
  const suf = m ? m[2] : '';
  // 시/군/구 단위로 split
  const parts = base.match(/[가-힣]+?(?:특별자치시|특별시|광역시|특별자치도|시|군|구)/g) || [base];
  let body;
  if (parts.length === 1) {
    body = parts[0].replace(/(시|군|구)$/, '');
  } else {
    body = parts.map(p => p.replace(/(시|군|구)$/, '').slice(0, 2)).join('/');
  }
  // 갑/을 suffix는 body에 붙임 ('평택갑')
  if (suf) body = body + suf;
  // SIDO_HEX_LAYOUT에 '전라남도'·'광주광역시'는 9회 통합으로 인해 '전남광주특별시' 키만
  // 등록됨. 22대 이전 회차 cells가 '전라남도'·'광주광역시' sido이라 fallback 필요.
  const SIDO_LABEL_FALLBACK = {
    '전라남도': '전남', '광주광역시': '광주',
    '강원도': '강원', '제주도': '제주', '전라북도': '전북',
  };
  const sidoAbbr = sido ? (SIDO_HEX_LAYOUT[sido]?.label || SIDO_LABEL_FALLBACK[sido] || sido.slice(0, 2)) : '';
  return { prefix: sidoAbbr, short: body, fullName: name };
}

// === 21·22대 GeoJSON chloropleth (OhmyNews MIT) + 시도 경계 overlay ===
async function loadGeo(n) {
  if (state.geoCache[n] && state.geoMapCache[n]) return;
  const [geo, mapj] = await Promise.all([
    loadJson(`data/geo/district_${n}_geojson.json`),
    loadJson(`data/geo/district_${n}_geojson_map.json`),
  ]);
  state.geoCache[n] = geo;
  state.geoMapCache[n] = mapj.name_to_sgg_code;
}

async function loadSidoGeo() {
  if (state.geoSido) return;
  state.geoSido = await loadJson('data/geo/sido_simple.json');
}

function _geoDisplayName(p, n) {
  // 22대: SIDO_SGG (예: '서울 강서갑'), 21대: SGG_2 (예: '경기도 고양시갑')
  return p.SIDO_SGG || p.SGG_2 || p.SGG || '';
}

// === Leaflet geomap (21·22대 총선 지역구 chloropleth) ===
// 확대·패닝 + 미니맵 지원. polls.js 패턴 재사용.

let geoLeafletMap = null;
let geoDistrictLayer = null;    // 현재 회차 layer
let geoDistrictByN = {};        // n → L.geoJSON layer (캐시, 재방문 시 재생성 안 함)
let geoSidoOutlineLayer = null;
let geoMiniMapCtrl = null;
let geoInitialZoom = null;
const KOREA_BOUNDS_GEO = [[32.5, 123.5], [39.5, 132.5]];

function _districtStyleFor(info) {
  return {
    color: 'rgba(10,14,26,0.35)',
    weight: 0.6,
    fillColor: info?.winner?.party ? partyColor(info.winner.party) : 'rgba(154,163,179,0.65)',
    fillOpacity: 0.85,
  };
}

function _attachDistrictInteraction(feature, layer, info, label) {
  layer.bindTooltip(
    info ? `${label} — ${info.winner?.name || ''} (${info.winner?.party || ''})` : label,
    { className: 'sigungu-tooltip', sticky: true, direction: 'auto' }
  );
  if (info) {
    layer.on('mouseover', () => layer.setStyle({ weight: 1.8, color: 'rgba(10,14,26,0.85)' }));
    layer.on('mouseout', () => layer.setStyle({ weight: 0.6, color: 'rgba(10,14,26,0.35)' }));
    layer.on('click', () => {
      state.selected = { sido: info.race.sido, name: info.race.name, kind: 'district' };
      renderDetail();
    });
  }
}

function _setupGeoMiniMap(sidoData) {
  if (geoMiniMapCtrl || typeof L.Control.MiniMap === 'undefined') return;
  const miniLayer = L.geoJSON(sidoData, {
    style: { color: 'rgba(10,14,26,0.4)', weight: 0.6, fillColor: 'rgba(230,233,239,0.85)', fillOpacity: 0.85 },
    interactive: false,
  });
  const MAINLAND = L.latLngBounds([32.8, 125.6], [38.8, 130.0]);
  const TARGET_H = 170;
  let miniZoom = geoInitialZoom;
  let sw, ne, miniW, miniH;
  for (let i = 0; i < 8; i++) {
    sw = geoLeafletMap.project(MAINLAND.getSouthWest(), miniZoom);
    ne = geoLeafletMap.project(MAINLAND.getNorthEast(), miniZoom);
    miniH = sw.y - ne.y;
    if (miniH > TARGET_H * 1.4 && miniZoom > 0) { miniZoom--; continue; }
    if (miniH < TARGET_H * 0.7) { miniZoom++; continue; }
    break;
  }
  miniW = Math.ceil(ne.x - sw.x) + 12;
  miniH = Math.ceil(miniH) + 12;
  geoMiniMapCtrl = new L.Control.MiniMap(miniLayer, {
    position: 'bottomleft',
    width: miniW,
    height: miniH,
    toggleDisplay: false,
    zoomLevelFixed: miniZoom,
    centerFixed: MAINLAND.getCenter(),
    aimingRectOptions: { color: '#e61e2b', weight: 2, fillColor: '#e61e2b', fillOpacity: 0.15 },
  }).addTo(geoLeafletMap);
  const updateMini = () => {
    const path = geoMiniMapCtrl._aimingRect && geoMiniMapCtrl._aimingRect._path;
    if (!path) return;
    path.style.display = geoLeafletMap.getZoom() > geoInitialZoom ? '' : 'none';
  };
  geoLeafletMap.on('zoomend', updateMini);
  geoLeafletMap.on('moveend', updateMini);
  setTimeout(updateMini, 0);
}

async function renderGeoMap() {
  const n = state.n;
  await Promise.all([loadGeo(n), loadSidoGeo()]);
  const features = state.geoCache[n]?.features || [];
  if (!features.length) return;
  const sggMap = state.geoMapCache[n];
  const sggToWinner = {};
  const districts = state.results?.district || [];
  for (const race of districts) {
    // sggMap 키는 새 sido명(전북특별자치도·강원특별자치도) 기준. 옛 race 데이터(전라북도·강원도)는
    // canonSido로 정규화해 매칭.
    const key = `${canonSido(race.sido)}|${race.name}`;
    const sggCode = sggMap[key];
    if (sggCode == null) continue;
    const winner = (race.candidates || []).find((c) => c.won || c.rank === 1) || race.candidates?.[0];
    sggToWinner[String(sggCode)] = { race, winner };
  }

  if (!geoLeafletMap) {
    geoLeafletMap = L.map('geomap', {
      zoomControl: true,
      attributionControl: false,
      maxBounds: KOREA_BOUNDS_GEO,
      maxBoundsViscosity: 1.0,
    });
    geoLeafletMap.setView([35.9, 127.8], 6);
  } else {
    geoLeafletMap.invalidateSize();
  }

  // 기존 회차 layer 제거 (회차 바뀐 경우)
  if (geoDistrictLayer && geoLeafletMap.hasLayer(geoDistrictLayer)) {
    geoLeafletMap.removeLayer(geoDistrictLayer);
  }

  // 회차별 layer 캐시 — winner 색만 재적용
  if (!geoDistrictByN[n]) {
    geoDistrictByN[n] = L.geoJSON(state.geoCache[n], {
      style: (f) => _districtStyleFor(sggToWinner[String(f.properties.SGG_Code)]),
      onEachFeature: (f, l) => {
        const info = sggToWinner[String(f.properties.SGG_Code)];
        _attachDistrictInteraction(f, l, info, _geoDisplayName(f.properties, n));
      },
    });
  } else {
    // 캐시된 layer는 style/tooltip만 갱신
    geoDistrictByN[n].eachLayer((l) => {
      const f = l.feature;
      const info = sggToWinner[String(f.properties.SGG_Code)];
      l.setStyle(_districtStyleFor(info));
      l.unbindTooltip();
      _attachDistrictInteraction(f, l, info, _geoDisplayName(f.properties, n));
    });
  }
  geoDistrictLayer = geoDistrictByN[n];
  geoDistrictLayer.addTo(geoLeafletMap);

  // 시도 외곽선 overlay (한 번만 생성)
  if (!geoSidoOutlineLayer && state.geoSido) {
    geoSidoOutlineLayer = L.geoJSON(state.geoSido, {
      style: { color: 'rgba(10,14,26,0.85)', weight: 1.4, fill: false, lineJoin: 'round' },
      interactive: false,
    });
  }
  if (geoSidoOutlineLayer && !geoLeafletMap.hasLayer(geoSidoOutlineLayer)) {
    geoSidoOutlineLayer.addTo(geoLeafletMap);
  }
  if (geoSidoOutlineLayer) geoSidoOutlineLayer.bringToFront();

  // 초기 fitBounds + minimap (한 번만)
  if (geoInitialZoom == null) {
    const bounds = geoDistrictLayer.getBounds();
    geoLeafletMap.fitBounds(bounds, { padding: [12, 12] });
    const finalize = () => {
      geoLeafletMap.off('moveend', finalize);
      geoInitialZoom = geoLeafletMap.getZoom();
      geoLeafletMap.setMinZoom(geoInitialZoom);
      if (state.geoSido) _setupGeoMiniMap(state.geoSido);
    };
    geoLeafletMap.on('moveend', finalize);
  }
}


async function renderDistrictHex() {
  const layout = await loadDistrictHex(state.n);
  const svg = $('#hex2');
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  if (!layout?.length) return;
  const cs = layout.map((d) => d.c);
  const rs = layout.map((d) => d.r);
  const minC = Math.min(...cs), minR = Math.min(...rs);
  const maxC = Math.max(...cs), maxR = Math.max(...rs);
  const r = 22;
  const colW = r * Math.sqrt(3);
  const rowH = r * 1.5;
  const w = (maxC - minC + 2) * colW;
  const h = (maxR - minR + 2) * rowH;
  svg.setAttribute('viewBox', `0 0 ${Math.ceil(w)} ${Math.ceil(h)}`);
  const offX = -minC * colW + colW / 2;
  const offY = -minR * rowH + rowH;

  const cellAt = new Map();
  for (const d of layout) cellAt.set(`${d.c},${d.r}`, d);
  // nbrs·NBR_TO_EDGE·corner → assets/hexgrid.js (공용)

  for (const d of layout) {
    const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
    const result = resultForDistrict(d.sido, d.name);
    const top = topCandidate(result);
    const sec = result?.candidates?.length >= 2 ? result.candidates[1] : null;
    const gap = top && sec ? top.pct - sec.pct : null;
    const fill = top ? partyColor(top.party) : '#e6e9ef';
    const opacity = top ? 1 : 1;
    const isSelected = state.selected
      && state.selected.sido === d.sido && state.selected.name === d.name;

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.style.cursor = result ? 'pointer' : 'default';
    g.addEventListener('click', () => {
      state.selected = { sido: d.sido, name: d.name, kind: 'district' };
      renderAll();
    });

    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', 'hex-cell ' + (top ? 'has-data' : 'no-data') + (isSelected ? ' is-selected' : ''));
    poly.setAttribute('points', hexPoints(cx, cy, r - 0.7));
    poly.setAttribute('fill', fill);
    poly.setAttribute('stroke', '#0a0e1a');
    poly.setAttribute('stroke-width', isSelected ? '1.6' : '0.7');
    poly.setAttribute('fill-opacity', opacity);
    g.appendChild(poly);

    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = top
      ? `${d.sido} ${d.name} · ${top.name} (${top.party}) ${result.uncontested ? '무투표 당선' : top.pct?.toFixed(1) + '%'}`
      : `${d.sido} ${d.name} · 데이터 없음`;
    g.appendChild(title);

    const lbl = shortDistrictLabel(d.name, d.sido);
    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x', cx);
    txt.setAttribute('text-anchor', 'middle');
    txt.setAttribute('font-weight', '600');
    txt.setAttribute('fill', top ? '#fff' : '#0a0e1a');
    txt.setAttribute('pointer-events', 'none');
    txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
    // 시군구 hex와 동일 패턴: prefix(시도, 작게·옅게) 위 + short(지역구+갑) 아래
    if (lbl.prefix) {
      const tp1 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
      tp1.setAttribute('x', cx);
      tp1.setAttribute('y', cy - 2);
      tp1.setAttribute('font-size', '6');
      tp1.setAttribute('opacity', '0.75');
      tp1.textContent = lbl.prefix;
      txt.appendChild(tp1);
      const tp2 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
      tp2.setAttribute('x', cx);
      tp2.setAttribute('y', cy + 8);
      tp2.setAttribute('font-size', lbl.short.length > 4 ? '6' : lbl.short.length > 3 ? '7' : '9');
      tp2.textContent = lbl.short;
      txt.appendChild(tp2);
    } else {
      txt.setAttribute('y', cy + 3);
      txt.setAttribute('font-size', lbl.short.length > 4 ? '6' : '8');
      txt.textContent = lbl.short;
    }
    g.appendChild(txt);
    svg.appendChild(g);
  }

  // 시도 경계 굵은 선 + 한반도 외곽 — drawHexBorders (hexgrid.js)
  drawHexBorders(svg, layout, cellAt, colW, rowH, offX, offY, r, '1.8', true);

  // 비례대표 — 정당별 세로 col, 지역구 hex 우측에 배치. 사이즈는 지역구와 동일(r=22).
  // 같은 col 안 vertical pitch = 1.5r (격자 hex 표준, odd col 0.5 row shift로 interlock).
  const propSeats = state.results?.national?.proportional_seats || [];
  if (propSeats.length) {
    const totalProp = propSeats.reduce((s, p) => s + p.seats, 0);
    const totalSeats = layout.length + totalProp;
    const sorted = [...propSeats].sort((a, b) => b.seats - a.seats);
    const ns = 'http://www.w3.org/2000/svg';

    const propGap = colW * 0.8;          // 지역구와 비례 영역 사이 여백
    const propStartX = w + propGap;      // 비례 첫 col 좌측 base
    const propColW = colW;               // 정당 col 폭 = 지역구 colW (snug interlock)
    const propRowH = rowH;               // 세로 pitch = 지역구 rowH (1.5r)
    const labelOffsetY = -rowH * 0.6;    // 정당 라벨 baseline (첫 hex 위쪽)

    // 헤더 (지역구 위쪽 여백, 비례 영역 상단)
    const headerY = labelOffsetY * 2;    // 정당 라벨보다 더 위
    const sectionLabel = document.createElementNS(ns, 'text');
    sectionLabel.setAttribute('x', propStartX);
    sectionLabel.setAttribute('y', headerY);
    sectionLabel.setAttribute('font-size', '12');
    sectionLabel.setAttribute('font-weight', '700');
    sectionLabel.setAttribute('fill', '#0a0e1a');
    sectionLabel.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
    sectionLabel.textContent = `비례대표 ${totalProp}석 · 총 ${totalSeats}석`;
    svg.appendChild(sectionLabel);

    let maxColH = 0;
    sorted.forEach((ps, pi) => {
      const color = partyColor(ps.party);
      // odd col 0.5 row shift로 interlock (지역구 hex와 같은 odd-r offset 패턴).
      const colCx = propStartX + (pi + 0.5) * propColW;
      // 정당 라벨 (col 위쪽)
      const nm = document.createElementNS(ns, 'text');
      nm.setAttribute('x', colCx);
      nm.setAttribute('y', labelOffsetY);
      nm.setAttribute('text-anchor', 'middle');
      nm.setAttribute('font-size', '11');
      nm.setAttribute('font-weight', '700');
      nm.setAttribute('fill', color);
      nm.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      nm.textContent = `${ps.party} ${ps.seats}`;
      svg.appendChild(nm);
      // 의석 hex 세로 stack (위→아래)
      for (let j = 0; j < ps.seats; j++) {
        const cy = j * propRowH + r;  // 첫 hex 중심 = top + r
        // odd col은 0.5 row shift
        const cxShift = (pi % 2) * 0;   // col 자체 위치는 위에서 잡았으니 추가 shift 없음
        const cy2 = cy + (pi % 2) * (rowH / 2);
        const poly = document.createElementNS(ns, 'polygon');
        poly.setAttribute('points', hexPoints(colCx + cxShift, cy2, r - 0.7));
        poly.setAttribute('fill', color);
        poly.setAttribute('stroke', '#fff');
        poly.setAttribute('stroke-width', '1');
        const tt = document.createElementNS(ns, 'title');
        tt.textContent = `비례 ${ps.party} ${j + 1}/${ps.seats}석`;
        poly.appendChild(tt);
        svg.appendChild(poly);
      }
      const colH = ps.seats * propRowH + (pi % 2) * (rowH / 2) + r;
      if (colH > maxColH) maxColH = colH;
    });

    // viewBox 확장 — 우측 비례 + 위쪽 라벨 영역까지
    const newW = propStartX + sorted.length * propColW + propGap;
    const topPad = -headerY + 8;
    const newH = Math.max(h, maxColH) + topPad;
    const minY = headerY - 8;
    svg.setAttribute('viewBox', `0 ${Math.floor(minY)} ${Math.ceil(newW)} ${Math.ceil(newH)}`);
  }
}

// === 시군구 hex ===

function renderSigunguHex() {
  const svg = $('#hex2');
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  // 대선만 일반구별 개표 단위 (legacy sigungu hex). 지선은 통합 시장이라 base hex.
  // 총선은 지역구(district_hex_*.json) — renderDistrictHex가 별도 처리.
  const useLegacy = state.hexLegacy && state.type === 'presidential';
  let data = useLegacy ? state.hexLegacy : state.hexData;
  if (!data?.length) return;
  // 회차별 자동 hide — data.sigungu에 매칭 없는 cell (행정구역상 그 시점 존재 X 또는 데이터 누락)
  data = data.filter((d) => resultForSigungu(d.sido, d.name));
  const cs = data.map((d) => d.c);
  const rs = data.map((d) => d.r);
  const minC = Math.min(...cs), minR = Math.min(...rs);
  const maxC = Math.max(...cs), maxR = Math.max(...rs);
  const r = 22;
  const colW = r * Math.sqrt(3);
  const rowH = r * 1.5;
  const w = (maxC - minC + 2) * colW;
  const h = (maxR - minR + 2) * rowH;
  svg.setAttribute('viewBox', `0 0 ${Math.ceil(w)} ${Math.ceil(h)}`);
  const offX = -minC * colW + colW / 2;
  const offY = -minR * rowH + rowH;

  // (c,r) → cell lookup (시도 경계 감지에 사용)
  const cellAt = new Map();
  for (const d of data) cellAt.set(`${d.c},${d.r}`, d);
  // nbrs·NBR_TO_EDGE·corner → assets/hexgrid.js (공용)

  // 사이즈 모드 4가지: 동일 / 반지름 (hex radius scale) / 격자 (multiple small hexes per sigungu) / dorling (circles)
  const sizingMode = state.sizing || '동일';
  let maxVoted = 0;
  for (const d of data) {
    const result = resultForSigungu(d.sido, d.name);
    if (result?.voted) maxVoted = Math.max(maxVoted, result.voted);
  }
  const minRatio = 0.20;

  // 격자 hex 모드: 시군구당 N개 작은 hex 패킹 (1 hex = 2만표)
  if (sizingMode === '격자' && maxVoted > 0) {
    const unit = 20000;  // 1 hex = 2만표 (고정 — 회차·선거 동일 단위로 비교 가능)
    const smallR = 3.2;  // unit ↓ → N ↑ (×2.5) → 면적 보존 위해 r √2.5 분의 1
    // axial 좌표 BFS 스파이럴 (1..N hex 배치)
    function hexSpiral(N) {
      const out = [[0, 0]];
      if (N <= 1) return out;
      const seen = new Set(['0,0']);
      let frontier = [[0, 0]];
      const DIRS = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]];
      while (out.length < N) {
        const next = [];
        for (const [q, ar] of frontier) {
          for (const [dq, dr] of DIRS) {
            const nq = q + dq, nr = ar + dr;
            const key = nq + ',' + nr;
            if (seen.has(key)) continue;
            seen.add(key);
            next.push([nq, nr]);
            out.push([nq, nr]);
            if (out.length >= N) return out;
          }
        }
        frontier = next;
      }
      return out;
    }
    // 후보별 hex 개수 — 큰 정수 잔여(largest remainder) 방식으로 N에 정확히 맞춤.
    function allocateByVotes(cands, N) {
      const total = cands.reduce((s, c) => s + (c.votes || 0), 0);
      if (!total) return cands.map(() => 0);
      const raw = cands.map((c) => (c.votes || 0) * N / total);
      const floors = raw.map(Math.floor);
      let rem = N - floors.reduce((a, b) => a + b, 0);
      const fracs = raw.map((v, i) => ({ i, f: v - Math.floor(v) }))
                       .sort((a, b) => b.f - a.f);
      for (let k = 0; k < rem; k++) floors[fracs[k].i] += 1;
      return floors;
    }
    for (const d of data) {
      const result = resultForSigungu(d.sido, d.name);
      if (!result?.voted) continue;
      const N = Math.max(1, Math.ceil(result.voted / unit));
      const [cx0, cy0] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
      const cands = (result.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      const alloc = allocateByVotes(cands, N);
      const top = cands[0];
      const isSelected = state.selected
        && state.selected.sido === d.sido && state.selected.name === d.name;
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.style.cursor = 'pointer';
      g.addEventListener('click', () => {
        state.selected = { sido: d.sido, name: d.name, code: d.code };
        renderAll(); renderDetail();
      });
      const tt = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      tt.textContent = top
        ? `${d.sido} ${d.name} · ${candLabel(top)} (${top.party}) ${top.pct?.toFixed(1)}% · ${N}석/표`
        : `${d.sido} ${d.name}`;
      g.appendChild(tt);
      // 시군구 boundary outline — 작은 hex cluster 둘러쌈 (시각 통합, 인접 격자 겹침 방지)
      const sigOutline = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      sigOutline.setAttribute('points', hexPoints(cx0, cy0, 22));
      sigOutline.setAttribute('fill', isSelected ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.35)');
      sigOutline.setAttribute('stroke', isSelected ? '#0a0e1a' : 'rgba(27,34,55,0.45)');
      sigOutline.setAttribute('stroke-width', isSelected ? '1.8' : '1.0');
      g.appendChild(sigOutline);
      // 후보별 hex 배정 (스파이럴 순서대로 1위→2위→... 채움)
      const spiral = hexSpiral(N);
      const fills = [];
      for (let i = 0; i < cands.length; i++) {
        for (let k = 0; k < alloc[i]; k++) fills.push(partyColor(cands[i].party));
      }
      while (fills.length < N) fills.push('#e6e9ef');  // 안전 fallback
      for (let i = 0; i < spiral.length; i++) {
        const [q, ar] = spiral[i];
        const dx = smallR * Math.sqrt(3) * (q + ar / 2);
        const dy = smallR * 1.5 * ar;
        const sx = cx0 + dx, sy = cy0 + dy;
        const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        poly.setAttribute('points', hexPoints(sx, sy, smallR - 0.4));
        poly.setAttribute('fill', fills[i] || '#e6e9ef');
        poly.setAttribute('stroke', isSelected ? '#0a0e1a' : 'none');
        poly.setAttribute('stroke-width', isSelected ? '1.0' : '0');
        g.appendChild(poly);
      }
      // 시군구 라벨 — cell 상단으로 이동해 spiral(중앙) 안 가림. N 작은 시군구도 색 보임.
      const label = shortSigunguLabel(d.name, d.sido);
      if (label.short) {
        const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        txt.setAttribute('x', cx0);
        txt.setAttribute('text-anchor', 'middle');
        txt.setAttribute('font-weight', '700');
        txt.setAttribute('fill', '#0a0e1a');
        txt.setAttribute('stroke', 'rgba(255,255,255,0.9)');
        txt.setAttribute('stroke-width', '2.2');
        txt.setAttribute('paint-order', 'stroke fill');
        txt.setAttribute('pointer-events', 'none');
        txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
        if (label.prefix) {
          // prefix(작게) 위 + short(메인) 아래 — 둘 다 cell 상단 영역
          const tp1 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
          tp1.setAttribute('x', cx0);
          tp1.setAttribute('y', cy0 - 14);
          tp1.setAttribute('font-size', '6');
          tp1.setAttribute('opacity', '0.75');
          tp1.textContent = label.prefix;
          txt.appendChild(tp1);
          const tp2 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
          tp2.setAttribute('x', cx0);
          tp2.setAttribute('y', cy0 - 5);
          tp2.setAttribute('font-size', label.short.length > 3 ? '7' : '9');
          tp2.textContent = label.short;
          txt.appendChild(tp2);
        } else {
          txt.setAttribute('y', cy0 - 10);
          txt.setAttribute('font-size', label.short.length > 3 ? '7' : '9');
          txt.textContent = label.short;
        }
        g.appendChild(txt);
      }
      svg.appendChild(g);
    }
    // 시도 경계 굵은 선 — 격자 모드도 cell 위치가 동일 모드와 같으므로 적용 가능.
    drawHexBorders(svg, data, cellAt, colW, rowH, offX, offY, r, '1.8', true);
    return;
  }

  // Dorling cartogram: 원, force-directed packing
  if (sizingMode === 'dorling' && maxVoted > 0) {
    const nodes = data.map((d) => {
      const result = resultForSigungu(d.sido, d.name);
      const v = result?.voted || 0;
      const top = topCandidate(result);
      const sec = result?.candidates?.length >= 2 ? result.candidates[1] : null;
      const gap = top && sec ? top.pct - sec.pct : null;
      const [cx0, cy0] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
      return {
        d, result, top,
        cx0, cy0,
        radius: v > 0 ? Math.max(3, (r - 0.7) * Math.sqrt(v / maxVoted)) : 3,
        fill: top ? partyColor(top.party) : '#e6e9ef',
        op: top ? gapOpacity(gap) : 1,
      };
    });
    for (const n of nodes) { n.cx = n.cx0; n.cy = n.cy0; }
    // Force-directed (30 iterations): repel overlaps + anchor to original
    for (let iter = 0; iter < 40; iter++) {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = b.cx - a.cx, dy = b.cy - a.cy;
          const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
          const overlap = a.radius + b.radius - dist;
          if (overlap > 0) {
            const push = overlap * 0.5 / dist;
            a.cx -= push * dx; a.cy -= push * dy;
            b.cx += push * dx; b.cy += push * dy;
          }
        }
      }
      // Anchor towards original position
      for (const n of nodes) {
        n.cx += (n.cx0 - n.cx) * 0.05;
        n.cy += (n.cy0 - n.cy) * 0.05;
      }
    }
    for (const n of nodes) {
      const isSelected = state.selected
        && state.selected.sido === n.d.sido && state.selected.name === n.d.name;
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.style.cursor = 'pointer';
      g.addEventListener('click', () => {
        state.selected = { sido: n.d.sido, name: n.d.name, code: n.d.code };
        renderAll(); renderDetail();
      });
      const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('cx', n.cx);
      c.setAttribute('cy', n.cy);
      c.setAttribute('r', n.radius);
      c.setAttribute('fill', n.fill);
      c.setAttribute('fill-opacity', n.op);
      c.setAttribute('stroke', '#0a0e1a');
      c.setAttribute('stroke-width', isSelected ? '1.6' : '0.5');
      g.appendChild(c);
      const tt = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      tt.textContent = n.top
        ? `${n.d.sido} ${n.d.name} · ${candLabel(n.top)} (${n.top.party}) ${n.top.pct?.toFixed(1)}%`
        : `${n.d.sido} ${n.d.name}`;
      g.appendChild(tt);
      // 라벨 — 큰 원만
      if (n.radius >= 10 && n.top) {
        const lbl = shortSigunguLabel(n.d.name, n.d.sido);
        if (lbl.short) {
          const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          txt.setAttribute('x', n.cx);
          txt.setAttribute('y', n.cy + 3);
          txt.setAttribute('text-anchor', 'middle');
          txt.setAttribute('font-size', '7');
          txt.setAttribute('font-weight', '600');
          txt.setAttribute('fill', '#fff');
          txt.setAttribute('pointer-events', 'none');
          txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
          txt.textContent = lbl.short;
          g.appendChild(txt);
        }
      }
      svg.appendChild(g);
    }
    return;
  }

  for (const d of data) {
    const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
    const result = resultForSigungu(d.sido, d.name);
    const top = topCandidate(result);
    const sec = result?.candidates?.length >= 2 ? result.candidates[1] : null;
    const gap = top && sec ? top.pct - sec.pct : null;
    const fill = top ? partyColor(top.party) : '#e6e9ef';
    const opacity = top ? gapOpacity(gap) : 1;
    // 반지름 결정
    let cellR = r - 0.7;
    if (sizingMode === '반지름' && maxVoted > 0 && result?.voted) {
      const ratio = Math.max(minRatio, Math.sqrt(result.voted / maxVoted));
      cellR = (r - 0.7) * ratio;
    } else if (sizingMode === '반지름') {
      cellR = (r - 0.7) * minRatio;  // 데이터 없는 셀
    }
    const isSelected = state.selected
      && state.selected.sido === d.sido && state.selected.name === d.name;

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.style.cursor = result ? 'pointer' : 'default';
    g.addEventListener('click', () => {
      state.selected = { sido: d.sido, name: d.name, code: d.code };
      renderAll();
      renderDetail();
    });

    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', 'hex-cell ' + (top ? 'has-data' : 'no-data') + (isSelected ? ' is-selected' : ''));
    poly.setAttribute('points', hexPoints(cx, cy, cellR));
    poly.setAttribute('fill', fill);
    poly.setAttribute('stroke', '#0a0e1a');
    poly.setAttribute('stroke-width', isSelected ? '1.6' : '0.7');
    poly.setAttribute('fill-opacity', opacity);
    g.appendChild(poly);

    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = top
      ? `${d.sido} ${d.name} · ${candLabel(top)} (${top.party}) ${top.pct?.toFixed(1)}%`
      : `${d.sido} ${d.name} · 데이터 없음`;
    g.appendChild(title);

    // 라벨 — 작은 hex는 라벨 생략 (가독성)
    const label = shortSigunguLabel(d.name, d.sido);
    if (label.short && cellR >= 8) {
      const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      txt.setAttribute('x', cx);
      txt.setAttribute('text-anchor', 'middle');
      txt.setAttribute('font-weight', '600');
      txt.setAttribute('fill', top ? '#fff' : '#0a0e1a');
      txt.setAttribute('pointer-events', 'none');
      txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      if (label.prefix) {
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
      g.appendChild(txt);
    }
    svg.appendChild(g);
  }

  // 시도 경계 굵은 선 + 한반도 외곽 — dorling 제외 (원 위치가 force-directed로 이동해 경계 불일치).
  // 격자 모드는 spiral 그린 뒤 위쪽에서 별도 호출.
  if (sizingMode === 'dorling') return;
  drawHexBorders(svg, data, cellAt, colW, rowH, offX, offY, r, '1.8', true);
}

// === Parliament half-donut chart ===
// 의회 반도넛 시각화. 각 점 = 1 의석. 좌→우 순서로 정당별 의석 배치.
// parties: [{party, seats, color}] 의석 desc 정렬.
function renderParliamentChart(parties, total, width = 320, height = 170) {
  if (!total) return '';
  const cx = width / 2;
  const cy = height - 14;
  // ring 개수 — 의석 많을수록 많이.
  const rings = total > 280 ? 7 : total > 180 ? 6 : total > 100 ? 5 : 4;
  const rOuter = Math.min(width / 2 - 8, height - 18);
  // inner radius 비율 — ring 개수에 따라 조정
  const rInner = rOuter * (0.40 + 0.04 * (rings - 4));
  const dr = (rOuter - rInner) / Math.max(1, rings - 1);
  const ringR = Array.from({ length: rings }, (_, i) => rInner + i * dr);
  // dot radius — ring 간격에 fit + 가장 안쪽 ring 호 길이로 제한
  // 한 ring 당 dot 개수가 호 길이에 비례하므로, 모두 같은 dot size로 fit 가능.
  // dot 지름 ≈ dr (ring 간격) — 그러면 ring 사이 간격 0, 빽빽.
  // 약간 여유: dr * 0.46
  const seatRadius = dr * 0.46;
  // 각 ring 의석 수 — 호 길이 / (2 × seatRadius × spacing)
  const spacing = 1.15;  // dot 사이 간격
  const ringCap = ringR.map(r => Math.floor((Math.PI * r) / (2 * seatRadius * spacing)));
  // ringCap 합 < total이면 capacity 부족 → seatRadius 조정 (작게).
  let cap = ringCap.reduce((a, b) => a + b, 0);
  let adjRadius = seatRadius;
  while (cap < total && adjRadius > 0.5) {
    adjRadius *= 0.97;
    cap = ringR.map(r => Math.floor((Math.PI * r) / (2 * adjRadius * spacing))).reduce((a, b) => a + b, 0);
  }
  const finalCap = ringR.map(r => Math.floor((Math.PI * r) / (2 * adjRadius * spacing)));
  // 의석을 ring에 분배 — 호 길이 비율로
  const weight = ringR.map(r => Math.PI * r);
  const totalW = weight.reduce((a, b) => a + b, 0);
  let ringSeats = weight.map(w => Math.floor(total * w / totalW));
  let diff = total - ringSeats.reduce((a, b) => a + b, 0);
  for (let i = rings - 1; diff > 0 && i >= 0; i--) {
    const room = finalCap[i] - ringSeats[i];
    const add = Math.min(diff, room);
    ringSeats[i] += add; diff -= add;
  }
  // 각 seat에 (x, y, angle) 결정
  const allSeats = [];
  for (let i = 0; i < rings; i++) {
    const r = ringR[i];
    const n = ringSeats[i];
    if (!n) continue;
    // 양 끝 padding — n>1이면 끝점 안 닿게
    for (let k = 0; k < n; k++) {
      const t = n > 1 ? k / (n - 1) : 0.5;
      const angle = Math.PI * (1 - t);
      allSeats.push({ x: cx + r * Math.cos(angle), y: cy - r * Math.sin(angle), angle });
    }
  }
  allSeats.sort((a, b) => b.angle - a.angle);
  // 정당별 색 배정 (좌→우)
  const seatColors = [];
  for (const p of parties) {
    for (let k = 0; k < p.seats; k++) seatColors.push(p.color);
  }
  let svg = `<svg class="parliament-chart" viewBox="0 0 ${width} ${height}" width="100%" preserveAspectRatio="xMidYMax meet">`;
  for (let i = 0; i < allSeats.length; i++) {
    const s = allSeats[i];
    const c = seatColors[i] || '#bbb';
    svg += `<circle cx="${s.x.toFixed(1)}" cy="${s.y.toFixed(1)}" r="${adjRadius.toFixed(1)}" fill="${c}" stroke="rgba(0,0,0,0.15)" stroke-width="0.4"/>`;
  }
  svg += '</svg>';
  return svg;
}

// === Detail Pane ===

function renderDetail() {
  const pane = $('#detail-pane');
  const list = state.elections[state.type]?.elections || [];
  const el = list.find((x) => x.n === state.n);

  if (!state.results) {
    pane.innerHTML = `<div class="detail-empty">
      <strong>${TYPE_LABEL[state.type].ko} ${state.n}회</strong>
      ${el ? `(${el.date})` : ''}
      <br><br>데이터를 아직 수집하지 않았습니다.
    </div>`;
    return;
  }

  const data = activeOfficeData();
  const nat = data?.national;
  let html = '';
  if (state.type === 'national_assembly' && nat) {
    // 정당별 총 의석 (지역구 winner_party 카운트 + 비례 의석)
    const seatsByParty = new Map();
    for (const d of state.results?.district || []) {
      if (!d.winner_party) continue;
      seatsByParty.set(d.winner_party, (seatsByParty.get(d.winner_party) || 0) + 1);
    }
    for (const p of nat.proportional_seats || []) {
      seatsByParty.set(p.party, (seatsByParty.get(p.party) || 0) + (p.seats || 0));
    }
    const parties = [...seatsByParty.entries()]
      .map(([party, seats]) => ({ party, seats, color: partyColor(party) }))
      .sort((a, b) => b.seats - a.seats);
    const total = parties.reduce((s, p) => s + p.seats, 0);
    const top = parties[0];
    html += `<div class="national-summary" style="border-left-color:${top ? top.color : 'var(--ink)'}">
      <div class="ns-title">${TYPE_LABEL[state.type].ko} ${state.n}회 · 전국 의석</div>
      <div class="ns-name" style="color:${top ? top.color : 'var(--ink)'}">${top ? top.party : '—'}</div>
      <div class="ns-party">${top ? `${top.seats}석 / 총 ${total}석` : ''}</div>
      <div class="ns-stat">
        <span>투표율 ${turnoutLabel(nat?.turnout, el)}</span>
        ${el?.date ? `<span>${el.date}</span>` : ''}
      </div>
    </div>
    <div class="parliament-wrap">
      ${renderParliamentChart(parties, total)}
      <div class="party-seats">
        ${parties.map((p) => `<span class="ps-item" title="${p.party} ${p.seats}석">
          <span class="ps-dot" style="background:${p.color}"></span>${p.party} <b>${p.seats}</b>
        </span>`).join('')}
      </div>
    </div>`;
  } else if (state.type === 'local') {
    // 지선 — 광역단체장·기초단체장·교육감 winner_party 카운트 (정당별 당선 곳 수)
    const winsByParty = new Map();
    for (const r of data?.sigungu || []) {
      const winner = r.candidates?.[0];
      if (!winner?.party) continue;
      winsByParty.set(winner.party, (winsByParty.get(winner.party) || 0) + 1);
    }
    const parties = [...winsByParty.entries()]
      .map(([party, wins]) => ({ party, wins, color: partyColor(party) }))
      .sort((a, b) => b.wins - a.wins);
    const total = parties.reduce((s, p) => s + p.wins, 0);
    const top = parties[0];
    html += `<div class="national-summary" style="border-left-color:${top ? top.color : 'var(--ink)'}">
      <div class="ns-title">${TYPE_LABEL[state.type].ko} ${state.n}회 · ${state.office}</div>
      <div class="ns-name" style="color:${top ? top.color : 'var(--ink)'}">${top ? top.party : '—'}</div>
      <div class="ns-party">${top ? `${top.wins}곳 / 총 ${total}곳` : (el?.date || '')}</div>
      <div class="ns-stat">
        <span>투표율 ${turnoutLabel(nat?.turnout, el)}</span>
        ${el?.date ? `<span>${el.date}</span>` : ''}
      </div>
    </div>
    ${parties.length ? `<div class="party-seats">
      ${parties.map((p) => `<span class="ps-item" title="${p.party} ${p.wins}곳">
        <span class="ps-dot" style="background:${p.color}"></span>${p.party} <b>${p.wins}</b>
      </span>`).join('')}
    </div>` : ''}`;
  } else if (nat?.candidates?.length) {
    const sorted = [...nat.candidates].sort((a, b) => (b.pct || 0) - (a.pct || 0));
    const top = sorted[0];
    const color = partyColor(top.party);
    const maxPct = top.pct || 0;
    // 1·2위 격차 그리고 전체 분포 (최대 10명 막대그래프)
    const barRows = sorted.slice(0, 10).map((c) => {
      const cColor = partyColor(c.party);
      const w = maxPct > 0 ? ((c.pct || 0) / maxPct) * 100 : 0;
      return `<div class="rc-bar-row">
        <span class="name">${candLabel(c)}</span>
        <span class="rc-bar"><span class="rc-bar-fill" style="width:${w}%;background:${cColor}"></span></span>
        <span class="pct" style="color:${cColor}">${c.pct != null ? c.pct.toFixed(1) + '%' : '—'}</span>
      </div>`;
    }).join('');
    html += `<div class="national-summary" style="border-left-color:${color}">
      <div class="ns-title">${TYPE_LABEL[state.type].ko} ${state.n}회 · 전국</div>
      <div class="ns-name" style="color:${color}">${candLabel(top) || el?.winner || '—'}</div>
      <div class="ns-party">${top.party} · ${top.pct?.toFixed(1)}%</div>
      <div class="ns-stat">
        <span>투표율 ${turnoutLabel(nat?.turnout, el)}</span>
        ${el?.date ? `<span>${el.date}</span>` : ''}
      </div>
    </div>
    <div class="result-card" style="border-left-color:${color}">${barRows}</div>`;
  } else if (el) {
    html += `<div class="national-summary">
      <div class="ns-title">${TYPE_LABEL[state.type].ko} ${state.n}회</div>
      <div class="ns-name">${el.winner || '—'}</div>
      <div class="ns-party">${el.winner_party || ''} · 투표율 ${el.turnout ?? '—'}%</div>
      <div class="ns-stat"><span>${el.date}</span></div>
    </div>`;
  }

  // 선택된 지역 결과 (시도/시군구/지역구)
  if (state.selected) {
    const isSido = !state.selected.name;
    const isDistrict = state.selected.kind === 'district';
    const result = isSido
      ? resultForSido(state.selected.sido)
      : isDistrict
        ? resultForDistrict(state.selected.sido, state.selected.name)
        : resultForSigungu(state.selected.sido, state.selected.name);
    const titleText = isSido ? state.selected.sido : `${state.selected.sido} · ${state.selected.name}`;
    const tag = isSido ? '시도 합산' : isDistrict ? '지역구' : '시군구';
    html += `<div class="detail-hdr">
      <h2>${titleText}</h2>
      <span class="count">${tag}</span>
    </div>`;
    if (result?.candidates?.length) {
      const sorted = [...result.candidates].sort((a, b) => b.pct - a.pct);
      const maxPct = sorted[0].pct;
      const top = sorted[0];
      const leftColor = partyColor(top.party);
      const barRows = sorted.slice(0, 10).map((c) => {
        const color = partyColor(c.party);
        const w = result.uncontested ? 100 : (maxPct > 0 ? (c.pct / maxPct) * 100 : 0);
        return `<div class="rc-bar-row">
          <span class="name">${candLabel(c)}</span>
          <span class="rc-bar"><span class="rc-bar-fill" style="width:${w}%;background:${color}"></span></span>
          <span class="pct" style="color:${color}">${c.pct != null ? c.pct.toFixed(1) + '%' : '무투표'}</span>
        </div>`;
      }).join('');
      html += `<div class="result-card" style="border-left-color:${leftColor}">
        <div class="rc-hdr">
          <span class="rc-name">${candLabel(top)} ${result.uncontested ? '무투표 당선' : '1위'}</span>
          <span class="rc-meta">${result.uncontested ? '단독 출마' : '투표율 ' + turnoutLabel(result.turnout, el)}</span>
        </div>
        ${barRows}
      </div>`;
    } else {
      html += `<div class="detail-empty">이 지역 데이터 없음</div>`;
    }
  } else {
    html += `<div class="detail-empty">시도·시군구를 클릭하면 그 지역 결과가 표시됩니다.</div>`;
  }
  pane.innerHTML = html;
}

init();
