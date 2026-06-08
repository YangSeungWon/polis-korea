// 한국 주요 정당 색 매핑 — 공식 또는 관례.
// 데이터 출처: 각 정당 공식 로고, 위키백과 정당별 색.
const PARTY_COLORS = {
  // ko.wiki '틀:정당색/대한민국' + namu.wiki infobox 양쪽 cross-check.
  // 시대별 색 변천은 PARTY_COLOR_PERIODS로 보정.
  '더불어민주당':     '#003B96',  // ko·namu 일치 — 네이비
  '더불어민주연합':   '#003B96',  // 22대 위성 (모당과 동일)
  '더불어시민당':     '#004EA2',  // 21대 위성 — ko.wiki 별도 값
  '열린민주당':       '#003E9B',  // 21대
  '민주당':           '#003B96',  // 5회 지선(2010) 등 시대별 다른 색은 PERIODS
  '새천년민주당':     '#00AA7B',  // 16대 — 청록 (당시 공식)
  '새정치국민회의':   '#009A44',  // 15대 — 녹색 (당시 공식)
  '평화민주당':       '#FADA5E',  // 13대 — 옅은 노랑 (DJ당, ko·namu 일치)
  '통일민주당':       '#1A6AC0',  // 13대 (YS당) — ko·namu 충돌, 잠정 유지
  '민주통합당':       '#FFD504',  // 19대 총선 — 노랑 (namu.wiki)
  '대통합민주신당':   '#FF7F00',  // 17대 대선 — 주황
  '통합민주당':       '#419639',  // 2008-02 손학규 통합민주당 — 18대 총선 81석. namu #419639 초록
  '열린우리당':       '#FFD700',  // 17대 총선 — 노랑 (ko.wiki 공식)
  '새정치민주연합':   '#0082CD',  // 20대 총선 직전
  '국민의힘':         '#E61E2B',
  '국민의미래':       '#E4002B',  // 22대 위성 (ko.wiki)
  '미래통합당':       '#EF426F',  // 21대 — 핫핑크 (당시 공식 PI, ko·namu 일치)
  '미래한국당':       '#EF426F',  // 21대 위성 (미래통합당과 동일)
  '자유한국당':       '#C9151E',  // 20대 대선 — 진한 빨강
  '새누리당':         '#C9252B',  // 18·19·20대
  '한나라당':         '#0095DA',  // 2004~ 하늘색 (1997~2004 짙은 남색은 PERIODS)
  '민주자유당':       '#003990',  // 14대
  '민주정의당':       '#0A84E9',  // 13대 — 청 (ko.wiki)
  '자유민주연합':     '#1B5B40',  // 자민련 (JP)
  '자민련':           '#1B5B40',
  '신민주공화당':     '#59955E',  // 13대 (JP)
  '통일국민당':       '#22B14C',  // 14대 (정주영)
  '국민신당':         '#336C77',  // 15대 (이인제)
  '신민당':           '#DC352A',  // 구 야당
  '통합진보당':       '#782B90',  // 19대 — 보라
  '조국혁신당':       '#06275E',
  '자유와혁신':       '#A50034',  // 황교안 — 2026 창당
  '개혁신당':         '#FF7210',
  '진보당':           '#D6001C',
  '진보신당':         '#E62020',  // 18-19대 — 빨강 (ko·namu 일치, 옛 #FF7A05 주황은 오류)
  '친박연대':         '#0C449B',  // 18대 — 남색 (옛 노랑 #FFC107는 명백 오류)
  '녹색정의당':       '#FFED00',
  '정의당':           '#FFED00',
  '민주노동당':       '#EE7700',  // 위키 #EE7700 주황 (1차 2000-01 ~ 2차 2011-12 통진당 합류)
  '창조한국당':       '#84BC34',
  '기본소득당':       '#00D2C3',  // 터쿼이즈
  '노동당':           '#D71920',
  '새로운미래':       '#1A6AC0',
  '자유통일당':       '#1B5198',
  '공화당':           '#3F8FCB',
  '국민당':           '#FF6699',
  '국민의당':         '#006241',  // 안철수 — People Green
  '바른미래당':       '#00B4B4',  // 21대 — 민트
  '국민통합21':       '#003399',  // 16대 (정몽준) — 네이비
  '민중당':           '#A5132F',
  '민생당':           '#00A85F',  // 21대 비례 (구 평화당 등 통합) — 민생그린
  '대한애국당':       '#3399FF',
  '녹색당':           '#7FBE26',
  '소나무당':         '#5DA532',
  '국가혁명당':       '#FFD700',
  '국가혁명배당금당': '#FFD700',  // 21대 (허경영)
  '자유선진당':       '#00529C',

  // === 보수 계열 ===
  '친박연합':         '#C9151E',  // 19대 총선 비례 친박
  '친박신당':         '#C9151E',  // 21대 (홍문종)
  '한나라당계열':     '#0095DA',
  '국민대통합당':     '#E61E2B',  // 19대 대선 (장성민)
  '늘푸른한국당':     '#7B7BD8',  // 19대 대선 (이재오)
  '경제애국당':       '#C9151E',  // 19대 대선 (오영국)
  '대한민국당':       '#3F8FCB',
  '대한당':           '#C9151E',
  '한국국민당':       '#C9151E',
  '혹익당':           '#888888',  // 19대 대선
  '홍익당':           '#FFD700',  // 21·22대
  '자유당':           '#5A6E9C',
  '바른정당':         '#00B1EB',  // 19·20대 (유승민) — 스카이블루

  // === 진보·노동 계열 ===
  '한국사회당':       '#D71920',  // 16·17·18대 진보
  '사회당':           '#D71920',
  '진보당계열':       '#D6001C',
  '민중연합당':       '#A5132F',  // 20대 (구 통진당 후신)
  '코리아':           '#FFCD00',  // 20대 (정의당 위성)
  '깨어있는시민연대당': '#7B68C5',
  '미래민주당':       '#1A6AC0',
  '국민새정당':       '#FFD700',
  '국민참여신당':     '#7B68C5',
  '새벽당':           '#7B68C5',

  // === 기독·종교 계열 ===
  '기독당':           '#1B5198',  // 17·18·19·20대 (기독사랑실천당 등)
  '기독자유당':       '#1B5198',  // 20대
  '기독자유민주당':   '#1B5198',
  '기독자유통일당':   '#1B5198',  // 21대
  '불교당':           '#FFC107',
  '불교연합당':       '#FFC107',
  '대한국당':         '#7B68C5',

  // === 여성·성평등·인권 ===
  '여성의당':         '#E63B7A',
  '일제.위안부.인권정당': '#E63B7A',

  // === 통일·평화 ===
  '통일한국당':       '#1763B6',
  '남북통일당':       '#1763B6',
  '평화통일당':       '#1763B6',
  '가자!평화인권당':  '#10A66E',

  // === 청년·실용·기타 ===
  '미래연합':         '#5A6E9C',  // 19대 비례
  '미래당':           '#1A6AC0',
  '한국복지당':       '#10A66E',
  '복지국가당':       '#10A66E',
  '고용복지연금선진화연대': '#10A66E',
  '한국경제당':       '#3F8FCB',
  '자영업당':         '#FF7A05',
  '한류연합당':       '#FF7A05',
  '국민새시대':       '#FFD700',
  '새정치국민의당':   '#01A14B',
  '한국국민당계':     '#3F8FCB',
  '개혁국민신당':     '#FF7A05',
  '친반통일당':       '#1763B6',
  '가자환경당':       '#7FBE26',

  // === 폴백 ===
  '무소속':           '#888888',
};

const PARTY_FALLBACK = '#777777';

// 같은 당명이라도 시대에 따라 공식 브랜드 색이 달랐던 케이스 override.
// from(inclusive) ≤ date < to(exclusive). 매칭되면 PARTY_COLORS보다 우선.
// 추가 시: 위키백과 정당별 entry의 공식 색·로고 확인.
const PARTY_COLOR_PERIODS = {
  '민주당': [
    // 2008-02 ~ 2011-12 통합민주당 → 민주당 (정통민주당) — 초록 #00AA7B.
    // 2010 5회 지선이 이 시기. 현행 더불어민주당 파랑과 다름.
    { from: '2008-02-17', to: '2011-12-23', color: '#00AA7B' },
  ],
  '한나라당': [
    // 1997-11 창당 ~ 2004: 짙은 남색 #0000A8 (namu.wiki). 2004 이후는 default 하늘색 #0095DA.
    { from: '1997-11-21', to: '2004-03-23', color: '#0000A8' },
  ],
};

// 메트릭(국정평가·투표의향) 카테고리 색
const METRIC_COLORS = {
  '긍정평가':     '#2e7d6f',  // 청록 (찬성·긍정)
  '부정평가':     '#c8553d',  // 주홍 (부정)
  '투표함':       '#5a6e9c',  // 청람 (참여)
  '투표안함':     '#999999',  // 회색 (불참)
  '모름/무응답':  '#bbbbbb',  // 옅은 회색
};

// 9회 지선 주요 출마 정당 — 범례에 항상 노출. 1위 안 잡혀도 색 안내용.
const LEGEND_DEFAULT_PARTIES = [
  '더불어민주당', '국민의힘', '조국혁신당', '개혁신당', '진보당', '무소속',
];

// 페이지가 표시하는 회차 날짜 — archive/history 등에서 1회 set 후 모든 render가 동일 시점.
// 명시 date 인자가 더 우선 (timeline 같은 다회차 페이지용).
let _partyColorContextDate = null;
function setPartyColorContext(date) { _partyColorContextDate = date || null; }

function partyColor(party, date) {
  if (!party) return PARTY_FALLBACK;
  if (METRIC_COLORS[party]) return METRIC_COLORS[party];
  // 시대 override — date 인자 → context date 순. YYYY-MM-DD.
  const effDate = date || _partyColorContextDate;
  if (effDate && PARTY_COLOR_PERIODS[party]) {
    for (const p of PARTY_COLOR_PERIODS[party]) {
      if (effDate >= p.from && effDate < p.to) return p.color;
    }
  }
  if (PARTY_COLORS[party]) return PARTY_COLORS[party];
  // 부분 매칭 (e.g., "더불어민주당 OO지부")
  for (const k of Object.keys(PARTY_COLORS)) {
    if (party.includes(k) || k.includes(party)) return PARTY_COLORS[k];
  }
  return PARTY_FALLBACK;
}

// 글씨 색 — fill에 적합한 회색이 글씨로 쓰이면 흰 배경에서 잘 안 보임. 무소속 등 회색계만 더 진하게.
const PARTY_TEXT_OVERRIDE = {
  '무소속': '#4a4a4a',
};
function partyTextColor(party) {
  if (party && PARTY_TEXT_OVERRIDE[party]) return PARTY_TEXT_OVERRIDE[party];
  const c = partyColor(party);
  if (c === PARTY_FALLBACK) return '#4a4a4a';  // 매칭 안 된 회색 fallback도 글씨용 진하게
  return c;
}

// hex/cell 배경색 위에 글씨 색 자동 결정. YIQ 공식 — 밝으면 검정, 어두우면 흰색.
// fillOpacity가 낮으면 페이지 배경(라이트=흰·다크=어두움)에 blend되어 실제 보이는 색이 옅어지므로 그것도 반영.
function _detectDarkTheme() {
  try {
    const root = document.documentElement;
    if (root.getAttribute('data-theme') === 'dark') return true;
    if (root.getAttribute('data-theme') === 'light') return false;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  } catch (e) { return false; }
}
function pickTextColor(bgHex, fillOpacity = 1) {
  const c = (bgHex || '#ffffff').replace('#', '');
  if (c.length < 6) return '#0a0e1a';
  let r = parseInt(c.substr(0, 2), 16);
  let g = parseInt(c.substr(2, 2), 16);
  let b = parseInt(c.substr(4, 2), 16);
  const isDark = _detectDarkTheme();
  const bgR = isDark ? 13 : 255, bgG = isDark ? 16 : 255, bgB = isDark ? 24 : 255;
  if (fillOpacity < 1) {
    r = Math.round(r * fillOpacity + bgR * (1 - fillOpacity));
    g = Math.round(g * fillOpacity + bgG * (1 - fillOpacity));
    b = Math.round(b * fillOpacity + bgB * (1 - fillOpacity));
  }
  const yiq = (r * 299 + g * 587 + b * 114) / 1000;
  // 다크 테마는 텍스트 흰/검 임계점도 더 낮게 (텍스트는 어차피 다크에선 밝아야)
  const threshold = isDark ? 130 : 165;
  return yiq >= threshold ? (isDark ? '#0a0e1a' : '#0a0e1a') : '#fff';
}

// 격차(%p)에 따른 opacity. 박빙일수록 연하게.
//   0p (박빙) → 0.55
//   5p        → 0.73
//   10p       → 0.84
//   20p+ (압도) → 0.95
function gapOpacity(gap) {
  if (gap == null || isNaN(gap)) return 0.8;
  const a = 0.55 + 0.45 * (1 - Math.exp(-Math.abs(gap) / 10));
  return Math.max(0.5, Math.min(1, a));
}

// 17 시도 hex 격자 — pointy-top, odd-row 오른쪽 offset.
// 9회 active layout: 5 row 4·4·4·3·1 (16 cell 빈자리 0). 한국 지도 모양 + lat·lon 정확.
//   row 0:  [인천][서울][경기][강원]                  (4) — 수도권·강원
//   row 1:    [충남][세종][충북][경북]                (4) — 중부 (충청·경북)
//   row 2:    [전북][대전][대구][울산]                (4) — 광역시 동측 cluster + 전북
//   row 3:  [전남광주][경남][부산]                    (3) — 호남·영남 남부
//   row 4:    [제주]                                  (1) — 제주 단독
// 옛 시점 (history.js LEGACY override): row 2 5 cell (광주 추가), row 3 (전남·경남·부산).
const SIDO_HEX_LAYOUT = {
  '인천광역시':     { col: 1, row: 0, label: '인천' },
  '서울특별시':     { col: 2, row: 0, label: '서울' },
  '경기도':         { col: 3, row: 0, label: '경기' },
  '강원특별자치도': { col: 4, row: 0, label: '강원' },

  '충청남도':       { col: 1, row: 1, label: '충남' },
  '세종특별자치시': { col: 2, row: 1, label: '세종' },
  '충청북도':       { col: 3, row: 1, label: '충북' },
  '경상북도':       { col: 4, row: 1, label: '경북' },

  '전북특별자치도': { col: 2, row: 2, label: '전북' },
  '전라북도':       { col: 2, row: 2, label: '전북' },  // 옛 이름 alias
  '대전광역시':     { col: 3, row: 2, label: '대전' },
  '대구광역시':     { col: 4, row: 2, label: '대구' },
  '울산광역시':     { col: 5, row: 2, label: '울산' },

  '전남광주특별시': { col: 1, row: 3, label: '전남광주' },
  '경상남도':       { col: 2, row: 3, label: '경남' },
  '부산광역시':     { col: 3, row: 3, label: '부산' },

  '제주특별자치도': { col: 2, row: 4, label: '제주' },
};

const SIDO_HEX_BLANKS = [];

// === SATELLITE_TO_MAIN auto-generated ===
// data/parties/satellites.json에서 sync. 손으로 수정하지 말 것 —
// scripts/build/sync_satellites_js.py 재실행으로 갱신.
const SATELLITE_TO_MAIN = {
  '미래한국당': '미래통합당',
  '더불어시민당': '더불어민주당',
  '국민의미래': '국민의힘',
  '더불어민주연합': '더불어민주당',
};
const mainParty = (p) => SATELLITE_TO_MAIN[p] || p;
// === /SATELLITE_TO_MAIN ===
