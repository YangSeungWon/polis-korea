// 회차 레지스트리 client — data/elections/{id}.json + index.json fetch + cache.
// 단일 출처: 페이지가 회차 메타를 직접 박지 말고 이걸 통해 가져옴.

(function (root) {
  const cache = new Map();
  let indexPromise = null;

  function loadElectionMeta(id) {
    if (!id) return Promise.resolve(null);
    if (cache.has(id)) return cache.get(id);
    // getJson으로 받아야 **못 받았다는 사실이 기록된다.** 여기서 조용히 null이
    // 되면 archive 엔트리(core.js)가 console.warn만 남기고 통째로 멈춰서,
    // 페이지가 정적 껍데기로 남는데도 화면엔 아무 말이 없다.
    const p = getJson(`/data/elections/${id}.json`, null, { cache: 'default' });
    cache.set(id, p);
    return p;
  }

  function loadElectionsIndex() {
    if (indexPromise) return indexPromise;
    indexPromise = getJson('/data/elections/index.json',
      { active: [], archive: [] }, { cache: 'default' });
    return indexPromise;
  }

  root.Elections = { loadElectionMeta, loadElectionsIndex };
})(window);
