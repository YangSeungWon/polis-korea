// 연동 하이라이트(brushing) — 한 곳에 올린 손이 같은 지역을 가리키는 다른 표시를 함께 밝힌다.
//
// 지도 칸과 표 행이 같은 키 data-region="시도|시군구"(시도 단위는 "시도")를 단다.
// 렌더러는 서로를 모른다 — 키만 맞추면 된다. 시도 키는 그 시도의 시군구 키와도 맞는다
// (시·도의회 칸에 올리면 그 시도의 시군구 칸과 광역의원 행이 함께 밝아진다).
//
// 지운다·숨긴다가 아니라 나머지를 **흐리게** 한다 — 전체 모습(Overview)은 그대로 둔다.
(function () {
  const ON = 'is-brushed';
  let active = null;

  const related = (a, b) => a === b || a.startsWith(b + '|') || b.startsWith(a + '|');

  function clear() {
    document.querySelectorAll('.' + ON).forEach((el) => el.classList.remove(ON));
    document.querySelectorAll('.brushing').forEach((el) => el.classList.remove('brushing'));
    active = null;
  }

  function apply(key) {
    if (key === active) return;
    clear();
    if (!key) return;
    active = key;
    const hosts = new Set();
    document.querySelectorAll('[data-region]').forEach((el) => {
      if (!related(el.dataset.region, key)) return;
      el.classList.add(ON);
      const h = el.closest('svg, .ar-winners-grid');
      if (h) hosts.add(h);
    });
    // 같은 지역이 하나도 없는 지도는 흐리지 않는다 — 그 지도와는 상관없는 손이다.
    hosts.forEach((h) => h.classList.add('brushing'));
  }

  function keyOf(target) {
    const el = target && target.closest ? target.closest('[data-region]') : null;
    return el ? el.dataset.region : null;
  }

  document.addEventListener('mouseover', (e) => apply(keyOf(e.target)));
  document.addEventListener('focusin', (e) => apply(keyOf(e.target)));
  document.addEventListener('mouseleave', clear);

  window.Brush = { apply, clear, related };
})();
