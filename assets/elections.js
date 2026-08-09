// 회차 레지스트리 client — data/elections/{id}.json + index.json fetch + cache.
// 단일 출처: 페이지가 회차 메타를 직접 박지 말고 이걸 통해 가져옴.

(function (root) {
  const cache = new Map();
  let indexPromise = null;

  function loadElectionMeta(id) {
    if (!id) return Promise.resolve(null);
    if (cache.has(id)) return cache.get(id);
    const p = fetch(`/data/elections/${id}.json`, { cache: 'default' })
      .then((r) => r.ok ? r.json() : null)
      .catch(() => null);
    cache.set(id, p);
    return p;
  }

  function loadElectionsIndex() {
    if (indexPromise) return indexPromise;
    indexPromise = fetch('/data/elections/index.json', { cache: 'default' })
      .then((r) => r.ok ? r.json() : { active: [], archive: [] })
    .then((d) => (d && typeof d === 'object' ? d : { active: [], archive: [] }))
      .catch(() => ({ active: [], archive: [] }));
    return indexPromise;
  }

  root.Elections = { loadElectionMeta, loadElectionsIndex };
})(window);
