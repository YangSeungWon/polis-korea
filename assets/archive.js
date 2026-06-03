// archive 회차 페이지 — window.__ARCHIVE__ 메타 기반.
// 결과·여론조사·재보궐 데이터 fetch 후 점진 렌더. 데이터 없으면 섹션 hidden.

(async function() {
  const meta = window.__ARCHIVE__ || {};
  if (!meta.id) return;
  const $ = (s) => document.querySelector(s);

  // 1. 결과 데이터
  let results = null;
  try {
    results = await fetch(meta.resultsPath, { cache: 'no-cache' }).then((r) => r.ok ? r.json() : null);
  } catch { results = null; }

  // 2. 폴 데이터 (aggregated)
  let polls = null;
  try {
    const all = await fetch('data/polls/aggregated.json').then((r) => r.json());
    polls = (all.polls || []).filter(filterPollForArchive);
  } catch { polls = null; }

  // 3. 재보궐 사유
  let byReasons = [];
  try {
    const br = await fetch('data/byelection_reasons.json').then((r) => r.json());
    // 9회 재보궐 = 2026-06-03 실시일
    byReasons = (br.reasons || []).filter((r) => r.elctYmd === meta.date.replace(/-/g, ''));
  } catch {}

  renderHero(results, polls);
  renderPrediction(results, polls);
  renderPollsList(polls);
  renderByelection(byReasons, results);
  renderTrend(polls);

  // === 필터 ===
  function filterPollForArchive(p) {
    // 9회 지선 폴만 — period가 2025~2026 + office_level 광역단체장 위주
    const ps = (p.period_start || '');
    if (!ps) return false;
    // 9회 지선 관련 시기: 2025-12 ~ 2026-05 까지
    if (ps < '2025-09-01' || ps > '2026-06-03') return false;
    return true;
  }

  // === Hero stats ===
  function renderHero(results, polls) {
    if (polls) document.getElementById('ar-polls-count').textContent = polls.length.toLocaleString() + '건';
    // 결과 들어왔으면 광역단체장 정당 분포
    if (results?.races) {
      const sidoRace = results.races.filter((r) => r.scope === 'sido' && r.sg_typecode === '3');
      const partyCount = {};
      let turnoutTotal = 0, voters = 0, electors = 0;
      for (const r of sidoRace) {
        const cands = (r.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0));
        if (cands[0]) partyCount[cands[0].party] = (partyCount[cands[0].party] || 0) + 1;
        voters += r.voters || 0;
        electors += r.electors || 0;
      }
      const sorted = Object.entries(partyCount).sort((a, b) => b[1] - a[1]).slice(0, 3);
      if (sorted.length) {
        const govEl = document.getElementById('ar-governor-summary');
        govEl.innerHTML = sorted.map(([p, c]) => {
          const col = (typeof partyColor === 'function') ? partyColor(p) : '#999';
          return `<span style="color:${col};margin-right:6px"><b>${c}</b> ${p}</span>`;
        }).join('');
      }
      if (electors > 0) document.getElementById('ar-turnout').textContent = (voters / electors * 100).toFixed(1) + '%';
      document.getElementById('ar-status').textContent = `개표 완료 · ${results._meta?.fetched_at || '갱신 시각 미상'}`;
    }
  }

  // === 예측 vs 실제 (광역단체장) ===
  function renderPrediction(results, polls) {
    if (!results?.races || !polls) return;
    const sidoRace = results.races.filter((r) => r.scope === 'sido' && r.sg_typecode === '3');
    if (!sidoRace.length) return;
    // 시도별 actual top
    const actual = {};
    for (const r of sidoRace) {
      const cands = (r.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0));
      if (cands[0]) actual[r.sido] = { party: cands[0].party, name: cands[0].name, pct: cands[0].pct };
    }
    // 시도별 마지막 폴 1위 (office_level=광역단체장)
    const predicted = {};
    for (const p of polls) {
      if (p.office_level !== '광역단체장') continue;
      const sido = p.sido;
      const cands = (p.candidates || []).slice().sort((a, b) => (b.pct||0) - (a.pct||0));
      if (!cands[0]) continue;
      const prev = predicted[sido];
      if (!prev || (p.period_end || '') > (prev._period_end || '')) {
        predicted[sido] = { party: cands[0].party, name: cands[0].name, pct: cands[0].pct, _period_end: p.period_end };
      }
    }
    const sidoOrder = [
      '서울특별시','인천광역시','경기도','강원특별자치도',
      '세종특별자치시','대전광역시','충청북도','충청남도',
      '광주광역시','전북특별자치도','전라남도',
      '대구광역시','부산광역시','울산광역시','경상북도','경상남도',
      '제주특별자치도',
    ];
    const host = document.getElementById('ar-prediction-grid');
    let hasAny = false;
    for (const sido of sidoOrder) {
      const a = actual[sido], p = predicted[sido];
      if (!a && !p) continue;
      hasAny = true;
      const hit = a && p && a.party === p.party;
      const cell = document.createElement('div');
      cell.className = 'ar-pred-cell ' + (a && p ? (hit ? 'is-hit' : 'is-miss') : '');
      const sshort = (typeof SIDO_LABEL_SHORT !== 'undefined') ? (SIDO_LABEL_SHORT[sido] || sido) : sido;
      const partyHTML = (party, pct) => {
        if (!party) return '<span class="party" style="color:#999">—</span>';
        const col = (typeof partyColor === 'function') ? partyColor(party) : '#999';
        return `<span class="party" style="color:${col}">${party}</span>${pct != null ? ` <span class="pct">${pct.toFixed(1)}%</span>` : ''}`;
      };
      cell.innerHTML = `
        <div class="ar-pred-sido">${sshort}</div>
        <div class="ar-pred-row"><span class="lbl">예측</span><span>${partyHTML(p?.party, p?.pct)}</span></div>
        <div class="ar-pred-row"><span class="lbl">실제</span><span>${partyHTML(a?.party, a?.pct)}</span></div>
        ${a && p && a.pct != null && p.pct != null ? `<div class="ar-pred-result">오차 ${Math.abs(a.pct - p.pct).toFixed(1)}pp ${hit ? '· 적중 ✓' : '· 빗나감 ❌'}</div>` : ''}
      `;
      host.appendChild(cell);
    }
    if (hasAny) document.getElementById('ar-prediction').hidden = false;
  }

  // === 모든 여론조사 list ===
  function renderPollsList(polls) {
    if (!polls?.length) return;
    const host = document.getElementById('ar-polls-list-host');
    polls.slice().sort((a, b) => (b.period_end || '').localeCompare(a.period_end || ''))
         .slice(0, 60).forEach((p) => {
      const item = document.createElement('div');
      item.className = 'ar-poll-item';
      item.innerHTML = `
        <div class="agency">${p.agency || '—'}</div>
        <div class="period">${p.period_start || '?'} ~ ${p.period_end || '?'} · ${p.sido || ''} · n=${p.sample_size || '?'}</div>
      `;
      host.appendChild(item);
    });
    if (polls.length > 60) {
      const more = document.createElement('div');
      more.className = 'ar-poll-item';
      more.style.textAlign = 'center';
      more.style.color = 'var(--ink-mute)';
      more.textContent = `… 외 ${polls.length - 60}건`;
      host.appendChild(more);
    }
    document.getElementById('ar-polls-list').hidden = false;
  }

  // === 재보궐 ===
  function renderByelection(reasons, results) {
    document.getElementById('ar-byelection-count').textContent = reasons.length ? `${reasons.length}건` : '데이터 대기';
    if (!reasons.length) return;
    const host = document.getElementById('ar-byelection-host');
    for (const r of reasons) {
      if (r.elctKndCd !== '2') continue;  // 국회의원만
      const card = document.createElement('div');
      card.className = 'ar-by-card';
      const col = (typeof partyColor === 'function' && r.plprNm) ? partyColor(r.plprNm) : '#999';
      card.innerHTML = `
        <div class="ar-by-elpc">${r.ctpvNm || ''} ${r.elpcNm || ''}</div>
        <div class="ar-by-reason">${r.rsn || ''}</div>
        <div style="font-size:12px;margin-top:4px">전임 <span style="color:${col};font-weight:700">${r.trprNm || '—'}</span> (${r.plprNm || '—'})</div>
        ${r.rsnOcrnYmd ? `<div style="font-size:11px;color:var(--ink-soft);margin-top:2px">사유 발생 ${r.rsnOcrnYmd}</div>` : ''}
      `;
      host.appendChild(card);
    }
    document.getElementById('ar-byelection').hidden = false;
  }

  // === Trend (placeholder — 데이터 충분 시 시계열 차트) ===
  function renderTrend(polls) {
    if (!polls?.length) return;
    // 일단 시도별 폴 수만 표시
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
})();
