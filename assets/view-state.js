// 화면 상태 ↔ URL — 공유 링크로 같은 화면을 열고, 뒤로가기로 이전 화면에 돌아오게.
//
// 원칙 (Shneiderman의 History·Extract):
//   · 같은 틱 안의 여러 set은 **한 번**만 기록한다(microtask로 모음). 유형을 바꾸면
//     setType→setRound가 연달아 URL을 고치는데, 그게 뒤로가기 항목 둘이 되면 안 된다.
//   · 뒤로가기 항목(pushState)은 **경로가 바뀔 때만** 만든다 — 회차·선거 유형·직위.
//     표현 방식·선택·줌·필터는 replaceState: URL엔 남되 뒤로가기를 쌓지 않는다.
//   · 기본값과 같은 파라미터는 지운다(호출부가 null을 넘긴다) — 링크가 짧고 정본이 하나다.
//   · 복원 중(초기화·popstate)에 일어난 기록은 quiet()로 감싸 항상 replace다.
//
// 사용:
//   ViewState.get('sel') / getAll('v')
//   ViewState.set({ view: 'grid', sel: null })            // replace
//   ViewState.setPath('/history/presidential/21/', { nav: true })  // 경로가 바뀌면 push
//   ViewState.onPop(() => restore())
//   ViewState.hostMode('sgg', ['단색','geo','격자','dorling'])  → URL ?v=sgg-grid 이면 '격자'
//   ViewState.setHostMode('sgg', '격자', '단색')          // 기본 모드면 v에서 뺀다
//
// 파라미터 이름 — 한 페이지 안에서만 뜻을 갖는다(페이지끼리 공유하지 않는다).
// 같은 페이지에 같은 이름을 쓰는 위젯이 둘 생기면 앞에 접두어를 붙인다(당선자 표 w*).
//   공통      sel=시도|시군구 (고른 곳)   q= (검색어)
//   history   view= (표현 방식)  z= (줌)  — 회차·유형·직위는 경로(/history/{유형}/{n}/)
//   archive   v={host}-{mode} (지도마다 하나, 기본 모드는 생략 — 뷰 키와 같은 이름)
//             wq= wsido= wparty= wlv= (당선자 표)   margin= (기초단체장 접전 상한)
//   polls     office= scope= view= mode= sel=
//   search    q= round=      region hub  q=      compare  a= b= (지역 slug)
//   chronology f= (종류) from= to= (연도)
(function () {
  let pending = null;
  let quietDepth = 0;

  function current() { return pending ? pending.url : new URL(location.href); }

  function schedule(nav) {
    if (!pending) {
      pending = { url: new URL(location.href), nav: false, quiet: false };
      queueMicrotask(flush);
    }
    if (nav) pending.nav = true;
    if (quietDepth > 0) pending.quiet = true;
    return pending.url;
  }

  function flush() {
    const p = pending;
    pending = null;
    if (!p) return;
    const next = p.url.pathname + p.url.search + p.url.hash;
    const now = location.pathname + location.search + location.hash;
    if (next === now) return;
    const push = p.nav && !p.quiet && p.url.pathname !== location.pathname;
    try {
      if (push) history.pushState(null, '', next);
      else history.replaceState(history.state, '', next);
    } catch (e) { /* file:// 등 — URL 기록 불가해도 화면은 동작 */ }
  }

  function get(k) { return current().searchParams.get(k); }
  function getAll(k) { return current().searchParams.getAll(k); }

  function set(patch, opts) {
    const url = schedule(opts && opts.nav);
    const sp = url.searchParams;
    for (const k of Object.keys(patch)) {
      const v = patch[k];
      sp.delete(k);
      if (v == null || v === '') continue;
      if (Array.isArray(v)) v.forEach((x) => { if (x != null && x !== '') sp.append(k, String(x)); });
      else sp.set(k, String(v));
    }
  }

  function setPath(path, opts) {
    const url = schedule(opts && opts.nav);
    url.pathname = path;
  }

  function quiet(fn) {
    quietDepth++;
    try { return fn(); } finally { quietDepth--; }
  }

  function onPop(fn) { window.addEventListener('popstate', () => quiet(fn)); }

  // ── 뷰 키(host×mode) 기반 — archive처럼 한 페이지에 지도가 여럿일 때 ?v=를 여러 개 둔다.
  function encOf(token, encKeys, mode) {
    const VK = window.ViewKeys;
    if (!VK) return null;
    return encKeys.find((e) => VK.modeOf(e) === mode) || null;
  }

  function hostMode(token, encKeys) {
    const VK = window.ViewKeys;
    if (!VK || !token) return null;
    for (const key of getAll('v')) {
      const hm = VK.parseKey(key);
      if (hm && hm[0] === token && hm[1]) return encOf(token, encKeys, hm[1]);
    }
    return null;
  }

  function setHostMode(token, enc, defaultEnc) {
    const VK = window.ViewKeys;
    if (!VK || !token) return;
    const mode = VK.modeOf(enc);
    const rest = getAll('v').filter((key) => {
      const hm = VK.parseKey(key);
      return !(hm && hm[0] === token);
    });
    if (mode && enc !== defaultEnc) rest.push(VK.keyFor(token, mode));
    set({ v: rest });
  }

  window.ViewState = { get, getAll, set, setPath, quiet, onPop, hostMode, setHostMode };
})();
