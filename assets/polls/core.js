// polls.js core — ELECTION 상수 · state · 카운트다운 · 데이터 로드 · region/office lookup.
// 다른 모듈이 의존하는 기반.

// 9회 지선 여론조사 페이지 메인 스크립트.
// 데이터: data/polls/aggregated.json (build_polls.py 산출물).
// 의존: regions.js, parties.js, utils.js, Leaflet.

// 선거 메타 — 정적 prerender(build_static)가 per-election 페이지에 __INITIAL_STATE__.election 주입.
// 주입 없으면(루트 /polls.html·office 서브페이지) 9회 지선 기본값.
const POLL_ELECTION = Object.assign({
  slug: '9th-local-2026',
  name: '9회 전국동시지방선거',
  date: '2026-06-03',
  blackout_start: '2026-05-28T00:00:00+09:00',
  blackout_end: '2026-06-03T18:00:00+09:00',
  polls_path: 'data/polls/aggregated.json',
  results_path: 'data/results/9th-local-2026.json',
  roster_path: 'data/raw/nec_roster_9th.json',
  kind: 'local',
}, ((typeof window !== 'undefined' && window.__INITIAL_STATE__ && window.__INITIAL_STATE__.election) || {}));

const ELECTION = new Date(POLL_ELECTION.date + 'T00:00:00+09:00');
const ELECTION_NAME = POLL_ELECTION.name;
const BLACKOUT_START = new Date(POLL_ELECTION.blackout_start);
const BLACKOUT_END = new Date(POLL_ELECTION.blackout_end);

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
  // 선거 후 1주까지만 "선거 후 N일"(개표 직후 맥락), 그 뒤엔 정적 "선거 종료"(카운터가 계속
  // 커지며 낡아 보이는 것 방지 — 결과 동선은 아래 post-election-banner가 담당).
  $('#countdown').textContent = days > 0 ? `선거 D-${days}`
    : days === 0 ? '선거 당일'
    : days >= -7 ? `선거 후 ${-days}일`
    : '선거 종료';
  $('#countdown').classList.toggle('is-ended', days < -7);  // 종료 후엔 muted(덜 중요)
  // 블랙아웃 판정
  state.blackoutActive = now >= BLACKOUT_START && now < BLACKOUT_END;
  $('#blackout-tag').hidden = !state.blackoutActive;
  $('#legal-banner').hidden = !state.blackoutActive;
}

// 페이지 성격을 선거일 기준 자동 전환 — 폴링 중="여론조사", 선거 후="여론 vs 실제" 회고.
// 하드코딩 대신 날짜 기반이라 다음 선거로 갈아타도(ELECTION/ELECTION_NAME만 갱신) 자동 적용.
const POLL_SEASON_DAYS = 180;   // 선거 N일 전부터 = 활성 폴링 시즌(전면 승격)
function setPhase() {
  const now = new Date();
  const post = now >= ELECTION;
  const h1 = $('#poll-h1'), lede = $('#poll-lede'), banner = $('#post-banner');
  if (h1) h1.textContent = post ? `${ELECTION_NAME} · 여론조사 vs 실제` : `${ELECTION_NAME} 여론조사`;
  if (lede) lede.textContent = post
    ? 'NESDC 등록 조사 vs 실제 결과 — 여론조사가 얼마나 맞았는지. 셀 색=1위 정당.'
    : 'NESDC 등록 조사. 셀 색=마지막 조사 1위 정당.';
  if (banner) banner.hidden = !post;
  // post-banner 날짜·결과링크를 회차별로 (정적 마크업은 9회 기본 — per-election 페이지에서 교체)
  const pebTag = banner && banner.querySelector('.peb-tag');
  const pebLink = banner && banner.querySelector('.peb-link');
  if (pebTag) pebTag.textContent = POLL_ELECTION.date;
  if (pebLink) pebLink.href = `/archive/${POLL_ELECTION.slug}/`;

  // 활성 폴링 시즌이면 그 선거를 상단 전면 배너로 승격(사람 몰리는 선거를 끌어올림).
  const seasonStart = new Date(ELECTION);
  seasonStart.setDate(seasonStart.getDate() - POLL_SEASON_DAYS);
  const polling = now >= seasonStart && now < ELECTION;
  const apb = $('#active-poll-banner');
  if (apb) {
    apb.hidden = !polling;
    if (polling) {
      const days = Math.ceil((ELECTION - now) / 86400000);
      apb.innerHTML = `<span class="apb-dot"></span>`
        + `<b>${ELECTION_NAME} 여론조사 진행 중</b>`
        + `<span class="apb-dday">D-${days}</span>`
        + `<span class="apb-go">상세 보기 ↓</span>`;
    }
  }
}

async function loadData() {
  try {
    const r = await fetch(POLL_ELECTION.polls_path);
    if (!r.ok) throw new Error('데이터 없음');
    state.data = await r.json();
  } catch (e) {
    state.data = { _meta: {}, polls: [] };
  }
  // NEC 등록 후보 명부 (있으면 산점도에 진한/옅은 구분). 경로 없는 회차는 생략.
  state.roster = null;
  if (POLL_ELECTION.roster_path) {
    try {
      const r = await fetch(POLL_ELECTION.roster_path);
      state.roster = r.ok ? await r.json() : null;
    } catch (e) {
      state.roster = null;
    }
  }
  // 블랙아웃이면 공표금지 시작일 이전 조사만 노출
  if (state.blackoutActive) {
    const cutoff = POLL_ELECTION.blackout_start.slice(0, 10);
    state.data.polls = state.data.polls.filter((p) => {
      if (!p.period_end) return false;
      return p.period_end < cutoff;
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
  let r = summarizeLatest(pollsByOffice(office).filter((p) => p.sido === sido && !p.sigungu));
  // 분리 시도(광주·전남)로 못 찾으면 통합키(전남광주특별시)로 — 2026 지선 통합 대응.
  if (!r && typeof SIDO_MERGE !== 'undefined' && SIDO_MERGE[sido]) {
    r = summarizeLatest(pollsByOffice(office).filter((p) => p.sido === SIDO_MERGE[sido] && !p.sigungu));
  }
  return r;
}

// 시군구 단위 — 기초단체장은 office_level='기초단체장', 그외 메트릭(정당지지/국정평가/투표의향)은
// office_level이 메트릭 자체. sigungu 필드가 있는 polls만 사용.
// 일반구 → 모도시 매핑 (통합 도시 기초단체장은 시장 1명. 수원시장안구 → 수원시)
function parentSigungu(sigungu) {
  if (!sigungu) return null;
  const m = sigungu.match(/^([가-힣]+시)[가-힣]+구$/);
  return m ? m[1] : null;
}

function sigunguLastWinningParty(sido, sigungu, office = '기초단체장') {
  const polls = pollsByOffice(office).filter(
    (p) => p.sido === sido && p.sigungu === sigungu
  );
  if (polls.length) return summarizeLatest(polls);
  // 일반구라면 모도시(통합도시) polls로 fallback
  const parent = parentSigungu(sigungu);
  if (parent) {
    return summarizeLatest(pollsByOffice(office).filter(
      (p) => p.sido === sido && p.sigungu === parent
    ));
  }
  return null;
}

