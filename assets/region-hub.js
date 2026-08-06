// 지역 허브 찾기 — 366곳 목록에서 자기 지역을 눈으로 훑게 하지 않는다.
//
// JS가 없으면 입력창만 안 보이고 **목록은 그대로 있다**. 검색이 기능을 대체하는 게
// 아니라 위에 얹히는 것이라, 크롤러·비JS 사용자도 전 지역 링크에 그대로 닿는다.
(function () {
  const q = document.getElementById('rg-q');
  const hit = document.getElementById('rg-hit');
  if (!q) return;
  const items = [...document.querySelectorAll('.rg-item')];
  const secs = [...document.querySelectorAll('.dash-section[data-sido]')];
  // 초성이 아니라 부분일치 — '분당'으로 '성남시분당구'를, '성남'으로 세 구를 다 찾는다.
  const norm = (s) => (s || '').replace(/\s+/g, '');
  function apply() {
    const t = norm(q.value);
    let n = 0;
    for (const el of items) {
      const on = !t || norm(el.dataset.name || el.textContent).includes(t)
        || norm(el.closest('[data-sido]')?.dataset.sido || '').includes(t);
      el.hidden = !on;
      if (on) n++;
    }
    for (const s of secs) {
      s.hidden = !s.querySelector('.rg-item:not([hidden])');
      // 검색 중에는 접힌 '폐지·변경'도 펼친다 — 찾는 게 거기 있으면 안 보이면 안 된다
      const d = s.querySelector('.rg-past');
      if (d) d.open = !!t && !!d.querySelector('.rg-item:not([hidden])');
    }
    hit.textContent = t ? `${n}곳` : '';
  }
  q.addEventListener('input', apply);
  apply();
})();
