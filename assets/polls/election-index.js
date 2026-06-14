// 선거별 여론조사 디렉터리 — data/polls/election_index.json(build_static 생성) 읽어 카드 렌더.
// 허브(/polls.html)와 각 per-election 페이지(/polls/{id}/) 모두에 노출 — 회차 간 이동.
(function () {
  'use strict';
  const host = document.getElementById('poll-election-index');
  if (!host) return;
  const sec = host.closest('.poll-index-sec');
  const cur = (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.election
    && window.__INITIAL_STATE__.election.slug) || null;
  fetch('data/polls/election_index.json')
    .then((r) => (r.ok ? r.json() : []))
    .then((list) => {
      if (!Array.isArray(list) || !list.length) { sec && sec.remove(); return; }
      host.innerHTML = list.map((e) => {
        const isCur = e.slug === cur;
        return `<a class="poll-index-card${isCur ? ' is-current' : ''}" href="/polls/${e.slug}/"`
          + `${isCur ? ' aria-current="page"' : ''}>`
          + `<span class="pic-name">${e.name}</span>`
          + `<span class="pic-date">${e.date}</span>`
          + (isCur ? '<span class="pic-tag">지금 보는 중</span>' : '<span class="pic-go">여론조사 vs 실제 →</span>')
          + '</a>';
      }).join('');
    })
    .catch(() => { sec && sec.remove(); });
})();
