// 통합 검색 — 이름·지역·정당 fuzzy match. 인덱스: assets/search-index.json.

(function () {
  const $ = (s) => document.querySelector(s);
  let items = [];
  let filterRound = '';
  const MAX_RESULTS = 200;

  async function load() {
    try {
      const r = await fetch('assets/search-index.json');
      const j = await r.json();
      items = j.items || [];
    } catch (e) {
      $('#meta').textContent = '인덱스 로드 실패';
      return;
    }
    render($('#q').value || '');
  }

  function normalize(s) {
    return (s || '').toString().toLowerCase().replace(/\s+/g, '');
  }

  function match(it, q) {
    if (!q) return true;
    const hay = normalize(it.n + ' ' + it.p + ' ' + it.d + ' ' + (it.y || ''));
    return hay.includes(q);
  }

  function archiveHref(eid) {
    return `/archive/${eid}/`;
  }

  function partyBadge(party) {
    const col = (typeof partyColor === 'function') ? partyColor(party) : '#888';
    return `<span class="s-party" style="color:${col};border-color:${col}">${party || '무소속'}</span>`;
  }

  function render(rawQ) {
    const q = normalize(rawQ);
    const filtered = items.filter((it) => {
      if (filterRound && it.r !== filterRound) return false;
      return match(it, q);
    });
    const cap = filtered.slice(0, MAX_RESULTS);
    $('#meta').textContent = q || filterRound
      ? `${filtered.length.toLocaleString()}건 일치${filtered.length > MAX_RESULTS ? ` · 상위 ${MAX_RESULTS} 표시` : ''}`
      : `${items.length.toLocaleString()}건 (검색어 입력)`;
    const html = cap.map((it) => `
      <li class="s-item">
        <a class="s-link" href="${archiveHref(it.e)}">
          <span class="s-name">${escapeHtml(it.n)}</span>
          ${partyBadge(it.p)}
          <span class="s-meta">${it.y || ''} · ${it.r} · ${escapeHtml(it.d)}</span>
          ${it.pct != null ? `<span class="s-pct">${(+it.pct).toFixed(1)}%</span>` : ''}
        </a>
      </li>
    `).join('');
    $('#list').innerHTML = html;
  }

  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function init() {
    const input = $('#q');
    let t = null;
    input.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => render(input.value), 80);
    });
    document.querySelectorAll('[data-round]').forEach((b) => {
      b.addEventListener('click', () => {
        filterRound = b.dataset.round;
        document.querySelectorAll('[data-round]').forEach((x) => x.classList.toggle('is-active', x === b));
        render(input.value);
      });
    });
    // URL ?q=… 지원 — load 전 input.value 세팅, load 끝나면 render 호출됨
    const params = new URLSearchParams(location.search);
    const qp = params.get('q');
    if (qp) input.value = qp;
    load();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
