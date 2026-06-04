// archive 단독 재보궐 모드 — 같은 날 여러 office (광역단체장·기초단체장·국회의원·교육감) 동시.
// 사용: Archive.byelection.render(ctx).

(function () {
  const { SIDO_ORDER, ssh, pcol } = window.Archive;

  function racesBy(results, scope, tc) {
    return (results?.races || []).filter((r) => r.scope === scope && r.sg_typecode === tc);
  }

  // 사유 fetch + filter by 회차 날짜
  async function fetchReasons(date) {
    try {
      const j = await fetch('/data/byelection_reasons.json').then((r) => r.json());
      const ymd = date.replace(/-/g, '');
      return (j.reasons || []).filter((r) => r.elctYmd === ymd);
    } catch { return []; }
  }

  function renderHero(ctx, reasons) {
    const { results, meta } = ctx;
    const sido3 = racesBy(results, 'sido', '3');     // 광역단체장
    const sigungu4 = racesBy(results, 'sigungu', '4'); // 기초단체장
    const district2 = racesBy(results, 'district', '2'); // 국회의원
    const setN = (id, n) => { const el = document.getElementById(id); if (el) el.textContent = n ? `${n}건` : '—'; };
    setN('ar-by-sido-count', sido3.length);
    setN('ar-by-sigungu-count', sigungu4.length);
    setN('ar-by-district-count', district2.length);
    setN('ar-by-reasons-count', reasons.length);
    const m = results?._meta || {};
    const sourceLabel = m.source === 'nec-live-portal' ? '잠정' : (m.is_final ? '확정' : '진행');
    const status = document.getElementById('ar-status');
    if (status) status.textContent = `${sourceLabel} 결과 · 갱신 ${m.fetched_at || '미상'}`;
  }

  // 광역단체장 — 큰 카드. 보통 1~2건 (서울·부산 시장 같은).
  function renderSidoBig(ctx) {
    const races = racesBy(ctx.results, 'sido', '3');
    if (!races.length) return;
    const host = document.getElementById('ar-by-sido-host');
    host.innerHTML = '';
    for (const r of races) {
      const cands = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      const top = cands[0], second = cands[1];
      if (!top) continue;
      const electors = r.electors || 0, voted = r.voters || 0;
      const turnout = electors ? (voted / electors * 100) : 0;
      const col = pcol(top.party);
      const margin = second ? (top.pct - second.pct) : null;
      const card = document.createElement('div');
      card.className = 'ar-by-sido-card';
      card.innerHTML = `
        <h3 class="ar-by-sido-name">${r.sido}</h3>
        <div class="ar-by-sido-winner" style="border-left:4px solid ${col}">
          <span class="ar-by-sido-w-name" style="color:${col};font-weight:700">${top.name}</span>
          <span class="ar-by-sido-w-party" style="color:${col}">${top.party}</span>
          <span class="ar-by-sido-w-pct">${(top.pct || 0).toFixed(2)}%</span>
        </div>
        ${second ? `<div class="ar-by-sido-second">
          <span>2위 ${second.name}</span>
          <span style="color:${pcol(second.party)}">${second.party}</span>
          <span>${(second.pct || 0).toFixed(2)}%</span>
        </div>` : ''}
        ${margin != null ? `<div class="ar-by-sido-meta">격차 ${margin.toFixed(2)}pp · 투표율 ${turnout.toFixed(1)}%</div>` : ''}
      `;
      host.appendChild(card);
    }
    document.getElementById('ar-by-sido-section').hidden = false;
  }

  // 기초단체장 list — 시도별 그룹
  function renderSigunguList(ctx) {
    const races = racesBy(ctx.results, 'sigungu', '4');
    if (!races.length) return;
    const host = document.getElementById('ar-by-sigungu-host');
    const bySido = {};
    for (const r of races) (bySido[r.sido || '기타'] = bySido[r.sido || '기타'] || []).push(r);
    let html = '';
    for (const sido of SIDO_ORDER) {
      const list = bySido[sido];
      if (!list?.length) continue;
      html += `<div class="ar-dist-block"><h3 class="ar-dist-sido">${ssh(sido)} <span class="ar-dist-count">${list.length}건</span></h3><div class="ar-dist-rows">`;
      for (const r of list) {
        const cands = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
        const top = cands[0], second = cands[1];
        if (!top) continue;
        const col = pcol(top.party);
        const margin = second ? (top.pct - second.pct) : null;
        html += `<div class="ar-dist-row" style="border-left:3px solid ${col}">
          <span class="ar-dist-name">${r.sigungu}</span>
          <span class="ar-dist-cand" style="color:${col};font-weight:700">${top.name}</span>
          <span class="ar-dist-meta">${(top.pct || 0).toFixed(1)}${margin != null ? ` <span style="color:var(--ink-mute)">+${margin.toFixed(1)}</span>` : ''}</span>
        </div>`;
      }
      html += '</div></div>';
    }
    host.innerHTML = html;
    document.getElementById('ar-by-sigungu-section').hidden = false;
  }

  // 국회의원 list — 시도별 그룹 (총선 비슷)
  function renderDistrictList(ctx) {
    const races = racesBy(ctx.results, 'district', '2');
    if (!races.length) return;
    const host = document.getElementById('ar-by-district-host');
    const bySido = {};
    for (const r of races) (bySido[r.sido || '기타'] = bySido[r.sido || '기타'] || []).push(r);
    let html = '';
    for (const sido of SIDO_ORDER) {
      const list = bySido[sido];
      if (!list?.length) continue;
      html += `<div class="ar-dist-block"><h3 class="ar-dist-sido">${ssh(sido)} <span class="ar-dist-count">${list.length}건</span></h3><div class="ar-dist-rows">`;
      for (const r of list) {
        const cands = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
        const top = cands[0], second = cands[1];
        if (!top) continue;
        const col = pcol(top.party);
        const margin = second ? (top.pct - second.pct) : null;
        const name = r.district || r.sigungu || '?';
        html += `<div class="ar-dist-row" style="border-left:3px solid ${col}">
          <span class="ar-dist-name">${name}</span>
          <span class="ar-dist-cand" style="color:${col};font-weight:700">${top.name}</span>
          <span class="ar-dist-meta">${(top.pct || 0).toFixed(1)}${margin != null ? ` <span style="color:var(--ink-mute)">+${margin.toFixed(1)}</span>` : ''}</span>
        </div>`;
      }
      html += '</div></div>';
    }
    host.innerHTML = html;
    document.getElementById('ar-by-district-section').hidden = false;
  }

  function renderReasons(ctx, reasons) {
    if (!reasons.length) return;
    const host = document.getElementById('ar-by-reasons-host');
    // 종류별 그룹
    const KIND = { '2': '국회의원', '3': '광역단체장', '4': '기초단체장', '5': '광역의원', '6': '기초의원', '11': '교육감' };
    const byKind = {};
    for (const r of reasons) {
      const k = KIND[r.elctKndCd] || '기타';
      (byKind[k] = byKind[k] || []).push(r);
    }
    let html = '';
    for (const [kind, list] of Object.entries(byKind)) {
      html += `<div class="ar-rsn-block"><h3 class="ar-rsn-kind">${kind} <span class="ar-rsn-count">${list.length}건</span></h3><div class="ar-rsn-rows">`;
      for (const r of list) {
        const col = r.plprNm ? pcol(r.plprNm) : '#999';
        html += `<div class="ar-rsn-row">
          <span class="ar-rsn-loc">${r.ctpvNm} ${r.elpcNm || r.cmtNm || ''}</span>
          <span class="ar-rsn-prev"><span style="color:${col};font-weight:600">${r.trprNm || '—'}</span> <span class="ar-rsn-party">${r.plprNm || ''}</span></span>
          <span class="ar-rsn-rsn">${r.rsn || ''}</span>
        </div>`;
      }
      html += '</div></div>';
    }
    host.innerHTML = html;
    document.getElementById('ar-by-reasons-section').hidden = false;
  }

  // 의원 선거구 list (광역의원 tc=5 또는 기초의원 tc=6) — 시도별 그룹
  function renderMemberList(ctx, tc, hostId, sectionId) {
    const races = racesBy(ctx.results, 'district', tc);
    if (!races.length) return;
    const host = document.getElementById(hostId);
    const bySido = {};
    for (const r of races) (bySido[r.sido || '기타'] = bySido[r.sido || '기타'] || []).push(r);
    let html = '';
    for (const sido of SIDO_ORDER) {
      const list = bySido[sido];
      if (!list?.length) continue;
      html += `<div class="ar-dist-block"><h3 class="ar-dist-sido">${ssh(sido)} <span class="ar-dist-count">${list.length}건</span></h3><div class="ar-dist-rows">`;
      for (const r of list) {
        const cands = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
        const top = cands[0], second = cands[1];
        if (!top) continue;
        const col = pcol(top.party);
        const margin = second ? (top.pct - second.pct) : null;
        html += `<div class="ar-dist-row" style="border-left:3px solid ${col}">
          <span class="ar-dist-name">${r.district}</span>
          <span class="ar-dist-cand" style="color:${col};font-weight:700">${top.name}</span>
          <span class="ar-dist-meta">${(top.pct || 0).toFixed(1)}${margin != null ? ` <span style="color:var(--ink-mute)">+${margin.toFixed(1)}</span>` : ''}</span>
        </div>`;
      }
      html += '</div></div>';
    }
    host.innerHTML = html;
    document.getElementById(sectionId).hidden = false;
  }

  window.Archive.byelection = {
    async render(ctx) {
      const reasons = await fetchReasons(ctx.meta.date);
      renderHero(ctx, reasons);
      renderSidoBig(ctx);
      renderDistrictList(ctx);
      renderSigunguList(ctx);
      renderMemberList(ctx, '5', 'ar-by-sido-mem-host', 'ar-by-sido-mem-section');
      renderMemberList(ctx, '6', 'ar-by-sigungu-mem-host', 'ar-by-sigungu-mem-section');
      renderReasons(ctx, reasons);
    },
  };
})();
