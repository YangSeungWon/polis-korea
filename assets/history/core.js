// history.js core — state · 헬퍼 · 새 schema adapter · URL routing/setters.
// 다른 모듈이 의존하는 기반. 가장 먼저 로드.

// 역대 선거 결과 페이지 — polis.ysw.kr/history
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
    is_uncontested: race.is_uncontested || false,   // 무투표 당선 플래그 보존
  };
}

function _raceToOldDistrict(race) {
  const cands = race.candidates || [];
  const won = cands.filter((c) => c.won);
  const winner = won[0] || cands[0];
  const out = {
    sido: race.sido,
    name: race.district || '',
    winner: winner?.name || '',
    winner_party: winner?.party || '',
    electors: race.electors || 0,
    voted: race.voters || 0,
    invalid: race.invalid_votes || 0,
    turnout: race.electors ? +(race.voters / race.electors * 100).toFixed(2) : 0,
    candidates: cands,
    is_uncontested: race.is_uncontested || false,   // 무투표 당선 플래그 보존
  };
  // 중선거구(9~12대 1구 2인) — 당선자 2명 보존(의석 카운트·hex 줄무늬용).
  if (won.length >= 2) out.winners = won.map((c) => ({ name: c.name, party: c.party }));
  return out;
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
    // 비례 의석 — _meta 우선, 없으면 비례(7) race candidates의 proportional_seats 집계.
    // (20대 등 새 schema는 nation tc7 candidates에 party별 proportional_seats가 들어있음)
    if (raw._meta?.proportional_seats) {
      out.national.proportional_seats = raw._meta.proportional_seats;
    } else {
      const seatMap = new Map();
      const srcs = nation ? [nation] : sidoProp;
      for (const r of srcs) {
        for (const c of (r.candidates || [])) {
          if ((c.proportional_seats || 0) > 0) {
            seatMap.set(c.party, (seatMap.get(c.party) || 0) + c.proportional_seats);
          }
        }
      }
      if (seatMap.size) {
        out.national.proportional_seats = [...seatMap.entries()].map(([party, seats]) => ({ party, seats }));
      }
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
      const sggRows = races.filter((r) => r.scope === 'sigungu' && r.sg_typecode === tc)
                           .map(_raceToOldRow);
      out.offices[office] = {
        national: _aggSidoToNation(sidoRaces),
        // 시군구 breakdown 있으면 그걸 사용(시도 집계 + 시군구 드릴) — 5~8회.
        // 없으면(옛 1~4회·9회 광역장/교육감은 scope sido만) 시도 행으로 fallback →
        // resultForSido가 시도당 1행을 그대로 집계해 광역장/교육감 시도뷰가 뜬다.
        sigungu: sggRows.length ? sggRows : sidoRaces.map(_raceToOldRow),
      };
    }
  }
  return out;
}

// === URL ↔ state — path-based (prerender 호환, SEO 최적) ===
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

// 대선만 격자 hex 기본(전국 표심을 면적으로 — 1 hex=2만표). 지선·총선은 단일 hex('동일',
// 시군구당 1위 정당색). 대선 sizing-seg는 격자/Dorling만; 지선은 sizing-seg 자체가 숨김.
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
