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
      .catch(() => ({ active: [], archive: [] }));
    return indexPromise;
  }

  // 모든 id (active + archive) 메타 일괄 로드.
  async function loadAllElectionMetas() {
    const idx = await loadElectionsIndex();
    const ids = [...(idx.active || []), ...(idx.archive || [])];
    const metas = await Promise.all(ids.map(loadElectionMeta));
    return metas.filter((m) => m);
  }

  // archive 페이지가 있는 회차만 (meta.archive.page 존재).
  async function loadArchiveablePages() {
    const all = await loadAllElectionMetas();
    return all.filter((m) => m?.archive?.page);
  }

  root.Elections = { loadElectionMeta, loadElectionsIndex, loadAllElectionMetas, loadArchiveablePages };
})(window);
