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
      document.getElementById('status-asm-top').innerHTML = renderHalfDonut(sorted, total);
    }
    document.getElementById('status-asm-meta').textContent =
      `${total}석 · 임기 4년`;
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

  // 4) 시간축 — 최근 선거 ←  오늘  → 다음 선거
  const latest = past[0];
  const next = future[0];
  if (latest || next) {
    const axisEl = document.getElementById('status-timeline-axis');
    axisEl.innerHTML = renderTimeAxis(latest, next, today);
    const parts = [];
    if (latest) parts.push(`${latest.label} ${Math.abs(daysBetween(latest.date))}일 전`);
    if (next) {
      const dd = daysBetween(next.date);
      parts.push(`${next.label} ${dd > 0 ? `D-${dd}` : dd === 0 ? '오늘' : `D+${-dd}`}`);
    }
    document.getElementById('status-timeline-meta').textContent = parts.join(' · ');
  }

  root.hidden = false;
})();

// 반 도넛 의석 차트 — 좌(π)→우(0) 위쪽 호. SVG y-down에서 sweep=0 outer, sweep=1 inner.
function renderHalfDonut(sorted, total) {
  const W = 220, H = 78, cx = W / 2, cy = H - 6, rOut = 60, rIn = 36;
  let accAngle = Math.PI;
  const arcs = sorted.map(([party, seats]) => {
    const span = (seats / total) * Math.PI;
    const a0 = accAngle, a1 = accAngle - span;
    accAngle = a1;
    const color = (typeof partyColor === 'function') ? partyColor(party) : '#999';
    const p1 = polarToXY(cx, cy, rOut, a0);
    const p2 = polarToXY(cx, cy, rOut, a1);
    const p3 = polarToXY(cx, cy, rIn, a1);
    const p4 = polarToXY(cx, cy, rIn, a0);
    const d = `M${p1.x.toFixed(2)},${p1.y.toFixed(2)} `
            + `A${rOut},${rOut} 0 0 0 ${p2.x.toFixed(2)},${p2.y.toFixed(2)} `
            + `L${p3.x.toFixed(2)},${p3.y.toFixed(2)} `
            + `A${rIn},${rIn} 0 0 1 ${p4.x.toFixed(2)},${p4.y.toFixed(2)} Z`;
    return `<path d="${d}" fill="${color}"><title>${party} ${seats}석</title></path>`;
  }).join('');
  const cnt = `<text x="${cx}" y="${cy - 12}" text-anchor="middle" font-size="20" font-weight="800" fill="#0a0e1a" font-family="Pretendard, system-ui, sans-serif">${total}</text>`;
  const lbl = `<text x="${cx}" y="${cy + 2}" text-anchor="middle" font-size="9" fill="#5a6378" font-family="Pretendard, system-ui, sans-serif">지역구 의석</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="auto" preserveAspectRatio="xMidYMid meet" style="display:block">${arcs}${cnt}${lbl}</svg>`;
}

// 시간축 — 좌측 최근, 중앙 오늘 dot, 우측 다음. 막대 너비 비례 안 함 (단순 indicator).
function renderTimeAxis(latest, next, today) {
  const W = 220, H = 70;
  // 위치: latest 0%, today 40~60% (latest/next 거리 비례), next 100%
  let todayPct = 50;
  if (latest && next) {
    const a = new Date(latest.date).getTime();
    const b = new Date(next.date).getTime();
    const t = today.getTime();
    todayPct = Math.max(8, Math.min(92, ((t - a) / (b - a)) * 100));
  } else if (!latest) { todayPct = 8; } else if (!next) { todayPct = 92; }

  const kindCol = (k) => ({ presidential: '#c8553d', national_assembly: '#2e7d6f', local: '#b07e3d' }[k] || '#999');

  const leftLabel = latest
    ? `<g><circle cx="20" cy="40" r="6" fill="${kindCol(latest.kind)}"/>
        <text x="20" y="62" text-anchor="start" font-size="9" font-weight="700" fill="#0a0e1a">${latest.label}</text>
        <text x="20" y="22" text-anchor="start" font-size="8" fill="#5a6378">${latest.date}</text></g>`
    : '';
  const rightLabel = next
    ? `<g><circle cx="${W - 20}" cy="40" r="6" fill="${kindCol(next.kind)}" opacity="0.6" stroke="${kindCol(next.kind)}" stroke-width="1.5" stroke-dasharray="2,1.5"/>
        <text x="${W - 20}" y="62" text-anchor="end" font-size="9" font-weight="700" fill="#0a0e1a">${next.label}</text>
        <text x="${W - 20}" y="22" text-anchor="end" font-size="8" fill="#5a6378">${next.date}</text></g>`
    : '';
  // 가로 라인
  const line = `<line x1="20" y1="40" x2="${W - 20}" y2="40" stroke="rgba(10,14,26,0.25)" stroke-width="1.5"/>`;
  // 오늘 dot
  const todayX = 20 + (W - 40) * (todayPct / 100);
  const todayDot = `<g><circle cx="${todayX}" cy="40" r="4.5" fill="#0a0e1a"/>
                     <text x="${todayX}" y="55" text-anchor="middle" font-size="8" font-weight="700" fill="#0a0e1a">오늘</text></g>`;
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="auto" preserveAspectRatio="xMidYMid meet" style="display:block;margin-top:2px">${line}${leftLabel}${rightLabel}${todayDot}</svg>`;
}

function polarToXY(cx, cy, r, angle) {
  return { x: cx + r * Math.cos(angle), y: cy - r * Math.sin(angle) };
}
