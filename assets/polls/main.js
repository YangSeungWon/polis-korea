// polls.js entry — setOffice/setScope · seg fades · init.
// 마지막에 로드 + init() 호출.

function setOffice(o) {
  state.office = o;
  document.querySelectorAll('[data-office]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.office === o);
  });
  // scope 토글 — 정당지지만 시도/시군구 둘 다라 의미. 데이터 둘 다 있을 때만 노출.
  const scopeSeg = $('#scope-seg');
  const showScope = o === '정당지지' && hasSigunguData();
  scopeSeg.toggleAttribute('hidden', !showScope);
  if (!showScope) {
    state.scope = '시도';  // reset
  } else if (o === '정당지지') {
    // 정당지지 진입 시 시군구 기본 (지역별 격차가 더 흥미)
    state.scope = '시군구';
    document.querySelectorAll('[data-scope]').forEach((b) => {
      b.classList.toggle('is-active', b.dataset.scope === '시군구');
    });
  }
  setView(state.view);
  renderDetail();
  recalcSegFades();  // scope seg 노출 변화 → 페이드 재계산
}

function setScope(s) {
  state.scope = s;
  document.querySelectorAll('[data-scope]').forEach((b) => {
    b.classList.toggle('is-active', b.dataset.scope === s);
  });
  setView(state.view);
  renderDetail();
}

// === 초기화 ===

// 가로 스크롤되는 컨트롤(.seg)에 "더 있다" 페이드 — 끝에 닿으면 해제.
let recalcSegFades = () => {};
function setupSegFades() {
  const segs = [...document.querySelectorAll('.controls .seg')];
  const update = (el) => {
    const more = el.scrollWidth - el.clientWidth;
    if (more <= 1) { el.classList.remove('fade-left', 'fade-right'); return; }
    el.classList.toggle('fade-left', el.scrollLeft > 1);
    el.classList.toggle('fade-right', el.scrollLeft < more - 1);
  };
  segs.forEach((el) => {
    update(el);
    el.addEventListener('scroll', () => update(el), { passive: true });
  });
  recalcSegFades = () => segs.forEach(update);
  window.addEventListener('resize', recalcSegFades, { passive: true });
}

async function init() {
  setCountdown();
  setPhase();
  setInterval(setCountdown, 60_000);
  // 선거별 렌즈 전환 바 — per-election 폴 페이지에서만(허브는 election 없어 no-op).
  if (window.LensSwitcher && window.__INITIAL_STATE__ && window.__INITIAL_STATE__.election) {
    const el = window.__INITIAL_STATE__.election;
    const LT = { presidential: 'presidential', general_election: 'national_assembly', national_assembly: 'national_assembly', local: 'local' };
    if (LT[el.kind]) window.LensSwitcher.mount({ current: 'polls', id: el.slug, type: LT[el.kind], n: el.n });
  }
  await loadData();
  // 대선/총선 페이지면 전용 렌더 경로가 인계 — 지선 모놀리식 스킵.
  if (typeof initPresIfNeeded === 'function' && await initPresIfNeeded()) return;
  if (typeof initGenIfNeeded === 'function' && await initGenIfNeeded()) return;
  document.querySelectorAll('[data-view]').forEach((b) => {
    b.addEventListener('click', () => setView(b.dataset.view));
  });
  document.querySelectorAll('[data-office]').forEach((b) => {
    b.addEventListener('click', () => setOffice(b.dataset.office));
  });
  document.querySelectorAll('[data-scope]').forEach((b) => {
    b.addEventListener('click', () => setScope(b.dataset.scope));
  });
  setupSegFades();
  // 정적 prerender가 주입한 초기 상태 (URL 기반)
  const init0 = (typeof window !== 'undefined' && window.__INITIAL_STATE__) || {};
  if (init0.office) setOffice(init0.office);
  setView(init0.view || state.view);  // 기본 hex (prerender가 view 주입 시 그것)
  // 지선 per-election 페이지 — 선거 무렵 국정·정당 지지 배경(허브는 election 없어 no-op)
  if (window.PollClimate) PollClimate.mount({ after: 'election-intro' });
}

init();
