// history.js data access — activeOfficeData · 시군구 결과 lookup · 라벨 helper.
// render-* 가 의존. core 다음에 로드.

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
// 시도 통합(전남·광주 → 전남광주특별시)은 assets/regions.js의 전역 SIDO_MERGE 재사용
// (polls 코드도 동일 전역 사용). 분리된 광주/전남 조회 시 통합 시도 결과 broadcast 용도 — resultForSido.
// 행정구역 변경 — hex name → 데이터 name 후보들 (list).
const SIGUNGU_NAME_HISTORY = {
  '세종시':         ['세종특별자치시', '연기군'],  // 데이터 name 형식 차이 + 옛 충남 연기군
  '당진시':         ['당진군'],          // 2012 시 승격 전 (5회)
  '여주시':         ['여주군'],          // 2013 시 승격 전 (5회)
  '청주시청원구':   ['청원군'],          // 2014.7 통합 전 (5/6회)
  '미추홀구':       ['남구'],            // 인천 2018 개명 전 (5/6/7회 → '남구')
  '남구':           ['미추홀구'],        // 인천 — hex가 옛 vuski GeoJSON '남구', 8회+ 데이터엔 '미추홀구'
};
// 시군구 hex cell lifecycle — 등장(since)/폐지(until) 시점 + 이전·이후 대체 이름.
// since: 이 날짜 이전 회차 → cell hide (신설), beforeAs 있으면 옛 행정구역 이름으로 표시.
// until: 이 날짜 이후 회차 → cell hide (폐지), afterAs 있으면 새 이름으로 표시.
// beforeAs/afterAs: { sido, name } — 그 시점 행정구역 alias. 데이터 매칭 + 라벨 모두 적용.
// 추가 패턴:
//   '시도명|시군구명': { since: 'YYYY-MM-DD', beforeAs: { sido, name } }
//   '시도명|시군구명': { until: 'YYYY-MM-DD', afterAs: { sido, name } }
// sido 이동(군위군 경북→대구 2023-07)은 SIGUNGU_SIDO_HISTORY로 처리 — 별도.
const SIGUNGU_HEX_LIFECYCLE = {
  // 세종 2012-07-01 신설 — 그 전엔 충남 연기군. 5회 시점엔 연기군으로 표시.
  '세종특별자치시|세종시': {
    since: '2012-07-01',
    beforeAs: { sido: '충청남도', name: '연기군' },
  },
  // 인천 2026-07-01 신설 — 남구 분할 → 검단·제물포구, 중구 일부 → 영종구.
  '인천광역시|검단구':   { since: '2026-07-01' },
  '인천광역시|영종구':   { since: '2026-07-01' },
  '인천광역시|제물포구': { since: '2026-07-01' },
};

// cell의 회차 시점 effective 정보 — null이면 hide, 객체면 {sido, name} 그 시점 행정구역.
function effectiveCell(d, electionDate) {
  if (!electionDate) return { sido: d.sido, name: d.name };
  const lc = SIGUNGU_HEX_LIFECYCLE[`${d.sido}|${d.name}`];
  if (!lc) return { sido: d.sido, name: d.name };
  if (lc.since && electionDate < lc.since) {
    return lc.beforeAs ? { sido: lc.beforeAs.sido, name: lc.beforeAs.name } : null;
  }
  if (lc.until && electionDate >= lc.until) {
    return lc.afterAs ? { sido: lc.afterAs.sido, name: lc.afterAs.name } : null;
  }
  return { sido: d.sido, name: d.name };
}
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
  // 데이터 sigungu='세종특별자치시' (시도와 동일) → hex '세종시' 매칭.
  // 2012 출범 전(16·17대 등)엔 세종 = 옛 충남 연기군 → 그쪽으로 fallback.
  if (name === '세종시' && sido === '세종특별자치시') {
    const r = data.sigungu.find((rr) => rr.sido === '세종특별자치시')
      || data.sigungu.find((rr) => canonSido(rr.sido) === '충청남도' && rr.name === '연기군');
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

// 지역구 결과 (총선만). 양쪽 canonSido — geo 클릭이 저장한 raw '강원도'가 데이터 canon과 매칭.
function resultForDistrict(sido, name) {
  if (!state.results?.district) return null;
  return state.results.district.find((r) => canonSido(r.sido) === canonSido(sido) && r.name === name) || null;
}

// 시도 단위 합산 — 시군구 결과를 시도별 합산해서 1위 정당 결정
function resultForSido(sido) {
  const data = activeOfficeData();
  if (!data?.sigungu) return null;
  // 양쪽 정규화 — layout key가 옛 명칭('강원도')이어도 데이터('강원도'→canon '강원특별자치도')와 매칭.
  let matched = data.sigungu.filter((r) => canonSido(r.sido) === canonSido(sido));
  // 통합 시도 fallback — 광주/전남 분리 조회인데 데이터는 전남광주특별시 병합(9회). regions.js 전역.
  if (!matched.length && typeof SIDO_MERGE !== 'undefined' && SIDO_MERGE[sido]) {
    matched = data.sigungu.filter((r) => canonSido(r.sido) === SIDO_MERGE[sido]);
  }
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
  // 이미 시도 단위 행(name 비어있음 = 광역장·교육감)이면 합산·재계산 불필요 — 저장된 pct 사용.
  //   1~4회 광역장은 당선자 1명만 저장(+votes 깨짐)이라 votes 합산 재계산 시 100%로 잘못 나옴.
  //   5회+ 는 votes가 실제라 재계산해도 같지만, 일관되게 저장 pct를 그대로 쓴다.
  //   (기초장 fallback은 시군구별 행이라 name이 있어 이 분기를 안 타고 정상 합산.)
  if (matched.every((r) => !r.name)) {
    const r0 = matched[0];
    const candidates = matched.flatMap((r) => r.candidates || [])
      .slice().sort((a, b) => (b.pct || 0) - (a.pct || 0));
    return { sido, electors: r0.electors, voted: r0.voted, turnout: r0.turnout, candidates };
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
