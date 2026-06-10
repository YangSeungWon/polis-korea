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
    // 인물 단위 group — assembly_id 있으면 그 ID, 없으면 (name + 'unmatched') 키.
    // 같은 이름이라도 aid 다르면 동명이인 → 별도 카드. 항상 펴진 상태.
    const byPerson = new Map();
    for (const it of filtered) {
      const key = it.aid || `${it.n}__unmatched`;
      if (!byPerson.has(key)) byPerson.set(key, { name: it.n, aid: it.aid, dob: it.dob, items: [] });
      byPerson.get(key).items.push(it);
    }
    const groups = Array.from(byPerson.values());
    // 정렬: race 많은 사람 먼저, 동수면 최근 연도
    groups.sort((a, b) => b.items.length - a.items.length
      || (Math.max(...b.items.map((x) => x.y || 0)) - Math.max(...a.items.map((x) => x.y || 0))));
    const capGroups = groups.slice(0, MAX_RESULTS);
    $('#meta').textContent = q || filterRound
      ? `${filtered.length.toLocaleString()}건 · ${groups.length.toLocaleString()}명${groups.length > MAX_RESULTS ? ` · 상위 ${MAX_RESULTS}명 표시` : ''}`
      : `${items.length.toLocaleString()}건 (검색어 입력)`;

    const personHref = (g) =>
      (g.aid && g.dob) ? `/person/${encodeURIComponent(g.name + '-' + g.dob)}/`
                       : `/person.html?name=${encodeURIComponent(g.name)}`;

    const html = capGroups.map((g) => {
      const list = g.items.slice().sort((a, b) => (a.y || 0) - (b.y || 0));  // 최근이 아래로(오름차순)
      const parties = [...new Set(list.map((x) => x.p).filter(Boolean))].slice(0, 4);
      const years = list.map((x) => x.y).filter(Boolean);
      const yspan = years.length ? `${Math.min(...years)}–${Math.max(...years)}` : '';
      const wins = list.filter((x) => x.w).length;
      const meta = [];
      if (g.dob) meta.push(g.dob);
      if (g.aid) meta.push('국회');
      const metaTxt = meta.length ? meta.join(' · ') : (list.length === 1 ? list[0].r : '');
      // 회차 sub-rows → archive 직행. 당선/낙선 태그.
      const sub = list.map((it) => `
        <a class="s-sub${it.w ? '' : ' s-sub-lost'}" href="/archive/${it.e}/">
          <span class="s-sub-yr">${it.y || ''}</span>
          <span class="s-sub-rd">${it.r}</span>
          ${partyBadge(it.p)}
          <span class="s-sub-place">${escapeHtml(it.d)}</span>
          ${it.pct != null ? `<span class="s-sub-pct">${(+it.pct).toFixed(1)}%</span>` : ''}
          <span class="s-sub-tag ${it.w ? 's-won' : 's-lost'}">${it.w ? '당선' : '낙선'}</span>
        </a>`).join('');
      return `<li class="s-item s-group">
        <a class="s-link s-group-hdr" href="${personHref(g)}">
          <span class="s-name">${escapeHtml(g.name)}</span>
          <span class="s-group-count">${wins === list.length ? `${wins}회` : `당선 ${wins} · 출마 ${list.length}`} · ${yspan}</span>
          <span class="s-group-parties">${parties.map(partyBadge).join('')}</span>
          <span class="s-meta">${escapeHtml(metaTxt)}</span>
          <span class="s-group-arrow">인물 →</span>
        </a>
        <div class="s-sub-list">${sub}</div>
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
