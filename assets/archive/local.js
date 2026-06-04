// archive 지선 모드 — 광역단체장 17 시도.
// 사용: Archive.local.render(ctx).

(function () {
  const { SIDO_ORDER, ssh, pcol } = window.Archive;

  function sidoRaces(results) {
    return (results?.races || []).filter((r) => r.scope === 'sido' && r.sg_typecode === '3');
  }

  function renderHero(ctx) {
    const { results, polls } = ctx;
    if (polls) document.getElementById('ar-polls-count').textContent = polls.length.toLocaleString() + '건';
    if (!results?.races) return;
    const races = sidoRaces(results);
    const partyCount = {};
    let voters = 0, electors = 0;
    if (races.length) {
      // 시도별 race 있음 (NEC 또는 1회 위키) — 시도별 1위 정당 카운트
      for (const r of races) {
        const cands = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
        if (cands[0]) partyCount[cands[0].party] = (partyCount[cands[0].party] || 0) + 1;
        voters += r.voters || 0;
        electors += r.electors || 0;
      }
    } else {
      // 시도 race 없음 — nation 광역단체장 race로 fallback (옛 회차 위키 source)
      const nat3 = (results.races || []).find((r) => r.scope === 'nation' && r.sg_typecode === '3');
      if (nat3) {
        for (const c of nat3.candidates || []) {
          if (c.party && c.seats) partyCount[c.party] = (partyCount[c.party] || 0) + c.seats;
        }
        voters = nat3.voters || 0;
        electors = nat3.electors || 0;
      }
    }
    const sorted = Object.entries(partyCount).sort((a, b) => b[1] - a[1]).slice(0, 3);
    const govEl = document.getElementById('ar-governor-summary');
    if (sorted.length && govEl) {
      govEl.innerHTML = sorted.map(([p, c]) =>
        `<span style="color:${pcol(p)};margin-right:6px"><b>${c}</b> ${p}</span>`).join('');
    }
    if (electors > 0) document.getElementById('ar-turnout').textContent = (voters / electors * 100).toFixed(1) + '%';
    const meta = results._meta || {};
    const sourceLabel = meta.source === 'wikipedia-ko-infobox' || meta.source === 'wikipedia-ko-body'
      ? '위키' : (meta.source === 'nec-live-portal' ? '잠정' : (meta.is_final ? '확정' : '진행'));
    document.getElementById('ar-status').textContent = `${sourceLabel} 결과 · 갱신 ${meta.fetched_at || meta.election_date || '미상'}`;
  }

  function renderCounting(ctx) {
    const races = sidoRaces(ctx.results);
    if (!races.length) return;
    const host = document.getElementById('ar-counting-grid');
    for (const r of races) {
      const cands = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      const top = cands[0];
      const electors = r.electors || 0, voted = r.voters || 0;
      const turnout = electors > 0 ? (voted / electors * 100) : 0;
      const countPct = r.count_pct != null ? r.count_pct : null;  // 개표율 (NEC GAEPYOYUL)
      const col = top ? pcol(top.party) : '#999';
      // bar는 1위 후보 득표율 (시각적 우열). 진행 중이면 count_pct가 별도 라벨로.
      const barW = top?.pct != null ? top.pct : turnout;
      const cell = document.createElement('div');
      cell.className = 'ar-count-cell';
      const tail = countPct != null && countPct < 99.5
        ? `<span class="ar-count-pct">개표 ${countPct.toFixed(1)}%</span>`
        : (electors > 0 ? `<span class="ar-count-pct">투표율 ${turnout.toFixed(1)}%</span>` : '');
      cell.innerHTML = `
        <div class="ar-count-sido">${ssh(r.sido)}</div>
        <div class="ar-count-bar"><span class="ar-count-fill" style="width:${barW.toFixed(1)}%;background:${col}"></span></div>
        <div class="ar-count-meta">
          ${top ? `<span style="color:${col};font-weight:700">${top.party} ${top.pct?.toFixed(1) || ''}</span>` : '—'}
          ${tail}
        </div>
      `;
      host.appendChild(cell);
    }
    document.getElementById('ar-counting').hidden = false;
  }

  function renderPrediction(ctx) {
    const { results, polls } = ctx;
    if (!results?.races || !polls) return;
    const races = sidoRaces(results);
    if (!races.length) return;
    const actual = {};
    for (const r of races) {
      const cands = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      if (cands[0]) actual[r.sido] = { party: cands[0].party, name: cands[0].name, pct: cands[0].pct };
    }
    const predicted = {};
    for (const p of polls) {
      if (p.office_level !== '광역단체장') continue;
      const sido = p.sido;
      const cands = (p.candidates || []).slice().sort((a, b) => (b.pct || 0) - (a.pct || 0));
      if (!cands[0]) continue;
      const prev = predicted[sido];
      if (!prev || (p.period_end || '') > (prev._period_end || '')) {
        predicted[sido] = { party: cands[0].party, name: cands[0].name, pct: cands[0].pct, _period_end: p.period_end };
      }
    }
    const host = document.getElementById('ar-prediction-grid');
    let hasAny = false;
    for (const sido of SIDO_ORDER) {
      const a = actual[sido], p = predicted[sido];
      if (!a && !p) continue;
      hasAny = true;
      const hit = a && p && a.party === p.party;
      const partyHTML = (party, pct) => {
        if (!party) return '<span class="party" style="color:#999">—</span>';
        return `<span class="party" style="color:${pcol(party)}">${party}</span>${pct != null ? ` <span class="pct">${pct.toFixed(1)}%</span>` : ''}`;
      };
      const cell = document.createElement('div');
      cell.className = 'ar-pred-cell ' + (a && p ? (hit ? 'is-hit' : 'is-miss') : '');
      cell.innerHTML = `
        <div class="ar-pred-sido">${ssh(sido)}</div>
        <div class="ar-pred-row"><span class="lbl">예측</span><span>${partyHTML(p?.party, p?.pct)}</span></div>
        <div class="ar-pred-row"><span class="lbl">실제</span><span>${partyHTML(a?.party, a?.pct)}</span></div>
        ${a && p && a.pct != null && p.pct != null ? `<div class="ar-pred-result">오차 ${Math.abs(a.pct - p.pct).toFixed(1)}pp ${hit ? '· 적중 ✓' : '· 빗나감 ❌'}</div>` : ''}
      `;
      host.appendChild(cell);
    }
    if (hasAny) document.getElementById('ar-prediction').hidden = false;
  }

  function renderExitPoll(ctx) {
    const { exitData, results } = ctx;
    if (!exitData?.sources) return;
    const host = document.getElementById('ar-exitpoll-grid');
    const now = new Date();
    const blocks = [];
    for (const ep of exitData.sources) {
      const qa = ep.quote_after ? new Date(ep.quote_after) : null;
      if (qa && now < qa) continue;
      if (!ep.results || !Object.keys(ep.results).length) continue;
      blocks.push(ep);
    }
    if (!blocks.length) return;
    const actual = {};
    if (results?.races) {
      for (const r of sidoRaces(results)) {
        const cs = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
        if (cs[0]) actual[r.sido] = { party: cs[0].party, pct: cs[0].pct };
      }
    }
    for (const ep of blocks) {
      const card = document.createElement('div');
      card.className = 'ar-exit-block';
      card.innerHTML = `<h3 class="ar-exit-source">${ep.name || ep.key}</h3>`;
      const grid = document.createElement('div');
      grid.className = 'ar-exit-rows';
      for (const sido of SIDO_ORDER) {
        const e = (ep.results || {})[sido];
        if (!e?.[0]) continue;
        const top = e[0];
        const a = actual[sido];
        const hit = a && a.party === top.party;
        const row = document.createElement('div');
        row.className = 'ar-exit-row ' + (a ? (hit ? 'is-hit' : 'is-miss') : '');
        const col = pcol(top.party);
        row.innerHTML = `
          <span class="ar-exit-sido">${ssh(sido)}</span>
          <span class="ar-exit-pred" style="color:${col}">${top.party} ${top.pct?.toFixed(1) || ''}</span>
          ${a ? `<span class="ar-exit-actual">실제 ${a.party} ${a.pct?.toFixed(1) || ''}${hit ? ' ✓' : ' ✗'}</span>` : ''}
        `;
        grid.appendChild(row);
      }
      card.appendChild(grid);
      host.appendChild(card);
    }
    document.getElementById('ar-exitpoll').hidden = false;
  }

  async function renderByelection(ctx) {
    const reasons = ctx.byReasons || [];
    // 통합 동시 재보궐 결과 — byelectionId 메타가 있으면 fetch
    let byResults = null;
    if (ctx.meta.byelectionId) {
      try {
        byResults = await fetch(`data/results/${ctx.meta.byelectionId}.json`).then((r) => r.ok ? r.json() : null);
      } catch {}
    }
    const races = (byResults?.races || []).filter((r) => r.scope === 'district' && r.sg_typecode === '2');
    const cntEl = document.getElementById('ar-byelection-count');
    if (cntEl) {
      const parts = [];
      if (races.length) parts.push(`결과 ${races.length}`);
      if (reasons.length) parts.push(`사유 ${reasons.length}`);
      cntEl.textContent = parts.length ? parts.join(' · ') : '데이터 대기';
    }
    if (!races.length && !reasons.length) return;
    const host = document.getElementById('ar-byelection-host');

    // 결과 mini 카드 (먼저 — 핵심 정보)
    for (const race of races) {
      const cs = (race.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      const top = cs[0], second = cs[1];
      if (!top) continue;
      const margin = second ? (top.pct - second.pct) : null;
      const card = document.createElement('div');
      card.className = 'ar-by-card ar-by-result-card';
      const col = pcol(top.party);
      card.innerHTML = `
        <div class="ar-by-elpc">${race.sido || ''} ${race.district || race.sigungu || ''}</div>
        <div class="ar-by-result-winner" style="border-left:3px solid ${col}">
          <span style="color:${col};font-weight:700">${top.name}</span>
          <span style="color:${col};font-size:11px">${top.party}</span>
          <span style="font-weight:700;font-variant-numeric:tabular-nums">${(top.pct || 0).toFixed(2)}%</span>
        </div>
        ${second ? `<div class="ar-by-result-second">2위 <span style="color:${pcol(second.party)};font-weight:600">${second.name}</span> <span style="font-size:11px">${second.party}</span> <span style="font-variant-numeric:tabular-nums">${(second.pct || 0).toFixed(2)}%</span></div>` : ''}
        ${margin != null ? `<div style="font-size:11px;color:var(--ink-soft);margin-top:4px">격차 ${margin.toFixed(2)}pp</div>` : ''}
      `;
      host.appendChild(card);
    }

    // 사유 카드 (결과와 비교용)
    for (const r of reasons) {
      if (r.elctKndCd !== '2') continue;
      const card = document.createElement('div');
      card.className = 'ar-by-card';
      const col = r.plprNm ? pcol(r.plprNm) : '#999';
      card.innerHTML = `
        <div class="ar-by-elpc">${r.ctpvNm || ''} ${r.elpcNm || ''}</div>
        <div class="ar-by-reason">${r.rsn || ''}</div>
        <div style="font-size:12px;margin-top:4px">전임 <span style="color:${col};font-weight:700">${r.trprNm || '—'}</span> (${r.plprNm || '—'})</div>
        ${r.rsnOcrnYmd ? `<div style="font-size:11px;color:var(--ink-soft);margin-top:2px">사유 발생 ${r.rsnOcrnYmd}</div>` : ''}
      `;
      host.appendChild(card);
    }

    // 활성 회차면 byelection.html 진입 link, archive면 cross-archive link
    if (races.length || reasons.length) {
      const link = document.createElement('a');
      link.className = 'ar-by-more-link';
      link.href = '/byelection.html';
      link.textContent = '재·보궐 여론조사·결과 상세 →';
      host.appendChild(link);
    }

    document.getElementById('ar-byelection').hidden = false;
  }

  function renderTrend(ctx) {
    const { polls } = ctx;
    if (!polls?.length) return;
    const bySido = {};
    for (const p of polls) {
      if (!p.sido) continue;
      bySido[p.sido] = (bySido[p.sido] || 0) + 1;
    }
    const host = document.getElementById('ar-trend-host');
    const sorted = Object.entries(bySido).sort((a, b) => b[1] - a[1]);
    host.innerHTML = '<div style="font-weight:700;color:var(--ink);margin-bottom:8px">시도별 여론조사 건수</div>'
      + sorted.map(([s, c]) => `<div style="display:flex;justify-content:space-between;margin:2px 0"><span>${s}</span><span style="color:var(--ink);font-weight:600">${c}건</span></div>`).join('');
    document.getElementById('ar-polls-trend').hidden = false;
  }

  window.Archive.local = {
    async render(ctx) {
      renderHero(ctx);
      renderCounting(ctx);
      renderExitPoll(ctx);
      renderPrediction(ctx);
      await renderByelection(ctx);
      renderTrend(ctx);
    },
  };
})();
