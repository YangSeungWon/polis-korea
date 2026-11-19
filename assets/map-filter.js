// 지도 위 동적 질의 — "1·2위 격차가 x%p 이하인 곳"(접전).
//
// 기초단체장 지도에만 붙는다(render-council-hex) — 한 명이 그 시군구에서 실제로 이긴
// 선거라야 '접전'이 뜻을 갖는다. 대선 지도엔 없다(시군구 승부가 아니다).
//
// 조건 밖 칸을 **지우지 않고 흐린다**. 전체 모습(Overview)은 남고, 조건에 맞는 곳이
// 그 위로 떠오른다. 지도를 다시 그리지 않고 class만 바꾼다 — 끄는 동안 즉시 반영.
//
// 맞는 칸에는 테두리를 두른다 — 단색 지도는 격차가 작을수록 옅게 칠하므로, 접전만
// 고르면 맞는 칸이 가장 옅은 칸이다. 흐림만으로는 무엇이 남았는지 안 보인다.
//
// 모르는 값은 조건에 맞지 않는다고 하지 않는다 — '자료 없음'으로 따로 센다.
// (무투표 당선은 격차가 없다: 접전도 아니고 대패도 아니다.)
//
//   MapFilter.attach(mapHost, area, marginOf(sido, name) → %p | null)
//   area 안의 [data-region] 칸에 적용. 다시 그린 뒤 또 불러도 된다(막대는 한 번만 붙는다).
(function () {
  const VS = () => window.ViewState;
  const MARGIN_MAX = 40;   // 이 값이면 '제한 없음'

  function attach(mapHost, area, marginOf) {
    if (!mapHost || !area) return;
    let st = mapHost._mf;
    if (!st) {
      st = mapHost._mf = {};
      const bar = document.createElement('div');
      bar.className = 'map-filter';
      bar.innerHTML = `<label class="mf-margin"><span class="mf-lbl">접전</span>
          <input type="range" min="1" max="${MARGIN_MAX}" step="1" aria-label="1·2위 격차 상한(%p)">
          <output class="mf-mval"></output></label>
        <button type="button" class="fig-tool mf-reset" hidden>조건 지우기</button>
        <span class="mf-count" aria-live="polite"></span>`;
      // 지도 **아래**(범례 앞)에 둔다. 위는 방식 토글이 지도 모서리에 떠 있는 자리라 겹친다.
      area.parentNode.insertBefore(bar, area.nextSibling);
      st.bar = bar;
      st.margin = bar.querySelector('.mf-margin input');
      st.mval = bar.querySelector('.mf-mval');
      const v = VS();
      const mg = v ? +v.get('margin') : NaN;
      st.margin.value = (mg >= 1 && mg < MARGIN_MAX) ? mg : MARGIN_MAX;
      st.margin.addEventListener('input', () => update(st));
      bar.querySelector('.mf-reset').addEventListener('click', () => {
        st.margin.value = MARGIN_MAX;
        update(st);
      });
    }
    st.area = area; st.marginOf = marginOf;
    apply(st);
  }

  function limit(st) {
    const mg = +st.margin.value;
    return mg < MARGIN_MAX ? mg : null;
  }

  let urlT = null;
  function update(st) {
    apply(st);
    // URL은 손을 멈춘 뒤에 — 끄는 동안 매 틱 replaceState를 부르면 브라우저가 막는다.
    clearTimeout(urlT);
    urlT = setTimeout(() => { if (VS()) VS().set({ margin: limit(st) }); }, 300);
  }

  function apply(st) {
    const lim = limit(st);
    const on = lim != null;
    st.mval.textContent = on ? `격차 ${lim}%p 이하` : '제한 없음';
    st.bar.querySelector('.mf-reset').hidden = !on;
    st.area.classList.toggle('mf-on', on);
    const seen = new Map();   // region → hit|out|unknown (지도 하나에 같은 지역 칸이 여럿일 수 있다)
    st.area.querySelectorAll('[data-region]').forEach((el) => {
      const key = el.dataset.region;
      let r = seen.get(key);
      if (!r) {
        const m = on ? st.marginOf(...key.split('|')) : null;
        r = !on ? 'hit' : m == null ? 'unknown' : m > lim ? 'out' : 'hit';
        seen.set(key, r);
      }
      el.classList.toggle('mf-hit', on && r === 'hit');
      el.classList.toggle('mf-out', on && r !== 'hit');
    });
    const cnt = st.bar.querySelector('.mf-count');
    if (!on) { cnt.textContent = ''; return; }
    let hit = 0, unk = 0;
    for (const r of seen.values()) { if (r === 'hit') hit++; else if (r === 'unknown') unk++; }
    cnt.textContent = `${hit}곳 / ${seen.size}곳` + (unk ? ` · 자료 없음·무투표 ${unk}곳` : '');
  }

  window.MapFilter = { attach, _limit: limit };
})();
