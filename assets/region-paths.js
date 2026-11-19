// 지도에서 고른 곳 → 그 지역의 역대 선거 페이지(/region/…).
//
// 해소표는 build_region_pages가 낸 data/regions/index.json 하나다 — 페이지가 실제로
// 만들어진 slug, 시도 개명(강원도→강원특별자치도), containment의 선거구 집계
// (동대문갑구→동대문구). 이름 모양으로 추측하지 않는다: 못 정하면 링크를 안 단다.
(function () {
  let p = null;
  function load() {
    if (!p) {
      p = fetch('/data/regions/index.json').then((r) => (r.ok ? r.json() : null)).then((j) => {
        if (!j) return null;
        const pages = new Map(j.regions.map((r) => [r.slug, r]));
        return { pages, alias: j.sido_alias || {}, fold: j.fold || {} };
      }).catch(() => null);
    }
    return p;
  }

  function resolveWith(ix, sido, name) {
    if (!ix || !sido) return null;
    const sd = ix.alias[sido] || sido;
    if (!name) return ix.pages.has(sd) ? sd : null;
    const direct = `${sd}-${name}`;
    if (ix.pages.has(direct)) return direct;
    const parent = ix.fold[`${sd}|${name}`];
    return parent && ix.pages.has(`${sd}-${parent}`) ? `${sd}-${parent}` : null;
  }

  async function href(sido, name) {
    const slug = resolveWith(await load(), sido, name);
    return slug ? `/region/${encodeURIComponent(slug)}/` : null;
  }

  // container 끝에 '이 지역의 역대 선거 →' 링크를 단다. 없으면 아무것도 안 단다.
  async function attach(container, sido, name) {
    if (!container) return null;
    const url = await href(sido, name);
    if (!url || !container.isConnected || container.querySelector('.region-page-link')) return null;
    const a = document.createElement('a');
    a.className = 'region-page-link';
    a.href = url;
    a.textContent = '이 지역의 역대 선거 →';
    container.appendChild(a);
    return a;
  }

  window.RegionPaths = { load, href, attach, resolveWith };
})();
