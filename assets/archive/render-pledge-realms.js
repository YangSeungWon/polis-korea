// 회차별 공약 분야 분포 — data/pledges/realm-summary.json.
//
// 형태: 분야별 건수 내림차순 가로 막대. 계열이 하나(건수)뿐이라 색은 한 가지만 쓰고,
// 분야의 정체성은 색이 아니라 왼쪽 라벨이 갖는다. 12개 분야에 12색을 배정하면 서로
// 구분되지도 않고 색맹 안전성도 확보할 수 없다. 범례도 없다 — 계열이 하나라 불필요.
//
// 막대마다 건수·비중을 직접 붙여 값이 색에만 의존하지 않게 하고, 호버에 정당별 내역을 준다.
(function () {
  const HOST = 'ar-pledge-realm-host';
  const SECTION = 'ar-pledge-realm-section';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function row(r, max, total) {
    const pct = total ? (r.n / total * 100) : 0;
    const w = max ? (r.n / max * 100) : 0;
    const tip = (r.parties || [])
      .map((p) => `${esc(p.party)} ${p.n}`).join(' · ');
    return `<div class="pr-row" tabindex="0" title="${esc(r.realm)} — ${r.n}건 (${pct.toFixed(1)}%)${tip ? '\n' + tip : ''}">
      <div class="pr-label">${esc(r.realm)}</div>
      <div class="pr-track"><div class="pr-bar" style="width:${w.toFixed(1)}%"></div></div>
      <div class="pr-val">${r.n.toLocaleString()}<span class="pr-pct">${pct.toFixed(1)}%</span></div>
    </div>`;
  }

  async function render(ctx) {
    const sec = document.getElementById(SECTION);
    const host = document.getElementById(HOST);
    if (!sec || !host) return;                    // 이 회차 템플릿에 섹션이 없으면 조용히 끝
    const eid = ctx?.meta?.id;
    if (!eid) return;
    let all;
    try {
      all = await fetch('data/pledges/realm-summary.json').then((r) => r.ok ? r.json() : null);
    } catch { return; }
    const d = all && all[eid];
    if (!d || !(d.realms || []).length) return;   // 공약 없는 회차(총선 등) — 섹션 숨김 유지

    const total = d.realms.reduce((s, r) => s + r.n, 0);
    const max = Math.max(...d.realms.map((r) => r.n));
    // 무엇을 세었는지 먼저 밝힌다 — 당선인만인지 전 후보인지에 따라 분포가 달라진다.
    const who = d.roster_scope === 'all_candidates' ? '등록 후보' : '당선인';
    const note = `${who} ${d.n_people.toLocaleString()}명 · 공약 ${d.n_pledges.toLocaleString()}건`
      + (d.n_unclassified ? ` · 미분류 ${d.n_unclassified.toLocaleString()}건 제외` : '');
    host.innerHTML = `<p class="pr-note">${esc(note)}</p>
      <div class="pr-chart">${d.realms.map((r) => row(r, max, total)).join('')}</div>
      <p class="pr-fine">분야는 NEC 원본이 비어 있어 공약 제목·본문에서 자동 추정한 값입니다
        (대표 분야 1개 기준). 추정이라 오분류가 있을 수 있습니다.</p>`;
    sec.hidden = false;
  }

  window.Archive = window.Archive || {};
  window.Archive.pledgeRealms = { render };
})();
