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
    const endDate = new Date(lastPres.date);
    endDate.setFullYear(endDate.getFullYear() + 5);
    const remDays = Math.ceil((endDate - today) / 86400000);
    const remY = Math.floor(remDays / 365);
    const remM = Math.floor((remDays % 365) / 30);
    const result = lastPres.winner
      ? `<div class="pres-result">${lastPres.winner}${party ? ` <span class="party-pill" style="background:${color}">${party}</span>` : ''}</div>`
      : '<div class="pres-result">—</div>';
    // 전체 후보 득표 % 가로 막대 (상위 4명).
    const cands = (lastPres.presCandidates || []).slice(0, 4);
    const candHtml = cands.length
      ? `<div class="cand-bars">` + cands.map((c) => {
          const cc = (typeof partyColor === 'function') ? partyColor(c.party) : '#999';
          return `<div class="cand-row">
            <span class="cand-name">${c.name}</span>
            <span class="cand-bar"><span class="cand-fill" style="width:${c.pct}%;background:${cc}"></span></span>
            <span class="cand-pct">${c.pct.toFixed(1)}</span>
          </div>`;
        }).join('') + `</div>`
      : '';
    document.getElementById('status-pres-name').innerHTML = result + candHtml;
    document.getElementById('status-pres-meta').textContent =
      remDays > 0 ? `임기 5년 · 잔여 ${remY}년 ${remM}개월` : '임기 종료';
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
      const parties = sorted.map(([party, seats]) => ({
        party, seats,
        color: (typeof partyColor === 'function') ? partyColor(party) : '#999',
      }));
      const chart = (typeof renderParliamentChart === 'function')
        ? renderParliamentChart(parties, total, 260, 130)
        : '';
      // 범례: 상위 3 정당 + 나머지 합산
      const topN = 3;
      const top = parties.slice(0, topN);
      const restSeats = parties.slice(topN).reduce((s, p) => s + p.seats, 0);
      const legendHtml = top.map((p) =>
        `<span class="leg-item"><span class="leg-dot" style="background:${p.color}"></span><b>${p.seats}</b> ${p.party}</span>`
      ).join('')
      + (restSeats ? `<span class="leg-item leg-other"><b>${restSeats}</b> 외 ${parties.length - topN}당</span>` : '');
      document.getElementById('status-asm-top').innerHTML =
        `<div class="parliament-wrap-mini">${chart}<div class="parliament-total">${total}석</div></div>`
        + `<div class="party-legend">${legendHtml}</div>`;
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
    stripEl.innerHTML =
      `<div class="tl-strip-svg">${renderTimelineStrip(visible, today, tEarliest, tLatest)}</div>`
      + `<div class="tl-strip-list">${renderTimelineList(visible, today)}</div>`;
    stripEl.querySelectorAll('.tl-dot').forEach((g) => {
      const href = g.getAttribute('data-href');
      if (href) g.addEventListener('click', () => { location.href = href; });
    });
  }

  root.hidden = false;
})();

function renderTimelineStrip(rounds, today, tStart, tEnd) {
  const W = 900, H = 130;
  const padL = 26, padR = 26;
  const inner = W - padL - padR;
  const span = tEnd - tStart;
  const xOf = (d) => padL + ((new Date(d) - tStart) / span) * inner;
  const kindCol = (k) => ({ presidential: '#c8553d', national_assembly: '#2e7d6f', local: '#b07e3d' }[k] || '#999');
  const kindShort = { presidential: '대선', national_assembly: '총선', local: '지선' };

  // 라인
  const line = `<line x1="${padL}" y1="${H/2}" x2="${W - padR}" y2="${H/2}" stroke="rgba(10,14,26,0.18)" stroke-width="1.5"/>`;

  // round dots
  let dots = '';
  const unitOf = { presidential: '대', national_assembly: '대', local: '회' };
  // 위/아래 alternating — 회차명·연도 두 줄.
  rounds.forEach((r, i) => {
    const x = xOf(r.date);
    const isPast = !r.upcoming;
    const col = kindCol(r.kind);
    const fill = isPast ? col : 'rgba(255,255,255,0.85)';
    const stroke = col;
    const r0 = 7;
    const rHit = 18;  // 투명 hitbox 반경 — hover/click 영역 확장
    const above = (i % 2 === 0);
    // 위: 회차명 위, 연도 더 위 / 아래: 회차명 아래, 연도 더 아래
    const yName = above ? H/2 - 16 : H/2 + 26;
    const yYear = above ? H/2 - 30 : H/2 + 40;
    const labelName = `${r.n}${unitOf[r.kind]} ${kindShort[r.kind]}`;
    const year = r.date.slice(0, 4);
    dots += `
      <g class="tl-dot" data-href="history.html?type=${r.kind}&n=${r.n}">
        <title>${r.label} ${r.date}${r.winner ? ` · ${r.winner}` : ''}${r.upcoming ? ' (예정)' : ''}</title>
        <circle class="tl-dot-hit" cx="${x}" cy="${H/2}" r="${rHit}" fill="transparent"/>
        <circle class="tl-dot-vis" cx="${x}" cy="${H/2}" r="${r0}" fill="${fill}" stroke="${stroke}" stroke-width="${isPast ? 0 : 1.8}" ${isPast ? '' : 'stroke-dasharray="2,1.5"'} />
        <text x="${x}" y="${yName}" text-anchor="middle" font-size="13" font-weight="${isPast ? '700' : '600'}" fill="${isPast ? '#0a0e1a' : '#5a6378'}" font-family="Pretendard, system-ui, sans-serif">${labelName}</text>
        <text x="${x}" y="${yYear}" text-anchor="middle" font-size="13" font-weight="700" fill="#5a6378" font-family="Pretendard, system-ui, sans-serif">${year}</text>
      </g>
    `;
  });

  // 오늘 — 수직선만 강조. dot/라벨은 회차 dot과 충돌 피해 제거.
  const tx = xOf(today.toISOString().slice(0, 10));
  const todayDot = `
    <line x1="${tx}" y1="6" x2="${tx}" y2="${H - 6}" stroke="#0a0e1a" stroke-width="1.6" opacity="0.55"/>
  `;

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" style="display:block">
    ${line}
    ${dots}
    ${todayDot}
  </svg>`;
}

// (renderTimeAxis 제거됨 — 시간축은 renderTimelineStrip이 담당)

function polarToXY(cx, cy, r, angle) {
  return { x: cx + r * Math.cos(angle), y: cy - r * Math.sin(angle) };
}

// 모바일용 시간축 list — 시간 역순(미래→과거). 오늘 위치에 가로선 마커.
function renderTimelineList(rounds, today) {
  const kindCol = (k) => ({ presidential: '#c8553d', national_assembly: '#2e7d6f', local: '#b07e3d' }[k] || '#999');
  const kindShort = { presidential: '대선', national_assembly: '총선', local: '지선' };
  const unitOf = { presidential: '대', national_assembly: '대', local: '회' };
  const todayStr = today.toISOString().slice(0, 10);
  const sorted = [...rounds].sort((a, b) => b.date.localeCompare(a.date));
  let inserted = false;
  const rows = [];
  for (const r of sorted) {
    if (!inserted && r.date <= todayStr) {
      rows.push(`<li class="tl-list-today"><span>오늘 · ${todayStr}</span></li>`);
      inserted = true;
    }
    const col = kindCol(r.kind);
    const fill = r.upcoming ? 'transparent' : col;
    const dot = `<span class="tl-list-dot" style="background:${fill};border:2px solid ${col}"></span>`;
    const url = `history.html?type=${r.kind}&n=${r.n}`;
    rows.push(`<li class="tl-list-row${r.upcoming ? ' is-upcoming' : ''}">
      <a href="${url}">
        ${dot}
        <span class="tl-list-date">${r.date.slice(0, 4)}.${r.date.slice(5, 7)}</span>
        <span class="tl-list-name">${r.n}${unitOf[r.kind]} ${kindShort[r.kind]}</span>
      </a>
    </li>`);
  }
  if (!inserted) rows.push(`<li class="tl-list-today"><span>오늘 · ${todayStr}</span></li>`);
  return `<ul class="tl-list">${rows.join('')}</ul>`;
}
