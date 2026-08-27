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
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    for (const r of races) {
      const sd = canon(r.sido || '');   // 옛 강원도·전라북도 → 현 강원특별자치도·전북특별자치도(레이아웃 키와 일치)
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
    // hex/dorling 셀 클릭 → 당선인 섹션 그 시도(광역의원)로 필터·스크롤.
    const onSelect = (sido) => window.Archive.winners && window.Archive.winners.focus({ sido, level: '광역의원' });
    const modes = [
      { key: 'hex', label: '균등', draw: (el) => { agg = SC.drawHex(el, bySidoObj, { onSelect }); } },
      { key: 'dorling', label: '원형', draw: (el) => { agg = SC.drawDorling(el, bySidoObj, { onSelect }); } },
    ];
    if (window.Archive.sidoView && typeof window.Archive.sidoView.mount === 'function') window.Archive.sidoView.mount(host, modes, null, { hostKey: 'metro' });
    else { agg = SC.drawHex(host, bySidoObj, { onSelect }); }
    const { totalSeats, partyTotal } = agg || { totalSeats: 0, partyTotal: new Map() };
    const legend = document.getElementById('ar-metro-hex-legend');
    if (legend) {
      const sorted = Array.from(partyTotal.entries()).sort((a, b) => b[1] - a[1]);
      legend.innerHTML = sorted.map(([p, n]) => {
        const col = (typeof partyTextColor === 'function') ? partyTextColor(p) : '#999';
        return `<span class="mh-leg" style="color:${col}"><b>${n}</b> ${p}</span>`;
      }).join(' · ');
      const tot = document.getElementById('ar-metro-hex-total');
      if (tot) tot.textContent = `${totalSeats}석 (시·도의회) · hex 클릭 → 당선인`;
    }
  }

  // 광역의원 비례 — 시·도별 정당 득표(표심). 의석(지역구 승자독식 과대대표) 아닌 실제 표심.
  //   tc=8(proportional_sido) 정당 득표를 시도 표비례(sidoProp 격자/원형)로. 의석 섹션 뒤에 주입.
  async function initProp(ctx) {
    const races = (ctx?.results?.races || []).filter(
      (r) => r.sg_typecode === '8' && r.scope === 'proportional_sido' && (r.candidates || []).length);
    if (races.length < 2) return;
    const SP = window.Archive.sidoProp, SV = window.Archive.sidoView;
    if (!SP || !SV) return;
    const base = document.getElementById('ar-metro-hex');
    const anchor = base?.closest('.ar-section') || base?.parentElement;
    if (!anchor || !anchor.parentElement) return;
    let sec = document.getElementById('ar-metro-prop');
    if (!sec) {
      sec = document.createElement('section');
      sec.className = 'ar-section'; sec.id = 'ar-metro-prop';
      sec.innerHTML = '<h2 class="ar-section-title">광역의원 비례 — 시·도별 표심'
        + '<span class="info-i" tabindex="0" role="button" aria-label="설명">i<span class="info-pop">비례대표 정당 득표를 시·도별로 — 의석(지역구 승자독식)이 가린 실제 정당 지지.</span></span></h2>'
        + '<div class="ar-metro-prop-host"></div>';
      anchor.parentElement.insertBefore(sec, anchor.nextSibling);
    }
    const host = sec.querySelector('.ar-metro-prop-host');
    const onSelect = (sido) => window.Archive.winners && window.Archive.winners.focus({ sido, level: '광역의원' });
    const modes = [
      { key: 'grid', label: '격자', draw: (el) => SP.drawGrid(el, races, { onSelect }) },
      { key: 'dorling', label: '원형', draw: (el) => SP.drawDorling(el, races, { onSelect }) },
    ];
    SV.mount(host, modes, null, { hostKey: 'metro-prop' });
  }

  window.Archive = window.Archive || {};
  window.Archive.metroHex = { init, initProp };
})();
