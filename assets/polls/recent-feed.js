// 최근 여론조사 피드 — 상시 누적되는 정당지지(aggregated_etc)·차기주자(aggregated_candidates)
// 개별 조사를 최신순 카드로. 선거별 상세(hex explorer)와 독립. renderPollCard(utils.js) 재사용.
// "여론조사" 허브의 상시 섹션 — 선거 시즌이 아니어도 계속 최신이라 낡지 않음.
(function () {
  'use strict';
  const SHOW = 3;   // 허브에선 맛보기만 — 연속 추세는 tracker로(rp-more가 정적 링크)
  let all = [], filter = 'all';

  const host = () => document.getElementById('recent-feed-host');

  function pass(p) {
    if (filter === 'party') return p.metric_type === '정당지지';
    // 차기주자 = 차기 대선주자만(tracker와 동일 기준). 지선 후보지지(시장·도지사 등)는 대선주자가
    // 아니라 의미 없음 — 전체에만 노출. 대선주자 폴이 없는 시기엔 아래에서 버튼 자체를 숨김.
    if (filter === 'cand') return p.metric_type === '후보지지' && p.office_level === '대통령';
    return true;
  }

  function render() {
    const h = host();
    if (!h) return;
    const slice = all.filter(pass).slice(0, SHOW);
    h.innerHTML = slice.length
      ? slice.map((p) => renderPollCard(p, p.office_label)).join('')
      : `<p class="rp-empty">${emptyText('표시할 조사가 없습니다.')}</p>`;
  }

  async function load() {
    if (!host()) return;
    // per-election 페이지(특정 회차 viz)에선 전역 최근 피드 숨김 — 허브(/polls.html)에만.
    if (typeof window !== 'undefined' && window.__INITIAL_STATE__ && window.__INITIAL_STATE__.election) {
      document.getElementById('recent-polls')?.remove();
      return;
    }
    const files = ['data/polls/aggregated_etc.json', 'data/polls/aggregated_candidates.json'];
    try {
      const parts = await Promise.all(files.map((f) =>
        getJson(f, { polls: [] })));
      all = parts.flatMap((d) => d.polls || [])
        .filter((p) => p.period_end && (p.candidates || []).length)
        .sort((a, b) => (b.period_end || '').localeCompare(a.period_end || ''));
    } catch (e) {
      all = [];
    }
    // 차기 대선주자 폴이 없는 시기(지선 국면 등)엔 '차기주자' 버튼 숨김 — 빈/오해 필터 방지.
    const hasPresCand = all.some((p) => p.metric_type === '후보지지' && p.office_level === '대통령');
    const candBtn = document.querySelector('.rp-filter [data-rp="cand"]');
    if (candBtn && !hasPresCand) {
      candBtn.hidden = true;
      if (filter === 'cand') { filter = 'all'; document.querySelectorAll('.rp-filter [data-rp]').forEach((x) => x.classList.toggle('is-active', x.dataset.rp === 'all')); }
    }
    render();
  }

  function init() {
    document.querySelectorAll('.rp-filter [data-rp]').forEach((b) => {
      b.addEventListener('click', () => {
        document.querySelectorAll('.rp-filter [data-rp]').forEach((x) => x.classList.remove('is-active'));
        b.classList.add('is-active');
        filter = b.dataset.rp;
        render();
      });
    });
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
