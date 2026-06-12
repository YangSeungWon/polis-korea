// 최근 여론조사 피드 — 상시 누적되는 정당지지(aggregated_etc)·차기주자(aggregated_candidates)
// 개별 조사를 최신순 카드로. 선거별 상세(hex explorer)와 독립. renderPollCard(utils.js) 재사용.
// "여론조사" 허브의 상시 섹션 — 선거 시즌이 아니어도 계속 최신이라 낡지 않음.
(function () {
  'use strict';
  const PAGE = 24;
  let all = [], filter = 'all', shown = PAGE;

  const host = () => document.getElementById('recent-feed-host');
  const moreBtn = () => document.getElementById('rp-more');

  function pass(p) {
    if (filter === 'party') return p.metric_type === '정당지지';
    if (filter === 'cand') return p.metric_type && p.metric_type !== '정당지지';
    return true;
  }

  function render() {
    const h = host();
    if (!h) return;
    const list = all.filter(pass);
    const slice = list.slice(0, shown);
    h.innerHTML = slice.length
      ? slice.map((p) => renderPollCard(p, p.office_label)).join('')
      : '<p class="rp-empty">표시할 조사가 없습니다.</p>';
    const m = moreBtn();
    if (m) m.hidden = shown >= list.length;
  }

  async function load() {
    if (!host()) return;
    const files = ['data/polls/aggregated_etc.json', 'data/polls/aggregated_candidates.json'];
    try {
      const parts = await Promise.all(files.map((f) =>
        fetch(f).then((r) => (r.ok ? r.json() : { polls: [] })).catch(() => ({ polls: [] }))));
      all = parts.flatMap((d) => d.polls || [])
        .filter((p) => p.period_end && (p.candidates || []).length)
        .sort((a, b) => (b.period_end || '').localeCompare(a.period_end || ''));
    } catch (e) {
      all = [];
    }
    render();
  }

  function init() {
    document.querySelectorAll('.rp-filter [data-rp]').forEach((b) => {
      b.addEventListener('click', () => {
        document.querySelectorAll('.rp-filter [data-rp]').forEach((x) => x.classList.remove('is-active'));
        b.classList.add('is-active');
        filter = b.dataset.rp;
        shown = PAGE;
        render();
      });
    });
    const m = moreBtn();
    if (m) m.addEventListener('click', () => { shown += PAGE; render(); });
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
