// index.html 상단 status-overview — 정치 단위(대통령·국회·지방정부) ↔ 선거 매핑.
// 4번째는 시간축(최근/다음 선거 좌-오늘-우).

(async function fillStatus() {
  const root = document.getElementById('status-overview');
  if (!root) return;
  let timeline;
  try {
    timeline = await fetch('data/timeline.json').then((r) => r.json());
  } catch {
    return;
  }
  const rounds = (timeline.rounds || []).filter((r) => r.date);
  const past = rounds.filter((r) => !r.upcoming)
                     .sort((a, b) => b.date.localeCompare(a.date));
  const future = rounds.filter((r) => r.upcoming)
                       .sort((a, b) => a.date.localeCompare(b.date));
  const today = new Date();
  const daysBetween = (d) => Math.ceil((new Date(d) - today) / 86400000);

  // 1) 대통령 — 가장 최근 대선. 카드 layout: 회차+날짜 헤딩 → 결과 가운데 → 잔여 작게.
  const lastPres = past.find((r) => r.kind === 'presidential');
  if (lastPres) {
    const color = (typeof partyColor === 'function' && lastPres.winner_party)
      ? partyColor(lastPres.winner_party) : '#5a6378';
    const party = lastPres.winner_party || '';
    const card = document.querySelector('[data-slot="president"]');
    if (card) {
      const headingEl = card.querySelector('.card-heading') || (() => {
        const e = document.createElement('div');
        e.className = 'card-heading';
        card.querySelector('.status-label').after(e);
        return e;
      })();
      headingEl.innerHTML = `<span class="card-heading-n">${lastPres.label}</span><span class="card-heading-date">${lastPres.date}</span>`;
    }
    document.getElementById('status-pres-name').innerHTML = lastPres.winner
      ? `${lastPres.winner}${party ? ` <span class="party-pill" style="background:${color}">${party}</span>` : ''}`
      : '—';
    const endDate = new Date(lastPres.date);
    endDate.setFullYear(endDate.getFullYear() + 5);
    const remDays = Math.ceil((endDate - today) / 86400000);
    const remY = Math.floor(remDays / 365);
    const remM = Math.floor((remDays % 365) / 30);
    document.getElementById('status-pres-meta').textContent =
      remDays > 0 ? `당선 · 잔여 ${remY}년 ${remM}개월` : '임기 종료';
  }

  // 2) 국회 — 가장 최근 총선. partySeats(지역구+비례 위성정당 합산) 우선, fallback sidoWinners.
  const lastAsm = past.find((r) => r.kind === 'national_assembly');
  if (lastAsm) {
    let sorted = lastAsm.partySeats || [];
    if (!sorted.length) {
      const sw = lastAsm.sidoWinners || {};
      const counter = {};
      for (const sido of Object.keys(sw)) {
        const w = sw[sido];
        if (w?.party && w?.seats) counter[w.party] = (counter[w.party] || 0) + w.seats;
      }
      sorted = Object.entries(counter).sort((a, b) => b[1] - a[1]);
    }
    const total = sorted.reduce((s, [, v]) => s + v, 0);
    const card = document.querySelector('[data-slot="assembly"]');
    if (card) {
      const headingEl = card.querySelector('.card-heading') || (() => {
        const e = document.createElement('div');
        e.className = 'card-heading';
        card.querySelector('.status-label').after(e);
        return e;
      })();
      headingEl.innerHTML = `<span class="card-heading-n">${lastAsm.label}</span><span class="card-heading-date">${lastAsm.date}</span>`;
    }
    if (sorted.length && total > 0) {
      // parliament half-donut dots (history.html detail pane와 동일 디자인).
      const parties = sorted.map(([party, seats]) => ({
        party, seats,
        color: (typeof partyColor === 'function') ? partyColor(party) : '#999',
      }));
      const chart = (typeof renderParliamentChart === 'function')
        ? renderParliamentChart(parties, total, 260, 130)
        : '';
      document.getElementById('status-asm-top').innerHTML =
        `<div class="parliament-wrap-mini">${chart}<div class="parliament-total">${total}석</div></div>`;
    }
    document.getElementById('status-asm-meta').textContent = `임기 4년`;
  }

  // 3) 지방정부 — 가장 최근 지선, 시도지사 정당 분포
  const lastLocal = past.find((r) => r.kind === 'local');
  if (lastLocal) {
    const sw = lastLocal.sidoWinners || {};
    const partyCount = {};
    for (const sido of Object.keys(sw)) {
      const w = sw[sido];
      if (w && w.party) partyCount[w.party] = (partyCount[w.party] || 0) + 1;
    }
    const sorted = Object.entries(partyCount).sort((a, b) => b[1] - a[1]);
    const card = document.querySelector('[data-slot="local"]');
    if (card) {
      const headingEl = card.querySelector('.card-heading') || (() => {
        const e = document.createElement('div');
        e.className = 'card-heading';
        card.querySelector('.status-label').after(e);
        return e;
      })();
      headingEl.innerHTML = `<span class="card-heading-n">${lastLocal.label}</span><span class="card-heading-date">${lastLocal.date}</span>`;
    }
    const nameEl = document.getElementById('status-local-name');
    if (sorted.length) {
      nameEl.innerHTML = sorted.slice(0, 3).map(([p, c]) => {
        const col = (typeof partyColor === 'function') ? partyColor(p) : '#999';
        return `<span class="party-chip" style="color:${col}"><b>${c}</b>${p}</span>`;
      }).join(' ');
    }
    document.getElementById('status-local-meta').textContent =
      `17개 시·도지사 · 임기 4년`;
  }

  // 4) 시간축 strip — 최근 5년 + 향후 5년 회차 흐름. 오늘 dot.
  const stripEl = document.getElementById('status-timeline-strip');
  if (stripEl) {
    const tEarliest = new Date(today); tEarliest.setFullYear(today.getFullYear() - 5);
    const tLatest = new Date(today); tLatest.setFullYear(today.getFullYear() + 5);
    const visible = rounds.filter((r) => {
      const t = new Date(r.date);
      return t >= tEarliest && t <= tLatest;
    }).sort((a, b) => a.date.localeCompare(b.date));
    stripEl.innerHTML = renderTimelineStrip(visible, today, tEarliest, tLatest);
    stripEl.querySelectorAll('.tl-dot').forEach((g) => {
      const href = g.getAttribute('data-href');
      if (href) g.addEventListener('click', () => { location.href = href; });
    });
  }

  root.hidden = false;
})();

function renderTimelineStrip(rounds, today, tStart, tEnd) {
  const W = 1100, H = 90;
  const padL = 60, padR = 60;
  const inner = W - padL - padR;
  const span = tEnd - tStart;
  const xOf = (d) => padL + ((new Date(d) - tStart) / span) * inner;
  const kindCol = (k) => ({ presidential: '#c8553d', national_assembly: '#2e7d6f', local: '#b07e3d' }[k] || '#999');
  const kindShort = { presidential: '대선', national_assembly: '총선', local: '지선' };

  // 라인
  const line = `<line x1="${padL}" y1="${H/2}" x2="${W - padR}" y2="${H/2}" stroke="rgba(10,14,26,0.18)" stroke-width="1.5"/>`;

  // 시작/끝 연도 label
  const yLabel = (d, anchor, x) => `<text x="${x}" y="${H/2 + 20}" text-anchor="${anchor}" font-size="10" fill="#8a93a3" font-family="Pretendard, system-ui, sans-serif">${new Date(d).getFullYear()}</text>`;

  // round dots
  let dots = '';
  // 오늘과 충돌 방지 위해 label 위/아래 alternating
  rounds.forEach((r, i) => {
    const x = xOf(r.date);
    const isPast = !r.upcoming;
    const col = kindCol(r.kind);
    const fill = isPast ? col : 'rgba(255,255,255,0.85)';
    const stroke = col;
    const r0 = 5.5;
    const labelY = (i % 2 === 0) ? H/2 - 14 : H/2 + 24;
    const labelText = `${r.n}${kindShort[r.kind]}`;
    dots += `
      <g class="tl-dot" data-href="history.html?type=${r.kind}&n=${r.n}">
        <title>${r.label} ${r.date}${r.winner ? ` · ${r.winner}` : ''}${r.upcoming ? ' (예정)' : ''}</title>
        <circle cx="${x}" cy="${H/2}" r="${r0}" fill="${fill}" stroke="${stroke}" stroke-width="${isPast ? 0 : 1.6}" ${isPast ? '' : 'stroke-dasharray="2,1.5"'} />
        <text x="${x}" y="${labelY}" text-anchor="middle" font-size="10.5" font-weight="${isPast ? '700' : '600'}" fill="${isPast ? '#0a0e1a' : '#5a6378'}" font-family="Pretendard, system-ui, sans-serif">${labelText}</text>
      </g>
    `;
  });

  // 오늘 dot (더 큼, 다크)
  const tx = xOf(today.toISOString().slice(0, 10));
  const todayDot = `
    <line x1="${tx}" y1="${H/2 - 18}" x2="${tx}" y2="${H/2 + 18}" stroke="#0a0e1a" stroke-width="1.2" stroke-dasharray="2,2" opacity="0.4"/>
    <circle cx="${tx}" cy="${H/2}" r="6.5" fill="#0a0e1a"/>
    <text x="${tx}" y="${H - 4}" text-anchor="middle" font-size="11" font-weight="800" fill="#0a0e1a" font-family="Pretendard, system-ui, sans-serif">오늘</text>
  `;

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" style="display:block">
    ${line}
    ${yLabel(tStart, 'start', padL)}
    ${yLabel(tEnd, 'end', W - padR)}
    ${dots}
    ${todayDot}
  </svg>`;
}

// (renderTimeAxis 제거됨 — 시간축은 renderTimelineStrip이 담당)

function polarToXY(cx, cy, r, angle) {
  return { x: cx + r * Math.cos(angle), y: cy - r * Math.sin(angle) };
}
