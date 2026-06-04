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

  // 2. 폴 데이터 (회차별 path) — 메타의 pollsPath 우선, fallback aggregated.json.
  let polls = null;
  try {
    const path = meta.pollsPath || 'data/polls/aggregated.json';
    const all = await fetch(path).then((r) => r.json());
    polls = (all.polls || []).filter(filterPollForArchive);
  } catch { polls = null; }

  // 3. 재보궐 사유
  let byReasons = [];
  try {
    const br = await fetch('data/byelection_reasons.json').then((r) => r.json());
    byReasons = (br.reasons || []).filter((r) => r.elctYmd === meta.date.replace(/-/g, ''));
  } catch {}

  // 4. 출구조사 (방송 3사) — released_at 이후만 표시.
  let exitData = null;
  try {
    const path = meta.exitPollPath || `data/exit_polls/${meta.id}.json`;
    exitData = await fetch(path).then((r) => r.ok ? r.json() : null);
  } catch {}

  const isPres = meta.electionKind === 'presidential';
  const isGeneral = meta.electionKind === 'general_election' || meta.electionKind === 'national_assembly';
  const sgTypecode = meta.sgTypecode || (isPres ? '1' : isGeneral ? '2' : '3');

  if (isPres) {
    renderHeroPres(results, polls);
    renderNationPres(results);
    renderCountingPres(results);
    renderExitPollPres(exitData, results);
    renderTrendPres(polls);
  } else if (isGeneral) {
    renderHeroGeneral(results, polls);
    renderParliamentGeneral(results);
    renderProportionalGeneral(results);
    renderDistrictsGeneral(results);
    renderExitPollPres(exitData, results);  // 동일 schema 재사용 — 데이터 들어오면 동작
    renderTrendGeneral(polls);
  } else {
    renderHero(results, polls);
    renderCounting(results);
    renderExitPoll(exitData, results);
    renderPrediction(results, polls);
    renderByelection(byReasons, results);
    renderTrend(polls);
  }
  renderPollsList(polls);

  // === 필터 ===
  function filterPollForArchive(p) {
    // 메타의 pollsWindow 기준 — { start, end }. 지정 안 됐으면 1년 윈도.
    const ps = (p.period_start || '');
    if (!ps) return false;
    const w = meta.pollsWindow || {};
    const start = w.start || (() => { const d = new Date(meta.date); d.setFullYear(d.getFullYear() - 1); return d.toISOString().slice(0, 10); })();
    const end = w.end || meta.date;
    if (ps < start || ps > end) return false;
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
  function renderCounting(results) {
    if (!results?.races) return;
    const sidoRace = results.races.filter((r) => r.scope === 'sido' && r.sg_typecode === '3');
    if (!sidoRace.length) return;
    const host = document.getElementById('ar-counting-grid');
    for (const r of sidoRace) {
      const cands = (r.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0));
      const top = cands[0];
      const electors = r.electors || 0, voted = r.voters || 0;
      const pct = electors > 0 ? (voted / electors * 100) : 0;
      const cell = document.createElement('div');
      cell.className = 'ar-count-cell';
      const col = (top && typeof partyColor === 'function') ? partyColor(top.party) : '#999';
      const sshort = (typeof SIDO_LABEL_SHORT !== 'undefined') ? (SIDO_LABEL_SHORT[r.sido] || r.sido) : r.sido;
      cell.innerHTML = `
        <div class="ar-count-sido">${sshort}</div>
        <div class="ar-count-bar"><span class="ar-count-fill" style="width:${pct.toFixed(1)}%;background:${col}"></span></div>
        <div class="ar-count-meta">
          ${top ? `<span style="color:${col};font-weight:700">${top.party} ${top.pct?.toFixed(1) || ''}</span>` : '—'}
          <span class="ar-count-pct">${pct.toFixed(1)}% 개표</span>
        </div>
      `;
      host.appendChild(cell);
    }
    document.getElementById('ar-counting').hidden = false;
  }

  function renderExitPoll(exitData, results) {
    if (!exitData?.sources) return;
    const host = document.getElementById('ar-exitpoll-grid');
    const now = new Date();
    const blocks = [];
    for (const ep of exitData.sources) {
      const quoteAfter = ep.quote_after ? new Date(ep.quote_after) : null;
      if (quoteAfter && now < quoteAfter) continue;  // 인용 가능 시점 전 표시 X
      const hasData = ep.results && Object.keys(ep.results).length > 0;
      if (!hasData) continue;
      blocks.push({ ep });
    }
    if (!blocks.length) return;

    // 시도별 actual top (from results)
    const actual = {};
    if (results?.races) {
      const sidoRace = results.races.filter((r) => r.scope === 'sido' && r.sg_typecode === '3');
      for (const r of sidoRace) {
        const cs = (r.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0));
        if (cs[0]) actual[r.sido] = { party: cs[0].party, pct: cs[0].pct };
      }
    }

    for (const { ep } of blocks) {
      const card = document.createElement('div');
      card.className = 'ar-exit-block';
      card.innerHTML = `<h3 class="ar-exit-source">${ep.source}</h3>`;
      const grid = document.createElement('div');
      grid.className = 'ar-exit-rows';
      const sidoOrder = [
        '서울특별시','인천광역시','경기도','강원특별자치도',
        '세종특별자치시','대전광역시','충청북도','충청남도',
        '광주광역시','전북특별자치도','전라남도',
        '대구광역시','부산광역시','울산광역시','경상북도','경상남도',
        '제주특별자치도',
      ];
      for (const sido of sidoOrder) {
        const e = (ep.results || {})[sido];
        if (!e) continue;
        const top = e[0];
        const a = actual[sido];
        const hit = a && top && a.party === top.party;
        const row = document.createElement('div');
        row.className = 'ar-exit-row ' + (a ? (hit ? 'is-hit' : 'is-miss') : '');
        const col = (typeof partyColor === 'function') ? partyColor(top.party) : '#999';
        const sshort = (typeof SIDO_LABEL_SHORT !== 'undefined') ? (SIDO_LABEL_SHORT[sido] || sido) : sido;
        row.innerHTML = `
          <span class="ar-exit-sido">${sshort}</span>
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

  // ===========================================================
  //  대선 (presidential) — 전국 1개 race + 시도 17개 분포
  // ===========================================================
  const SIDO_ORDER = [
    '서울특별시','인천광역시','경기도','강원특별자치도',
    '세종특별자치시','대전광역시','충청북도','충청남도',
    '광주광역시','전북특별자치도','전라남도',
    '대구광역시','부산광역시','울산광역시','경상북도','경상남도',
    '제주특별자치도',
  ];
  const ssh = (s) => (typeof SIDO_LABEL_SHORT !== 'undefined') ? (SIDO_LABEL_SHORT[s] || s) : s;
  const pcol = (p) => (typeof partyColor === 'function') ? partyColor(p) : '#999';

  function nationRace(results) {
    return (results?.races || []).find((r) => r.scope === 'nation' && r.sg_typecode === sgTypecode);
  }
  function sidoRacesPres(results) {
    return (results?.races || []).filter((r) => r.scope === 'sido' && r.sg_typecode === sgTypecode);
  }

  function renderHeroPres(results, polls) {
    if (polls) document.getElementById('ar-polls-count').textContent = polls.length.toLocaleString() + '건';
    const nat = nationRace(results);
    if (!nat) return;
    const cands = (nat.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0));
    const top = cands[0], second = cands[1];
    if (top) {
      const col = pcol(top.party);
      document.getElementById('ar-winner').innerHTML =
        `<span style="color:${col};font-weight:700">${top.name}</span> <span style="font-size:13px;color:var(--ink-soft)">${top.party}</span> <span style="font-size:13px;color:var(--ink-soft)">${(top.pct||0).toFixed(1)}%</span>`;
    }
    if (top && second) {
      document.getElementById('ar-margin').innerHTML =
        `${(top.pct - second.pct).toFixed(2)}<span style="font-size:12px;color:var(--ink-soft)">pp</span>`;
    }
    if (nat.electors > 0) {
      document.getElementById('ar-turnout').textContent = (nat.voters / nat.electors * 100).toFixed(1) + '%';
    }
    document.getElementById('ar-status').textContent = `개표 완료 · ${results._meta?.fetched_at || '갱신 시각 미상'}`;
  }

  function renderNationPres(results) {
    const nat = nationRace(results);
    if (!nat) return;
    const host = document.getElementById('ar-nation-host');
    const cands = (nat.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0));
    // 전국 후보별 가로 막대 (상위 6명)
    const total = cands.reduce((s, c) => s + (c.votes || 0), 0) || 1;
    const top6 = cands.slice(0, 6);
    let html = '<div class="ar-nation-bars">';
    for (const c of top6) {
      const w = (c.votes / total) * 100;
      const col = pcol(c.party);
      html += `<div class="ar-nation-row">
        <div class="ar-nation-name"><span style="color:${col};font-weight:700">${c.name}</span> <span class="ar-nation-party">${c.party}</span></div>
        <div class="ar-nation-bar"><span class="ar-nation-fill" style="width:${w.toFixed(2)}%;background:${col}"></span></div>
        <div class="ar-nation-pct">${(c.pct||0).toFixed(2)}<span class="unit">%</span></div>
        <div class="ar-nation-votes">${(c.votes||0).toLocaleString()}표</div>
      </div>`;
    }
    html += '</div>';
    host.innerHTML = html;
    document.getElementById('ar-nation').hidden = false;
  }

  function renderCountingPres(results) {
    const sidos = sidoRacesPres(results);
    if (!sidos.length) return;
    const host = document.getElementById('ar-counting-grid');
    // 시도 dict
    const bySido = Object.fromEntries(sidos.map((r) => [r.sido, r]));
    for (const sido of SIDO_ORDER) {
      const r = bySido[sido];
      if (!r) continue;
      const cands = (r.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0));
      const top = cands[0], second = cands[1];
      if (!top) continue;
      const col = pcol(top.party);
      const margin = second ? (top.pct - second.pct) : null;
      const cell = document.createElement('div');
      cell.className = 'ar-count-cell';
      cell.innerHTML = `
        <div class="ar-count-sido">${ssh(sido)}</div>
        <div class="ar-count-bar"><span class="ar-count-fill" style="width:${(top.pct||0).toFixed(1)}%;background:${col}"></span></div>
        <div class="ar-count-meta">
          <span style="color:${col};font-weight:700">${top.name} ${(top.pct||0).toFixed(1)}</span>
          ${margin != null ? `<span class="ar-count-pct">+${margin.toFixed(1)}pp</span>` : ''}
        </div>
      `;
      host.appendChild(cell);
    }
    document.getElementById('ar-counting').hidden = false;
  }

  function renderExitPollPres(exitData, results) {
    if (!exitData?.sources) return;
    const host = document.getElementById('ar-exitpoll-grid');
    const now = new Date();
    // 실제 — 전국 + 시도별 1위 후보
    const nat = nationRace(results);
    const sidos = sidoRacesPres(results);
    const actual = {};
    if (nat) {
      const c = (nat.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0))[0];
      if (c) actual['전국'] = { name: c.name, party: c.party, pct: c.pct };
    }
    for (const r of sidos) {
      const c = (r.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0))[0];
      if (c) actual[r.sido] = { name: c.name, party: c.party, pct: c.pct };
    }

    let anyBlock = false;
    for (const ep of exitData.sources) {
      const qa = ep.quote_after ? new Date(ep.quote_after) : null;
      if (qa && now < qa) continue;
      const res = ep.results || {};
      if (!Object.keys(res).length) continue;
      anyBlock = true;
      const card = document.createElement('div');
      card.className = 'ar-exit-block';
      // 적중률·평균 오차
      let hits = 0, tot = 0, errSum = 0, errN = 0;
      for (const [sido, cands] of Object.entries(res)) {
        const a = actual[sido];
        const top = cands?.[0];
        if (a && top) {
          tot += 1;
          if (a.name === top.name) hits += 1;
          if (a.pct != null && top.pct != null) {
            errSum += Math.abs(a.pct - top.pct); errN += 1;
          }
        }
      }
      const stats = tot ? `<span style="color:var(--ink-soft);font-size:12px;margin-left:10px">${hits}/${tot} 적중 · 평균 오차 ${errN ? (errSum/errN).toFixed(2) : '—'}pp</span>` : '';
      card.innerHTML = `<h3 class="ar-exit-source">${ep.name || ep.key}${stats}</h3>`;
      const grid = document.createElement('div');
      grid.className = 'ar-exit-rows';
      // 전국 행 먼저
      const order = ['전국', ...SIDO_ORDER];
      for (const sido of order) {
        const cands = res[sido];
        if (!cands || !cands[0]) continue;
        const top = cands[0];
        const a = actual[sido];
        const hit = a && a.name === top.name;
        const row = document.createElement('div');
        row.className = 'ar-exit-row ' + (a ? (hit ? 'is-hit' : 'is-miss') : '');
        if (sido === '전국') row.classList.add('is-nation');
        const col = pcol(top.party);
        row.innerHTML = `
          <span class="ar-exit-sido">${sido === '전국' ? '전국' : ssh(sido)}</span>
          <span class="ar-exit-pred" style="color:${col}">${top.name} ${(top.pct||0).toFixed(1)}</span>
          ${a ? `<span class="ar-exit-actual">실제 ${a.name} ${(a.pct||0).toFixed(1)}${hit ? ' ✓' : ' ✗'}</span>` : ''}
        `;
        grid.appendChild(row);
      }
      card.appendChild(grid);
      host.appendChild(card);
    }
    if (anyBlock) document.getElementById('ar-exitpoll').hidden = false;
  }

  function renderTrendPres(polls) {
    if (!polls?.length) return;
    // office_level=대통령, 후보지지 metric. 후보별 (period_end → pct) 시계열.
    const candPolls = polls.filter((p) => p.office_level === '대통령' && p.metric_type === '후보지지');
    if (!candPolls.length) return;
    // 후보별 표본 집계 — 전체 등장 횟수 상위 N
    const byCand = new Map();
    for (const p of candPolls) {
      for (const c of (p.candidates || [])) {
        if (!c.name || c.pct == null) continue;
        const key = c.name;
        if (!byCand.has(key)) byCand.set(key, { name: c.name, party: c.party, points: [] });
        byCand.get(key).points.push({ d: p.period_end || p.period_start, pct: c.pct });
      }
    }
    // 상위 6명 (등장 수 기준)
    const top = Array.from(byCand.values()).sort((a, b) => b.points.length - a.points.length).slice(0, 6);
    if (!top.length) return;
    // SVG 시계열
    const W = 720, H = 280, P = { l: 36, r: 12, t: 12, b: 28 };
    const innerW = W - P.l - P.r, innerH = H - P.t - P.b;
    // 날짜 range
    const allD = top.flatMap((c) => c.points.map((p) => p.d)).filter(Boolean).sort();
    if (!allD.length) return;
    const d0 = new Date(allD[0]).getTime(), d1 = new Date(allD[allD.length-1]).getTime();
    const yMax = Math.max(60, Math.ceil(Math.max(...top.flatMap((c) => c.points.map((p) => p.pct))) / 10) * 10);
    const xf = (d) => P.l + ((new Date(d).getTime() - d0) / (d1 - d0 || 1)) * innerW;
    const yf = (v) => P.t + innerH - (v / yMax) * innerH;
    const host = document.getElementById('ar-trend-host');
    let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-height:340px">`;
    // grid
    for (let v = 0; v <= yMax; v += 20) {
      const y = yf(v);
      svg += `<line x1="${P.l}" x2="${W-P.r}" y1="${y}" y2="${y}" stroke="var(--line)" stroke-width="0.5"/>`;
      svg += `<text x="${P.l-6}" y="${y+3}" text-anchor="end" font-size="10" fill="var(--ink-mute)">${v}%</text>`;
    }
    // x-축 — 월별 tick (대략 6개)
    const dt0 = new Date(d0), dt1 = new Date(d1);
    const months = (dt1.getFullYear() - dt0.getFullYear()) * 12 + (dt1.getMonth() - dt0.getMonth());
    const step = Math.max(1, Math.ceil(months / 6));
    for (let i = 0; i <= months; i += step) {
      const dx = new Date(dt0.getFullYear(), dt0.getMonth() + i, 1);
      if (dx.getTime() > d1) break;
      const x = xf(dx.toISOString().slice(0, 10));
      svg += `<text x="${x}" y="${H-8}" text-anchor="middle" font-size="10" fill="var(--ink-mute)">${dx.getFullYear()%100}.${(dx.getMonth()+1).toString().padStart(2,'0')}</text>`;
    }
    // 라인
    for (const c of top) {
      const sorted = c.points.slice().sort((a, b) => (a.d || '').localeCompare(b.d || ''));
      const path = sorted.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xf(p.d).toFixed(1)} ${yf(p.pct).toFixed(1)}`).join(' ');
      const col = pcol(c.party);
      svg += `<path d="${path}" stroke="${col}" stroke-width="1.4" fill="none" opacity="0.85"/>`;
      // 마지막 점에 라벨
      const last = sorted[sorted.length-1];
      svg += `<circle cx="${xf(last.d)}" cy="${yf(last.pct)}" r="2.5" fill="${col}"/>`;
      svg += `<text x="${xf(last.d)+5}" y="${yf(last.pct)+3}" font-size="10" fill="${col}" font-weight="700">${c.name}</text>`;
    }
    svg += '</svg>';
    host.innerHTML = svg;
    document.getElementById('ar-polls-trend').hidden = false;
  }

  // ===========================================================
  //  총선 (general_election) — 254 지역구 + 비례 47석
  // ===========================================================
  // 위성정당 → 본정당 (의석 합산용).
  const SATELLITE_TO_MAIN = {
    '국민의미래': '국민의힘',
    '더불어민주연합': '더불어민주당',
    '미래한국당': '국민의힘',
    '더불어시민당': '더불어민주당',
  };
  const mainParty = (p) => SATELLITE_TO_MAIN[p] || p;
  const propSg = () => meta.proportionalSgTypecode || '7';

  function districtRaces(results) {
    return (results?.races || []).filter((r) => r.scope === 'district' && r.sg_typecode === sgTypecode);
  }
  function propNationRace(results) {
    return (results?.races || []).find((r) => r.scope === 'nation' && r.sg_typecode === propSg());
  }

  // 정당별 의석 = 지역구 winner 카운트 + 비례 의석 (results._meta or 별도 계산)
  function computeSeats(results) {
    const seats = {};
    for (const r of districtRaces(results)) {
      const cands = (r.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0));
      const top = cands[0];
      if (top) {
        const p = mainParty(top.party);
        seats[p] = (seats[p] || 0) + 1;
      }
    }
    // 비례: race에 proportional_seats가 있으면 사용, 없으면 nation race 정당 득표율로 추정 (정확도 ↓)
    const propNat = propNationRace(results);
    if (propNat?.candidates) {
      for (const c of propNat.candidates) {
        const n = c.proportional_seats != null ? c.proportional_seats : (c.seats != null ? c.seats : null);
        if (n != null) {
          const p = mainParty(c.party);
          seats[p] = (seats[p] || 0) + n;
        }
      }
    }
    return seats;
  }

  function renderHeroGeneral(results, polls) {
    if (polls) document.getElementById('ar-polls-count').textContent = polls.length.toLocaleString() + '건';
    if (!results) return;
    const seats = computeSeats(results);
    const sorted = Object.entries(seats).sort((a, b) => b[1] - a[1]);
    if (sorted.length) {
      const [p1, n1] = sorted[0];
      document.getElementById('ar-winner').innerHTML =
        `<span style="color:${pcol(p1)};font-weight:700">${p1}</span> <span style="font-size:13px;color:var(--ink-soft)">${n1}석</span>`;
    }
    if (sorted.length > 1) {
      const [p2, n2] = sorted[1];
      document.getElementById('ar-runnerup').innerHTML =
        `<span style="color:${pcol(p2)};font-weight:700">${p2}</span> <span style="font-size:13px;color:var(--ink-soft)">${n2}석</span>`;
    }
    // 투표율 — 지역구 race 합산
    const drs = districtRaces(results);
    let voters = 0, electors = 0;
    for (const r of drs) { voters += r.voters || 0; electors += r.electors || 0; }
    if (electors > 0) document.getElementById('ar-turnout').textContent = (voters / electors * 100).toFixed(1) + '%';
    document.getElementById('ar-status').textContent = `개표 완료 · ${results._meta?.fetched_at || '갱신 시각 미상'}`;
  }

  function renderParliamentGeneral(results) {
    if (!results) return;
    const seats = computeSeats(results);
    const total = Object.values(seats).reduce((a, b) => a + b, 0);
    if (!total) return;
    const parties = Object.entries(seats)
      .sort((a, b) => b[1] - a[1])
      .map(([party, n]) => ({ party, seats: n, color: pcol(party) }));
    const host = document.getElementById('ar-parliament-host');
    if (typeof renderParliamentChart === 'function') {
      host.innerHTML = renderParliamentChart(parties, total, 480, 230);
    }
    // 테이블
    const table = document.getElementById('ar-parliament-table');
    table.innerHTML = parties.slice(0, 10).map(({party, seats: n, color}) =>
      `<div class="ar-parl-row">
        <span class="ar-parl-swatch" style="background:${color}"></span>
        <span class="ar-parl-name">${party}</span>
        <span class="ar-parl-seats">${n}석</span>
      </div>`).join('');
    document.getElementById('ar-parliament').hidden = false;
  }

  function renderProportionalGeneral(results) {
    const propNat = propNationRace(results);
    if (!propNat?.candidates) return;
    const cands = (propNat.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0));
    const total = cands.reduce((s, c) => s + (c.votes || 0), 0) || 1;
    const top8 = cands.slice(0, 8);
    let html = '<div class="ar-nation-bars">';
    for (const c of top8) {
      const w = (c.votes / total) * 100;
      const col = pcol(c.party);
      html += `<div class="ar-nation-row">
        <div class="ar-nation-name"><span style="color:${col};font-weight:700">${c.party}</span></div>
        <div class="ar-nation-bar"><span class="ar-nation-fill" style="width:${w.toFixed(2)}%;background:${col}"></span></div>
        <div class="ar-nation-pct">${(c.pct||0).toFixed(2)}<span class="unit">%</span></div>
        <div class="ar-nation-votes">${(c.votes||0).toLocaleString()}표</div>
      </div>`;
    }
    html += '</div>';
    document.getElementById('ar-proportional-host').innerHTML = html;
    document.getElementById('ar-proportional').hidden = false;
  }

  function renderDistrictsGeneral(results) {
    const drs = districtRaces(results);
    if (!drs.length) return;
    // 시도별 그룹
    const bySido = {};
    for (const r of drs) {
      const s = r.sido || '기타';
      (bySido[s] = bySido[s] || []).push(r);
    }
    const host = document.getElementById('ar-districts-host');
    let html = '';
    for (const sido of SIDO_ORDER) {
      const list = bySido[sido];
      if (!list?.length) continue;
      html += `<div class="ar-dist-block"><h3 class="ar-dist-sido">${ssh(sido)} <span class="ar-dist-count">${list.length}곳</span></h3><div class="ar-dist-rows">`;
      // 지역구명 정렬
      list.sort((a, b) => (a.district || a.sigungu || '').localeCompare(b.district || b.sigungu || ''));
      for (const r of list) {
        const cands = (r.candidates || []).slice().sort((a, b) => (b.votes||0) - (a.votes||0));
        const top = cands[0], second = cands[1];
        if (!top) continue;
        const col = pcol(top.party);
        const margin = second ? (top.pct - second.pct) : null;
        const name = r.district || r.sigungu || '?';
        html += `<div class="ar-dist-row" style="border-left:3px solid ${col}">
          <span class="ar-dist-name">${name}</span>
          <span class="ar-dist-cand" style="color:${col};font-weight:700">${top.name}</span>
          <span class="ar-dist-meta">${(top.pct||0).toFixed(1)}${margin != null ? ` <span style="color:var(--ink-mute)">+${margin.toFixed(1)}</span>` : ''}</span>
        </div>`;
      }
      html += '</div></div>';
    }
    host.innerHTML = html;
    document.getElementById('ar-districts').hidden = false;
  }

  function renderTrendGeneral(polls) {
    if (!polls?.length) return;
    // 정당지지 시계열 — 정당별 (period_end → pct).
    const partyPolls = polls.filter((p) => p.metric_type === '정당지지');
    if (!partyPolls.length) return;
    const byParty = new Map();
    for (const p of partyPolls) {
      for (const c of (p.candidates || [])) {
        const pty = c.party || c.name;
        if (!pty || c.pct == null) continue;
        if (!byParty.has(pty)) byParty.set(pty, { party: pty, points: [] });
        byParty.get(pty).points.push({ d: p.period_end || p.period_start, pct: c.pct });
      }
    }
    const top = Array.from(byParty.values()).sort((a, b) => b.points.length - a.points.length).slice(0, 6);
    if (!top.length) return;
    const W = 720, H = 280, P = { l: 36, r: 12, t: 12, b: 28 };
    const innerW = W - P.l - P.r, innerH = H - P.t - P.b;
    const allD = top.flatMap((c) => c.points.map((p) => p.d)).filter(Boolean).sort();
    if (!allD.length) return;
    const d0 = new Date(allD[0]).getTime(), d1 = new Date(allD[allD.length-1]).getTime();
    const yMax = Math.max(50, Math.ceil(Math.max(...top.flatMap((c) => c.points.map((p) => p.pct))) / 10) * 10);
    const xf = (d) => P.l + ((new Date(d).getTime() - d0) / (d1 - d0 || 1)) * innerW;
    const yf = (v) => P.t + innerH - (v / yMax) * innerH;
    let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-height:340px">`;
    for (let v = 0; v <= yMax; v += 10) {
      const y = yf(v);
      svg += `<line x1="${P.l}" x2="${W-P.r}" y1="${y}" y2="${y}" stroke="var(--line)" stroke-width="0.5"/>`;
      svg += `<text x="${P.l-6}" y="${y+3}" text-anchor="end" font-size="10" fill="var(--ink-mute)">${v}%</text>`;
    }
    const dt0 = new Date(d0), dt1 = new Date(d1);
    const months = (dt1.getFullYear() - dt0.getFullYear()) * 12 + (dt1.getMonth() - dt0.getMonth());
    const step = Math.max(1, Math.ceil(months / 6));
    for (let i = 0; i <= months; i += step) {
      const dx = new Date(dt0.getFullYear(), dt0.getMonth() + i, 1);
      if (dx.getTime() > d1) break;
      const x = xf(dx.toISOString().slice(0, 10));
      svg += `<text x="${x}" y="${H-8}" text-anchor="middle" font-size="10" fill="var(--ink-mute)">${dx.getFullYear()%100}.${(dx.getMonth()+1).toString().padStart(2,'0')}</text>`;
    }
    for (const c of top) {
      const sorted = c.points.slice().sort((a, b) => (a.d || '').localeCompare(b.d || ''));
      const path = sorted.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xf(p.d).toFixed(1)} ${yf(p.pct).toFixed(1)}`).join(' ');
      const col = pcol(c.party);
      svg += `<path d="${path}" stroke="${col}" stroke-width="1.4" fill="none" opacity="0.85"/>`;
      const last = sorted[sorted.length-1];
      svg += `<circle cx="${xf(last.d)}" cy="${yf(last.pct)}" r="2.5" fill="${col}"/>`;
      svg += `<text x="${xf(last.d)+5}" y="${yf(last.pct)+3}" font-size="10" fill="${col}" font-weight="700">${c.party}</text>`;
    }
    svg += '</svg>';
    document.getElementById('ar-trend-host').innerHTML = svg;
    document.getElementById('ar-polls-trend').hidden = false;
  }
})();
