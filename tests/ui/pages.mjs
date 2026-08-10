// 대표 페이지 매트릭스 — 4,900개를 다 볼 필요는 없다. 서로 다른 실패 양식을 가진
// 화면만 고정해 계속 같은 걸 본다. 새 페이지 유형이 생기면 여기 추가한다.
//
// why: 각 항목이 '무엇을 대표하는가'를 적어 둔다. 대표성이 없으면 그냥 스크린샷 더미다.
export const PAGES = [
  { id: 'home',          url: '/',                                why: '홈 라우터' },
  { id: 'elections',     url: '/elections.html',                  why: '긴 목록 허브' },
  { id: 'archive-local', url: '/archive/9th-local-2026/',         why: '가장 복잡한 archive(7직위·hex 다수)' },
  { id: 'archive-pres',  url: '/archive/21st-pres-2025/',         why: '대선 — 지도·격자·여론·출구조사' },
  { id: 'archive-gen',   url: '/archive/22nd-general-2024/',      why: '총선 — 선거구 254개' },
  { id: 'archive-cmp',   url: '/archive/6th-local-2014/',         why: '비교 — 개명 보정(한나라당→새누리당)이 걸린 회차' },
  { id: 'archive-old',   url: '/archive/2nd-pres-1952/',          why: '데이터 빈약한 옛 회차(결손 표기)' },
  { id: 'archive-by',    url: '/archive/byelection-2025-04-02/',  why: '재보궐 — 다른 구조' },
  { id: 'polls',         url: '/polls.html',                      why: '인터랙티브 stress(토글 다수)' },
  { id: 'poll-round',    url: '/polls/9th-local-2026/',           why: '회차별 조사 vs 실제' },
  { id: 'history',       url: '/history.html',                    why: '지도/격자/원형 토글 stress' },
  { id: 'chronology',    url: '/chronology.html',                 why: '연표 — 1948~2026 시간 밀도' },
  { id: 'history-local',  url: '/history/local/9/governor/',       why: '지선 직위 뷰 — 가로 flex .viz(범례가 컬럼이 되던 자리) + 직위별 집계 단위' },
  { id: 'parties',       url: '/parties.html',                    why: '정당사 SVG stress(2020년대 밀집)' },
  { id: 'party-big',     url: '/party/국민의힘/',                 why: '큰 정당 — 인물 many' },
  { id: 'party-small',   url: '/party/노동당/',                   why: '작은 정당 — 빈 섹션' },
  { id: 'person',        url: '/person/이재명-1964-12-22/',       why: '인물 — 공약·이력' },
  { id: 'region-long',   url: '/region/경상북도-김천시/',         why: '긴 지역 기록(결손 표기 포함)' },
  { id: 'region-short',  url: '/region/경상북도-경주군/',         why: '데이터 3건 — 빈약한 entity' },
  { id: 'region-hub',    url: '/region/',                         why: '366개 칩 밀도' },
  { id: 'byelection',    url: '/byelection.html',                 why: '지도(leaflet) + 키' },
  { id: 'tracker',       url: '/tracker.html',                    why: '시계열' },
  { id: 'search',        url: '/search.html',                     why: '검색 진입' },
  { id: 'coverage',      url: '/about/data-coverage/',            why: '자료 출처 매트릭스 — 추정 금지 자리' },
];

// 뷰포트 — 초대형과 모바일 사이가 가장 잘 깨진다.
export const VIEWPORTS = [
  { id: 'desktop', width: 1366, height: 900 },
  { id: 'laptop',  width: 1024, height: 768 },
  { id: 'mobile',  width: 390,  height: 844 },
];
