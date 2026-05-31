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
  office: '광역단체장',
  sizing: '동일',  // 동일 | 인구비례 — 시군구 hex 사이즈 모드
  elections: null,
  hexData: null,            // sigungu_hex.json (9회 기준 통합도시)
  hexLegacy: null,          // sigungu_hex_legacy.json (옛 회차 — 일반구 분할)
  districtHex: {},          // {22: [...]} 지역구별 hex layout
  results: null,
  selected: null,
};

const $ = (s) => document.querySelector(s);

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

  // 정적 prerender가 주입한 초기 상태 (URL 기반)
  const init0 = (typeof window !== 'undefined' && window.__INITIAL_STATE__) || {};
  const type0 = init0.type || 'presidential';
  setType(type0, /*skipDefaultRound=*/ init0.n != null);
  // setType이 default office 'is-active' 처리하므로 setOffice는 setType 후 호출
  if (init0.office && init0.office !== state.office) setOffice(init0.office);
  if (init0.n != null) setRound(init0.n);
  $('#loading').hidden = true;
}

function setType(type, skipDefaultRound = false) {
  state.type = type;
  document.querySelectorAll('[data-type]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.type === type);
  });
  $('#offices-seg').hidden = type !== 'local';
  renderRoundsSeg();
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
  renderAll();
}

function setSizing(s) {
  state.sizing = s;
  document.querySelectorAll('[data-sizing]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.sizing === s);
  });
  renderAll();
}

// 현재 단위에 맞는 hex 렌더 + detail
async function renderAll() {
  const unit = activeUnit(state.type, state.office, state.results);
  $('#hex').toggleAttribute('hidden', unit !== 'sido');
  $('#hex2').toggleAttribute('hidden', unit === 'sido');
  // 사이즈 토글은 시군구 hex에서만 의미 있음 (반지름·격자·dorling이 시군구 응답수 기반)
  $('#sizing-seg').toggleAttribute('hidden', unit !== 'sigungu');
  if (unit === 'sido') renderSidoHex();
  else if (unit === 'district') await renderDistrictHex();
  else renderSigunguHex();
  renderDetail();
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
// 9회 이전 layout — 4·4·5·4. row 2가 5 cell (광주·대전·대구·부산·울산), row 3 4 cell.
//   row 2 col 1 = 광주, col 2 = 대전, col 3 = 대구, col 4 = 부산, col 5 = 울산
//   row 3 col 1 = 전남, col 2 = 전북, col 3 = 경남, col 4 = 제주 (col 1·2 lon 순서)
// parties.js 9회 active (부산·울산 swap, 전북 col 1)를 옛 layout으로 override.
const SIDO_HEX_LAYOUT_LEGACY = {
  '광주광역시':     { col: 1, row: 2, label: '광주' },
  '부산광역시':     { col: 4, row: 2, label: '부산' },  // 옛: row 2 col 4 (parties.js의 울산 자리)
  '울산광역시':     { col: 5, row: 2, label: '울산' },
  '전라남도':       { col: 1, row: 3, label: '전남' },  // 옛: col 1 (lon 서)
  '전북특별자치도': { col: 2, row: 3, label: '전북' },  // 옛: col 2 (lon 동)
  '전라북도':       { col: 2, row: 3, label: '전북' },
  '경상남도':       { col: 3, row: 3, label: '경남' },
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
  const sidoAbbr = sido ? (SIDO_HEX_LAYOUT[sido]?.label || sido.slice(0, 2)) : '';
  return { prefix: sidoAbbr, short: body, fullName: name };
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

  // 비례대표 — 정당별 한 줄 픽토그램 (한 줄 = 한 정당, hex 1개 = 1석)
  // pointy-top hex를 가로 pitch √3·r로 놓으면 좌우 수직변이 맞닿아 빈틈 없이 이어짐.
  const propSeats = state.results?.national?.proportional_seats || [];
  if (propSeats.length) {
    const totalProp = propSeats.reduce((s, p) => s + p.seats, 0);
    const totalSeats = layout.length + totalProp;
    const maxSeats = Math.max(...propSeats.map((p) => p.seats));
    const seatR = 13;                          // 비례 seat hex 반지름 (지역구보다 작게)
    const seatPitch = seatR * Math.sqrt(3);    // 같은 줄 가로 간격 (= hex 폭, snug)
    const rowGap = seatR * 2 + 7;              // 정당 줄 간격
    const labelRight = 96;                     // 정당명 우측 정렬 기준 x
    const hexStartX = labelRight + 14 + seatR; // 첫 hex 중심 x
    const margin = rowH * 1.1;
    const headerY = h + margin;                // 섹션 헤더 baseline
    const firstRowY = headerY + seatR + 16;    // 첫 정당 줄 중심 y

    // 헤더
    const sectionLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    sectionLabel.setAttribute('x', 10);
    sectionLabel.setAttribute('y', headerY);
    sectionLabel.setAttribute('font-size', '12');
    sectionLabel.setAttribute('font-weight', '700');
    sectionLabel.setAttribute('fill', '#0a0e1a');
    sectionLabel.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
    sectionLabel.textContent = `비례대표 ${totalProp}석 · 총 ${totalSeats}석`;
    svg.appendChild(sectionLabel);

    // 정당별 한 줄 (의석 많은 순)
    [...propSeats].sort((a, b) => b.seats - a.seats).forEach((ps, pi) => {
      const color = partyColor(ps.party);
      const cy = firstRowY + pi * rowGap;
      // 정당명 (우측 정렬, 줄 중앙)
      const nm = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      nm.setAttribute('x', labelRight);
      nm.setAttribute('y', cy + 4);
      nm.setAttribute('text-anchor', 'end');
      nm.setAttribute('font-size', '11');
      nm.setAttribute('font-weight', '700');
      nm.setAttribute('fill', color);
      nm.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      nm.textContent = ps.party;
      svg.appendChild(nm);
      // 의석 hex들
      for (let i = 0; i < ps.seats; i++) {
        const cx = hexStartX + i * seatPitch;
        const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        poly.setAttribute('points', hexPoints(cx, cy, seatR - 0.7));
        poly.setAttribute('fill', color);
        poly.setAttribute('stroke', '#fff');
        poly.setAttribute('stroke-width', '1');
        const tt = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        tt.textContent = `비례 ${ps.party} ${i + 1}/${ps.seats}석`;
        poly.appendChild(tt);
        svg.appendChild(poly);
      }
      // 의석 수 (hex 줄 우측 끝)
      const cnt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      cnt.setAttribute('x', hexStartX + (ps.seats - 1) * seatPitch + seatR + 8);
      cnt.setAttribute('y', cy + 4);
      cnt.setAttribute('text-anchor', 'start');
      cnt.setAttribute('font-size', '11');
      cnt.setAttribute('font-weight', '700');
      cnt.setAttribute('fill', color);
      cnt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      cnt.textContent = ps.seats;
      svg.appendChild(cnt);
    });

    // viewBox 확장 (가장 긴 줄 + 의석수 라벨까지)
    const contentW = hexStartX + (maxSeats - 1) * seatPitch + seatR + 36;
    const newH = firstRowY + propSeats.length * rowGap + seatR;
    svg.setAttribute('viewBox', `0 0 ${Math.ceil(Math.max(w, contentW))} ${Math.ceil(newH)}`);
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

  // 격자 hex 모드: 시군구당 N개 작은 hex 패킹
  if (sizingMode === '격자' && maxVoted > 0) {
    const unit = Math.max(20000, Math.round(maxVoted / 14));  // 시군구 최대 ~14개 hex
    const smallR = 5;
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
      svg.appendChild(g);
    }
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

  // 시도 경계 굵은 선 + 한반도 외곽 — 동일 모드에서만 (다른 모드는 hex 크기/위치 달라 경계 불일치)
  if (sizingMode !== '동일') return;
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
    html += `<div class="national-summary">
      <div class="ns-title">${TYPE_LABEL[state.type].ko} ${state.n}회 · ${state.office}</div>
      <div class="ns-name">${el?.date || ''}</div>
      <div class="ns-party">${state.office === '광역단체장' ? '17개 시·도지사 선거' :
                              state.office === '교육감' ? '17개 시·도교육감 선거' :
                              '각 시군구의 단체장 선거'}</div>
      <div class="ns-stat">
        <span>투표율 ${turnoutLabel(nat?.turnout, el)}</span>
      </div>
    </div>`;
  } else if (nat?.candidates?.length) {
    const top = nat.candidates[0];
    const color = partyColor(top.party);
    html += `<div class="national-summary" style="border-left-color:${color}">
      <div class="ns-title">${TYPE_LABEL[state.type].ko} ${state.n}회 · 전국</div>
      <div class="ns-name" style="color:${color}">${candLabel(top) || el?.winner || '—'}</div>
      <div class="ns-party">${top.party} · ${top.pct?.toFixed(1)}%</div>
      <div class="ns-stat">
        <span>투표율 ${turnoutLabel(nat?.turnout, el)}</span>
        ${el?.date ? `<span>${el.date}</span>` : ''}
      </div>
    </div>`;
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
