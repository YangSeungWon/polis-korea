// 시도의회 광역의원 의석 분포 — 시도 중심에 의석 spiral.
// 부모 = sigungu_hex의 시도별 centroid. 자식 = 광역의원 N석 spiral.
// 데이터: tc=5(지역구) + tc=8(비례). 8회+ sido_summary, 9회는 race winner 1로 fallback.

(function () {
  const NS = 'http://www.w3.org/2000/svg';
  // 시도별 광역의원 (지역구·비례) by party
  function aggregateMetroSeats(races) {
    const bySido = new Map();
    function add(sd, party, n) {
      if (!n) return;
      const m = bySido.get(sd) || new Map();
      m.set(party, (m.get(party) || 0) + n);
      bySido.set(sd, m);
    }
    for (const r of races) {
      const sd = r.sido || '';
      if (r.sg_typecode === '5') {
        if (r.scope === 'sido_summary') {
          for (const c of r.candidates || []) add(sd, c.party || '무소속', c.seats || 0);
        } else if (r.scope === 'district') {
          // 당선자 전원 — 전남광주통합 시도의회는 중선거구(1선거구 2~4명). won 없으면 top-1 fallback.
          const wonCs = (r.candidates || []).filter((c) => c.won);
          if (wonCs.length) {
            for (const c of wonCs) add(sd, c.party || '무소속', 1);
          } else {
            const top = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0))[0];
            if (top) add(sd, top.party || '무소속', 1);
          }
        }
      } else if (r.sg_typecode === '8' && r.scope === 'proportional_sido') {
        for (const c of r.candidates || []) add(sd, c.party || '무소속', c.seats || 0);
      }
    }
    return bySido;
  }

  async function init(ctx) {
    const host = document.getElementById('ar-metro-hex');
    if (!host) return;
    const races = ctx?.results?.races || [];
    const seats = aggregateMetroSeats(races);
    if (seats.size === 0) {
      host.parentElement?.setAttribute('hidden', '');
      return;
    }
    host.parentElement?.removeAttribute('hidden');
    // dorling용 {시도:{party:count}} (병합 시도 제외 — SIDO_HEX_LAYOUT 키 기준)
    const bySidoObj = {};
    for (const [sd, m] of seats) bySidoObj[sd] = Object.fromEntries(m);
    let agg = null;
    // 헥스·dorling 모두 공유 sidoCluster — 같은 layout/viewBox라 토글해도 권역 위치 고정.
    const SC = window.Archive.sidoCluster;
    const modes = [
      { key: 'hex', label: '헥스', draw: (el) => { agg = SC.drawHex(el, bySidoObj); } },
      { key: 'dorling', label: 'dorling', draw: (el) => { agg = SC.drawDorling(el, bySidoObj); } },
    ];
    if (window.Archive.sidoView && typeof window.Archive.sidoView.mount === 'function') window.Archive.sidoView.mount(host, modes);
    else { agg = SC.drawHex(host, bySidoObj); }
    const { totalSeats, partyTotal } = agg || { totalSeats: 0, partyTotal: new Map() };
    const legend = document.getElementById('ar-metro-hex-legend');
    if (legend) {
      const sorted = Array.from(partyTotal.entries()).sort((a, b) => b[1] - a[1]);
      legend.innerHTML = sorted.map(([p, n]) => {
        const col = (typeof partyColor === 'function') ? partyColor(p) : '#999';
        return `<span class="mh-leg" style="color:${col}"><b>${n}</b> ${p}</span>`;
      }).join(' · ');
      const tot = document.getElementById('ar-metro-hex-total');
      if (tot) tot.textContent = `${totalSeats}석 (시·도의회) · hex 클릭 → 당선인`;
    }
  }

  window.Archive = window.Archive || {};
  window.Archive.metroHex = { init };
})();
