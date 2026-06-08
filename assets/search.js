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
    // 이름 단위로 group — 같은 이름이 N≥2 race면 인물 카드로 묶고 펼치기 가능.
    const byName = new Map();
    for (const it of filtered) {
      if (!byName.has(it.n)) byName.set(it.n, []);
      byName.get(it.n).push(it);
    }
    const groups = Array.from(byName.entries()); // [[name, [items]]]
    // 정렬: race 많은 사람 먼저, 동수면 최근 연도
    groups.sort((a, b) => b[1].length - a[1].length
      || (Math.max(...b[1].map((x) => x.y || 0)) - Math.max(...a[1].map((x) => x.y || 0))));
    const capGroups = groups.slice(0, MAX_RESULTS);
    $('#meta').textContent = q || filterRound
      ? `${filtered.length.toLocaleString()}건 · ${groups.length.toLocaleString()}명${groups.length > MAX_RESULTS ? ` · 상위 ${MAX_RESULTS}명 표시` : ''}`
      : `${items.length.toLocaleString()}건 (검색어 입력)`;
    const html = capGroups.map(([name, list]) => {
      list.sort((a, b) => (b.y || 0) - (a.y || 0));
      if (list.length === 1) {
        const it = list[0];
        // 특정 회차 결과 → archive 직행. 오른쪽 끝에 인물 페이지 보조 링크 별도.
        return `<li class="s-item s-single">
          <a class="s-link" href="/archive/${it.e}/">
            <span class="s-name">${escapeHtml(it.n)}</span>
            ${partyBadge(it.p)}
            <span class="s-meta">${it.y || ''} · ${it.r} · ${escapeHtml(it.d)}</span>
            ${it.pct != null ? `<span class="s-pct">${(+it.pct).toFixed(1)}%</span>` : ''}
          </a>
          <a class="s-aside-link" href="/person.html?name=${encodeURIComponent(it.n)}">인물</a>
        </li>`;
      }
      // 인물 카드 — 정당색 색띠로 시각 비교, 클릭하면 펼치기
      const parties = [...new Set(list.map((x) => x.p).filter(Boolean))].slice(0, 3);
      const years = list.map((x) => x.y).filter(Boolean);
      const yspan = years.length ? `${Math.min(...years)}–${Math.max(...years)}` : '';
      // 회차별 sub-row는 해당 archive로 직행 — 특정 race를 명시했으므로
      const sub = list.map((it) => `
        <a class="s-sub" href="/archive/${it.e}/">
          <span class="s-sub-yr">${it.y || ''}</span>
          <span class="s-sub-rd">${it.r}</span>
          ${partyBadge(it.p)}
          <span class="s-sub-place">${escapeHtml(it.d)}</span>
          ${it.pct != null ? `<span class="s-sub-pct">${(+it.pct).toFixed(1)}%</span>` : ''}
        </a>`).join('');
      return `<li class="s-item s-group">
        <details>
          <summary class="s-link s-group-hdr">
            <span class="s-name">${escapeHtml(name)}</span>
            <span class="s-group-count">${list.length}회</span>
            <span class="s-group-parties">${parties.map(partyBadge).join('')}</span>
            <span class="s-meta">${yspan}</span>
            <a class="s-group-link" href="/person.html?name=${encodeURIComponent(name)}" onclick="event.stopPropagation()">인물 →</a>
          </summary>
          <div class="s-sub-list">${sub}</div>
        </details>
      </li>`;
    }).join('');
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
