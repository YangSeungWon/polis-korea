// 연동 하이라이트(brushing) — 지도 칸 ↔ 당선자 표 행, 이 둘 사이만.
//
// 지도 칸과 표 행이 같은 키 data-region="시도|시군구"(시도 단위는 "시도")를 단다.
// 렌더러는 서로를 모른다 — 키만 맞추면 된다. 시도 키는 그 시도의 시군구 키와도 맞는다.
//
// 방향을 건너서만 밝힌다:
//   · 표 행에 손 → 지도들의 같은 지역 칸이 밝아지고 나머지 칸은 흐려진다.
//   · 지도 칸에 손 → 표의 같은 지역 행만 밝아진다. 다른 지도는 건드리지 않는다 —
//     지도 위에서 손을 움직일 때마다 페이지의 모든 지도가 깜빡이면 방해만 된다.
// 지운다·숨긴다가 아니라 나머지를 **흐리게** 한다 — 전체 모습(Overview)은 그대로 둔다.
(function () {
  const ON = 'is-brushed';
  const TABLE = '.ar-winners-grid';
  let active = null;

  const related = (a, b) => a === b || a.startsWith(b + '|') || b.startsWith(a + '|');

  function clear() {
    document.querySelectorAll('.' + ON).forEach((el) => el.classList.remove(ON));
    document.querySelectorAll('.brushing').forEach((el) => el.classList.remove('brushing'));
    active = null;
  }

  // from: 'table' | 'map' — 손을 올린 쪽. 반대쪽만 밝힌다.
  function apply(key, from) {
    const tag = key && `${from}:${key}`;
    if (tag === active) return;
    clear();
    if (!key || !document.querySelector(TABLE)) return;   // 표가 없는 페이지 — 짝이 없다
    active = tag;
    const sel = from === 'table' ? 'svg [data-region]' : `${TABLE} [data-region]`;
    const hosts = new Set();
    document.querySelectorAll(sel).forEach((el) => {
      if (!related(el.dataset.region, key)) return;
      el.classList.add(ON);
      const h = el.closest(from === 'table' ? 'svg' : TABLE);
      if (h) hosts.add(h);
    });
    // 같은 지역이 하나도 없는 지도는 흐리지 않는다 — 그 지도와는 상관없는 손이다.
    hosts.forEach((h) => h.classList.add('brushing'));
  }

  function source(target) {
    const el = target && target.closest ? target.closest('[data-region]') : null;
    if (!el) return [null, null];
    if (el.closest(TABLE)) return [el.dataset.region, 'table'];
    if (el.closest('svg')) return [el.dataset.region, 'map'];
    return [null, null];
  }

  const on = (e) => apply(...source(e.target));
  document.addEventListener('mouseover', on);
  document.addEventListener('focusin', on);
  document.addEventListener('mouseleave', clear);

  window.Brush = { apply, clear, related };
})();
