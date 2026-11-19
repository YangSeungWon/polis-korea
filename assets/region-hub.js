// 지역 허브 — 지도에서 고르고, 이름으로 찾는다.
//
// 지도: 지금 시군구를 육각형 한 칸씩(data/geo/sigungu_hex.json). 칸이 그 지역 페이지
// 링크다(SVG <a>) — 마우스·키보드·스크린리더가 그대로 따라간다. 정당색은 칠하지 않는다:
// 이 페이지는 어느 한 선거의 결과가 아니다.
//
// 링크 대상은 **이 페이지 목록에 실제로 있는 지역**만 — 목록의 href를 모아 둔 것과 맞춘다.
// 이름 모양으로 slug를 짓지 않는다(없는 페이지로 보내지 않는다).
//
// JS가 없으면 지도가 비고, 접힌 목록이 같은 링크를 전부 갖는다(크롤러·비JS).
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const q = document.getElementById('rg-q');
  const hit = document.getElementById('rg-hit');
  const list = document.getElementById('rg-list');
  const svg = document.getElementById('rg-map');
  const items = [...document.querySelectorAll('.rg-item')];
  const secs = [...document.querySelectorAll('.dash-section[data-sido]')];
  const norm = (s) => (s || '').replace(/\s+/g, '');

  // 목록에 있는 페이지 — "시도-시군구" → href
  const pages = new Map();
  for (const a of items) pages.set(decodeURIComponent(a.getAttribute('href')).replace(/^\/region\/|\/$/g, ''), a.getAttribute('href'));
  // 시도 페이지(세종처럼 시군구가 없는 곳은 칸이 시도로 간다)
  const sidoHref = new Map([...document.querySelectorAll('.rg-sido-links a')].map((a) => [a.title, a.getAttribute('href')]));

  let cellsDrawn = [];
  async function drawMap() {
    if (!svg || typeof window.drawSigunguHex !== 'function') return;
    let cells;
    try { cells = await fetch('/data/geo/sigungu_hex.json').then((r) => (r.ok ? r.json() : null)); } catch { cells = null; }
    if (!Array.isArray(cells) || !cells.length) return;
    const canon = (s) => (typeof canonSido === 'function' ? canonSido(s) : s);
    window.drawSigunguHex(svg, cells, () => null, { r: 22 });
    const byKey = new Map(cells.map((c) => [`${c.sido}|${c.name}`, c]));
    cellsDrawn = [];
    svg.querySelectorAll('polygon.hex-cell[data-region]').forEach((poly) => {
      const c = byKey.get(poly.dataset.region);
      if (!c) return;
      const sd = canon(c.sido);
      const href = pages.get(`${sd}-${c.name}`) || pages.get(`${c.sido}-${c.name}`) || sidoHref.get(sd) || null;
      poly.classList.remove('no-data');
      poly.classList.add('rg-cell');
      if (!href) { poly.classList.add('rg-cell-nolink'); return; }
      const a = document.createElementNS(NS, 'a');
      a.setAttribute('href', href);
      a.setAttribute('aria-label', `${sd} ${c.name}`);
      poly.parentNode.insertBefore(a, poly);
      a.appendChild(poly);
      cellsDrawn.push({ poly, name: c.name, sido: sd });
    });
    svg.classList.add('is-ready');
    apply();
  }

  function apply() {
    const t = q ? norm(q.value) : '';
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
    // 검색하면 목록을 펼친다(지도에 없는 일반구·옛 이름도 거기서 잡힌다)
    if (list && t) list.open = true;
    // 지도: 맞는 칸만 밝게 — 지우지 않는다
    if (svg) {
      svg.classList.toggle('is-searching', !!t);
      for (const c of cellsDrawn) {
        const on = !!t && (norm(c.name).includes(t) || norm(c.sido).includes(t));
        c.poly.classList.toggle('is-hit', on);
      }
    }
    if (hit) hit.textContent = t ? `${n}곳` : '';
  }

  // 검색어 ↔ URL(?q=, replace) — '성남'으로 좁힌 목록을 링크로 보낼 수 있게.
  const VS = window.ViewState;
  if (q) {
    if (VS && VS.get('q')) q.value = VS.get('q');
    q.addEventListener('input', () => { apply(); if (VS) VS.set({ q: q.value.trim() || null }); });
  }
  apply();
  drawMap();
})();
