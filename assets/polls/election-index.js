// 선거별 여론조사 디렉터리 — 공용 ElectionTimeline로 3레인 타임라인 렌더(노드 → /polls/{slug}/).
//   허브(/polls.html)·각 per-election 페이지 모두에 노출(현재/최근 회차 강조). 폴 있는 회차만(election_index).
(function () {
  'use strict';
  const host = document.getElementById('poll-election-index');
  if (!host) return;
  const sec = host.closest('.poll-index-sec');
  const cur = (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.election
    && window.__INITIAL_STATE__.election.slug) || null;
  getJson('data/polls/election_index.json', [])
    .then((list) => {
      if (!Array.isArray(list) || !list.length || !window.ElectionTimeline) { sec && sec.remove(); return; }
      window.ElectionTimeline.render(host, list, {
        hrefFn: (e) => `/polls/${e.slug}/`,
        current: cur,
        curSuffix: '(최근)',
        ariaFn: (e) => `${e.name} 여론조사 vs 실제`,
        note: '이 사이트의 여론조사 자료는 2016년 선거부터입니다. 그 이전은 <a href="/history.html">역대 결과 →</a>',
      });
    })
    .catch(() => { sec && sec.remove(); });
})();
