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
    // 차트 합계가 공약 수와 다른 이유를 먼저 말한다. '미분류 N건 제외'라고 쓰면
    // 사용자는 10건을 분모로 잡고 '왜 2건이 22.2%지?' 하게 된다 — 실제 분모는 9건이다.
    // 알고 싶은 건 처리 로직(제외했다)이 아니라 분모가 얼마인가다.
    // note에 <b>를 쓰므로 값은 숫자로 강제한다 — 문자열이 그대로 들어가면 마크업이 샌다.
    const num = (v) => (Number(v) || 0).toLocaleString();
    const note = `${who} ${num(d.n_people)}명 · `
      + (d.n_unclassified
        ? `공약 ${num(d.n_pledges)}건 중 <b>${num(total)}건 분류</b>`
          + ` · 미분류 ${num(d.n_unclassified)}건`
        : `공약 ${num(d.n_pledges)}건`);
    // 출처·가공 여부는 신뢰 문법의 값 단위 칩으로 — 문장으로 세 번 반복하지 않는다.
    const chip = (window.Trust && window.Trust.fieldChip)
      ? window.Trust.fieldChip('autoClassified') : '';
    host.innerHTML = `<p class="pr-note">${note}</p>
      <div class="pr-chart">${d.realms.map((r) => row(r, max, total)).join('')}</div>
      <p class="pr-fine">${chip} NEC 원문에 분야 정보가 없어 공약 제목과 본문을 바탕으로
        분류했습니다. 공약마다 대표 분야 1개를 적용했으며, 일부 오분류가 있을 수 있습니다.</p>`;
    sec.hidden = false;
  }

  window.Archive = window.Archive || {};
  window.Archive.pledgeRealms = { render };
})();
