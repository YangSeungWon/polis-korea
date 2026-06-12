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
  '달성군': ['대구광역시', '경상북도'],  // 1995 대구 편입 전 경북 달성군
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
  '증평군':         ['괴산군'],          // 2003.8 괴산군서 분리 전 (16대 대선 2002 등)
  '계룡시':         ['논산시', '논산군'], // 2003.9 논산서 분리 전
  // 시 승격 전 군명 (13~15대 대선 등). 데이터에 시가 있으면 그게 먼저 매칭, 없으면 옛 군.
  '보령시': ['보령군', '대천시'], '아산시': ['아산군', '온양시'], '김제시': ['김제군'],
  '정읍시': ['정읍군', '정주시'], '익산시': ['이리시', '익산군'], '나주시': ['나주군', '금성시'],
  '남원시': ['남원군'], '광양시': ['광양군', '동광양시'], '화성시': ['화성군'],
  '광주시': ['광주군'], '안성시': ['안성군'], '이천시': ['이천군'], '양산시': ['양산군'],
  '군포시': ['시흥군', '시흥시'], '의왕시': ['시흥군', '시흥시'], '오산시': ['화성군', '화성시'],
  '문경시': ['문경군', '점촌시'],
  '제천시': ['제천군'], '평택시': ['평택군'], '상주시': ['상주군'], '충주시': ['충주군', '중원군'],
  '밀양시': ['밀양군'], '김천시': ['김천군', '금릉군'], '하남시': ['광주군'], '용인시': ['용인군'],
  '성남시': ['광주군'], '구리시': ['양주군'], '영주시': ['영주군'], '구미시': ['선산군'],
  '울주군': ['울산군', '울산시'], '시흥시': ['시흥군'], '안산시': ['시흥군'], '과천시': ['시흥군'],
  '경산시': ['경산군'],
  // 서울 1995 신설구 → 분리 전 모구 (13·14대 대선)
  '강북구': ['도봉구'], '금천구': ['구로구'], '광진구': ['성동구'],
  '광산구': ['광산군'],  // 광주 — 1988 편입 전 전남 광산군
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
  // 인천 2026-07-01 개편 — 중구(육지)+동구→제물포구, 중구 영종도→영종구, 서구 북부→검단구.
  // 그 전 회차(9회 2026-06 포함)는 옛 행정구역으로 표시(beforeAs) — 안 그러면 중구·동구
  // 데이터가 안 뜨고 검단 칸이 내부 구멍이 됨. 영종도=옛 중구, 제물포=옛 동구, 검단=옛 서구.
  '인천광역시|검단구':   { since: '2026-07-01', beforeAs: { sido: '인천광역시', name: '서구' } },
  '인천광역시|영종구':   { since: '2026-07-01', beforeAs: { sido: '인천광역시', name: '중구' } },
  '인천광역시|제물포구': { since: '2026-07-01', beforeAs: { sido: '인천광역시', name: '동구' } },
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

// 모도시/통합시 결과를 그 구 자체 데이터가 없는 셀에 broadcast(차용)할 때 표시.
// 격자 모드는 _fill 셀을 득표비례 N개 대신 단일 색 hex로 그림 — 같은 모도시가
// 미래 구 셀마다 중복 카운트되며 셀 밖으로 넘치는 것 방지.
function fillResult(r) { return r ? { ...r, _fill: true } : r; }

function resultForSigungu(sido, name, data) {
  data = data || activeOfficeData();
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
    const exact = data.sigungu.find((r) => canonSido(r.sido) === sido && r.name === parent);
    if (exact) return fillResult(exact);
    // 모도시 행도 없으면 형제 분구 합산 — 후신설 구(수원영통 2003·청주서원 2014 등)를 그 시점
    // 형제 구 데이터로 채워 구멍 방지. (현대 legacy hex가 옛 대선 회차보다 구가 많아 생기던 빈칸)
    const esc = parent.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const subRe = new RegExp(`^${esc}(?:[가-힣]+(?:구|군)|[갑을병정무])$`);
    const parts = data.sigungu.filter((r) => canonSido(r.sido) === sido && subRe.test(r.name));
    if (parts.length) return fillResult(mergeSigunguResults(parts));
    // 모도시의 옛 군명 (용인시수지구 → 용인시 → 용인군)
    for (const old of (SIGUNGU_NAME_HISTORY[parent] || [])) {
      const r = data.sigungu.find((rr) => canonSido(rr.sido) === sido && rr.name === old);
      if (r) return fillResult(r);
    }
    return null;
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
  // 광역시 자치구(bare 구명) — 옛 회차(구 신설·승격 전)엔 통합 시(또는 시 갑/을구). 데이터 sido는
  // 그 시점 모도(광주직할시 전엔 전남, 부산직할시 전엔 경남 등)라 모도 family로 제한해 동명(경기
  // 광주시 등) 오매칭 차단. '광주광역시 남구'→ 전남 '광주시갑/을구' 합산 broadcast.
  const METRO_FAMILY = {
    '서울특별시': { city: '서울', sidos: ['서울특별시'] },
    '부산광역시': { city: '부산', sidos: ['부산광역시', '부산직할시', '경상남도'] },
    '대구광역시': { city: '대구', sidos: ['대구광역시', '대구직할시', '경상북도'] },
    '인천광역시': { city: '인천', sidos: ['인천광역시', '인천직할시', '경기도'] },
    '광주광역시': { city: '광주', sidos: ['광주광역시', '광주직할시', '전라남도'] },
    '대전광역시': { city: '대전', sidos: ['대전광역시', '대전직할시', '충청남도'] },
    '울산광역시': { city: '울산', sidos: ['울산광역시', '울산시', '경상남도'] },
  };
  const mf = METRO_FAMILY[sido];
  // 울산광역시 울주군 — 옛엔 경남 울산시(군부 별도 데이터 없음) → 울산시로. (강화·옹진·달성 등
  // 다른 광역시 군은 모도 매핑이 따로 있어 bare 구만 일반 처리, 울주군만 명시 포함.)
  if (mf && (/^[가-힣]+구$/.test(name) || (sido === '울산광역시' && name === '울주군'))) {
    // 옛 '시+구' 형식 직접 매칭: '대구광역시 중구' → 경북 '대구시중구'.
    const direct = data.sigungu.find((rr) => mf.sidos.includes(rr.sido) && rr.name === `${mf.city}시${name}`);
    if (direct) return direct;
    // 같은 구의 갑/을/병 분구 합산 우선 — '동대문구' ← '동대문갑구'·'동대문을구' (그 구 자체 데이터, 차용 아님).
    // 모도시 전체 broadcast로 빠지기 전에 자기 선거구 데이터부터 잡음.
    const selfBase = name.replace(/구$/, '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const selfRe = new RegExp(`^${selfBase}[갑을병정무]구$`);
    const selfParts = data.sigungu.filter((rr) => canonSido(rr.sido) === sido && selfRe.test(rr.name));
    if (selfParts.length) return selfParts.length === 1 ? selfParts[0] : mergeSigunguResults(selfParts);
    // 통합시(또는 시 갑/을구) 합산: '광주시', '광주시갑구'.
    const re2 = new RegExp(`^${mf.city}시(?:[갑을병정무]?구)?$`);
    let parts = data.sigungu.filter((rr) => mf.sidos.includes(rr.sido) && re2.test(rr.name));
    if (!parts.length) {
      // 통합시 행 없음 — 그 광역시(또는 모도 sido의 '○○시○구')의 다른 자치구 합산 broadcast.
      // 1988 구 신설 직전(13대 광주 남구·광산구·서울 서초/송파, 대전 유성/대덕 등)을 채워 구멍 방지.
      parts = data.sigungu.filter((rr) =>
        (canonSido(rr.sido) === sido && /^[가-힣]+구$/.test(rr.name) && rr.name !== name)
        || (mf.sidos.includes(rr.sido) && rr.name.startsWith(`${mf.city}시`) && rr.name !== `${mf.city}시${name}`));
    }
    if (parts.length) return fillResult(parts.length === 1 ? parts[0] : mergeSigunguResults(parts));
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
