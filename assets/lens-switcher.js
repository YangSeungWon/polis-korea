// 선거별 렌즈 전환 — 같은 선거를 보는 3가지 방식 사이를 잇는다(어디 들어와도 다른 렌즈로 한 번에).
//   종합 결과(archive/{id}) · 여론조사 vs 실제(polls/{id}) · 역대 흐름(history/{type}/{n})
//   LensSwitcher.mount({ current:'archive'|'polls'|'history', type, n, date?, id?, host? })
//     type = 'presidential'|'national_assembly'|'local',  n = 회차,  id = archive/polls slug(없으면 유도)
//   존재하는 렌즈만 노출: archive=항상, polls=election_index.json, history=results/manifest.json.
(function () {
  'use strict';
  const TYPE_WORD = { presidential: 'pres', national_assembly: 'general', local: 'local' };
  function ordinal(n) { const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
  function deriveId(type, n, date) {
    const w = TYPE_WORD[type];
    if (!w || n == null || !date) return null;
    return `${ordinal(Number(n))}-${w}-${String(date).slice(0, 4)}`;
  }

  let _idx = null, _man = null;
  async function gates() {
    if (_idx && _man) return { idx: _idx, man: _man };
    const [idx, man] = await Promise.all([
      fetch('data/polls/election_index.json').then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch('data/results/manifest.json').then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
    ]);
    _idx = idx; _man = man;
    return { idx, man };
  }

  async function mount(opts) {
    opts = opts || {};
    const host = opts.host || document.getElementById('lens-switcher-host');
    if (!host) return;
    const type = opts.type, n = opts.n;
    const id = opts.id || deriveId(type, n, opts.date);
    if (!id || !type || n == null) { host.innerHTML = ''; return; }
    const { idx, man } = await gates();
    const hasPolls = Array.isArray(idx) && idx.some((e) => e.slug === id);
    const hasHistory = Array.isArray(man[type]) && man[type].includes(Number(n));
    const lenses = [
      { key: 'archive', label: '종합 결과', href: `/archive/${id}/`, on: true },
      { key: 'polls', label: '여론조사 vs 실제', href: `/polls/${id}/`, on: hasPolls },
      // URL 슬러그는 하이픈(history/national-assembly/) — manifest 키는 언더스코어(national_assembly).
      { key: 'history', label: '역대 흐름', href: `/history/${type.replace(/_/g, '-')}/${n}/`, on: hasHistory },
    ].filter((l) => l.on);
    if (lenses.length < 2) { host.innerHTML = ''; return; }   // 전환할 다른 렌즈 없으면 숨김
    host.innerHTML = '<nav class="lens-switcher" aria-label="이 선거 보는 방식">'
      + '<span class="lens-label">이 선거</span>'
      + lenses.map((l) => (l.key === opts.current
        ? `<span class="lens-chip is-current" aria-current="page">${l.label}</span>`
        : `<a class="lens-chip" href="${l.href}">${l.label}</a>`)).join('')
      + '</nav>';
  }

  window.LensSwitcher = { mount, deriveId };
})();
