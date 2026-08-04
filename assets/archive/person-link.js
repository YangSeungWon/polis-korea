// 후보 이름 → 인물 페이지 링크 — data/person-links/{eid}.json.
//
// 결과 파일의 후보에는 식별자가 없어 (직, 지역, 이름)으로 색인한다. 동명이인이 걸리는
// 키는 색인에서 아예 빠져 있으므로(build_person_links가 unresolved로 분리) 여기서는
// 있으면 걸고 없으면 그냥 텍스트로 둔다 — 억지 매칭을 하지 않는다.
(function () {
  let _map = null;
  let _loading = null;

  async function load(eid) {
    if (_map) return _map;
    if (!_loading) {
      _loading = fetch(`data/person-links/${eid}.json`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { _map = (d && d.links) || {}; return _map; })
        .catch(() => { _map = {}; return _map; });
    }
    return _loading;
  }

  // tc·place는 person-index의 race 필드와 같은 값이어야 한다.
  function href(tc, place, name) {
    if (!_map) return null;
    const slug = _map[`${tc}|${place}|${name}`];
    return slug ? `/person/${encodeURIComponent(slug)}/` : null;
  }

  // 이름을 링크로 감싼다. 연결 못 하면 원문 그대로 — 죽은 링크를 만들지 않는다.
  function wrap(tc, place, name, cls) {
    const h = href(tc, place, name);
    if (!h) return name;
    return `<a class="${cls || 'ar-person-link'}" href="${h}">${name}</a>`;
  }

  window.Archive = window.Archive || {};
  window.Archive.personLink = { load, href, wrap };
})();
