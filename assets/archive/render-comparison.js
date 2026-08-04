// 이전 회차 대비 변화 — data/comparisons/{current}__{previous}.json.
//
// 이 섹션이 페이지의 성격을 바꾼다. 다른 섹션이 '이 선거에 무슨 데이터가 있나'에 답한다면
// 여기는 '무엇이 달라졌나'에 답한다.
//
// 계산값이므로 polis 계산 칩을 단다(docs/trust-states.md). 그리고 비교하지 않은 단위를
// 반드시 함께 보인다 — 통합·개편으로 짝이 없는 단위를 조용히 빼면 실제로 일어나지 않은
// 변화가 만들어진다(광주+전남 → 전남광주 통합이 '민주당 -1'로 보이는 식).
(function () {
  const HOST = 'ar-compare-host';
  const SECTION = 'ar-compare-section';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  const pcol = (p) => (typeof partyColor === 'function' ? partyColor(p) : 'var(--ink-soft)');
  const sign = (n) => (n > 0 ? `+${n}` : String(n));

  // 정당별 증감 — 색은 정당 정체성이라 여기서는 정당색을 쓴다(신뢰 상태와 다른 축).
  function deltaRow(label, delta, note) {
    const items = Object.entries(delta || {}).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    if (!items.length) return '';
    const chips = items.map(([p, n]) =>
      `<span class="cmp-delta"><i style="background:${pcol(p)}"></i>${esc(p)}
        <b class="${n > 0 ? 'is-up' : 'is-down'}">${sign(n)}</b></span>`).join('');
    return `<div class="cmp-row"><div class="cmp-row-label">${esc(label)}
      ${note ? `<span class="cmp-note">${esc(note)}</span>` : ''}</div>
      <div class="cmp-chips">${chips}</div></div>`;
  }

  function flipList(office) {
    // outcome 기준 — '무소속→무소속'은 정당이 바뀐 게 아니라 정당이 없는 것이라 뺀다.
    const flips = (office.units || []).filter((u) => u.outcome === 'party_flip');
    if (!flips.length) return '';
    const rows = flips.map((u) => `<li>
      <span class="cmp-unit">${esc(u.unit)}</span>
      <span class="cmp-swap"><i style="background:${pcol(u.prev_party)}"></i>${esc(u.prev_party)}
        <span class="cmp-arrow">→</span>
        <i style="background:${pcol(u.cur_party)}"></i>${esc(u.cur_party)}</span>
    </li>`).join('');
    return `<details class="cmp-flips"><summary>정당이 바뀐 곳 ${flips.length}</summary>
      <ul class="cmp-flip-list">${rows}</ul></details>`;
  }

  function notCompared(all) {
    const rows = [];
    for (const o of all) {
      for (const x of o.not_compared || []) {
        rows.push(`<li><span class="cmp-unit">${esc(x.unit)}</span>
          <span class="cmp-reason">${esc(x.note || x.reason)}</span></li>`);
      }
    }
    if (!rows.length) return '';
    return `<details class="cmp-excluded"><summary>비교하지 않은 단위 ${rows.length}</summary>
      <p class="cmp-excluded-why">행정구역이 통합·신설·이관돼 지난 회차와 짝을 지을 수 없는
        단위입니다. 빼고 세면 실제로 없던 변화가 만들어지므로 따로 밝힙니다.</p>
      <ul class="cmp-flip-list">${rows.join('')}</ul></details>`;
  }

  // 단독 선출직은 단위 대조가 되고, 의회는 선거구 획정이 달라 합계만 된다.
  // 순서는 페이지의 다른 결과 섹션과 같게 — 광역 → 기초.
  const OFFICE_ORDER = ['3', '4'];

  function officeBlock(o) {
    const n = o.counts;
    const excluded = n.previous_unmatched + n.current_unmatched;
    const stat = (v, label, extra) => `<div class="cmp-stat">
      <b class="cmp-stat-n">${v}</b><span class="cmp-stat-l">${esc(label)}</span>
      ${extra ? `<span class="cmp-stat-x">${esc(extra)}</span>` : ''}</div>`;
    const indep = n.independent_to_independent
      ? stat(n.independent_to_independent, '무소속 → 무소속', '같은 정당은 아님') : '';
    return `<div class="cmp-office">
      <h3 class="cmp-office-title">${esc(o.label)}</h3>
      <div class="cmp-stats">
        ${stat(n.party_flip, '정당이 바뀐 곳')}
        ${stat(n.party_hold, '같은 정당 유지')}
        ${indep}
        ${excluded ? stat(excluded, '직접 비교 불가', '행정구역 변경') : ''}
      </div>
      ${deltaRow('정당 증감', o.delta_compared_only, '직접 비교 가능한 곳만')}
      ${flipList(o)}
      ${notCompared([o])}
    </div>`;
  }

  async function render(ctx) {
    const sec = document.getElementById(SECTION);
    const host = document.getElementById(HOST);
    if (!sec || !host) return;
    const prev = ctx?.meta?.comparePrevious;
    if (!prev || !ctx?.meta?.id) return;
    let d;
    try {
      d = await fetch(`data/comparisons/${ctx.meta.id}__${prev}.json`)
        .then((r) => (r.ok ? r.json() : null));
    } catch { return; }
    if (!d || !d.offices) return;

    const t = d.turnout || {};
    const parts = [`<p class="cmp-head"><b>${esc(d._meta.previous_name || prev)}</b>와 비교
      ${t.delta != null ? `· 투표율 ${t.previous}% → <b>${t.current}%</b>
        <span class="${t.delta > 0 ? 'is-up' : 'is-down'}">${sign(t.delta)}%p</span>` : ''}</p>`];

    for (const tc of OFFICE_ORDER) {
      if (d.offices[tc]) parts.push(officeBlock(d.offices[tc]));
    }

    // 의회는 선거구가 바뀌어 단위 대조를 하지 않는다 — 합계 증감만, 그 사실을 함께 밝힌다.
    const councils = Object.values(d.councils || {});
    if (councils.length) {
      parts.push(`<div class="cmp-office"><h3 class="cmp-office-title">지방의회 의석</h3>
        ${councils.map((c) => deltaRow(c.label, c.delta, '선거구 획정이 달라 합계만 비교')).join('')}
      </div>`);
    }

    const chip = (window.Trust && window.Trust.fieldChip)
      ? window.Trust.fieldChip('calculated',
        '두 회차 결과에서 polis가 계산한 값입니다. 같은 이름·같은 경계의 단위끼리만 대조합니다.')
      : '';
    parts.push(`<p class="cmp-foot">${chip} 정당 증감은 통합·개편 단위를 뺀
      <b>직접 비교 가능한 곳</b> 기준입니다. 전체 단위 수 변화는 별도입니다.</p>`);

    host.innerHTML = parts.filter(Boolean).join('');
    sec.hidden = false;
  }

  window.Archive = window.Archive || {};
  window.Archive.comparison = { render };
})();
