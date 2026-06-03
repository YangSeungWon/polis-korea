// index.html 상단 status-overview 채우기 — timeline.json 기반.
// 현 대통령, 현 국회 의석 분포, 가장 최근 선거, 다음 선거 D-N.

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
  const todayStr = today.toISOString().slice(0, 10);
  const daysBetween = (d) => Math.ceil((new Date(d) - today) / 86400000);

  // 1) 현 대통령 = 가장 최근 presidential 회차의 winner
  const lastPres = past.find((r) => r.kind === 'presidential');
  if (lastPres) {
    const color = (typeof partyColor === 'function' && lastPres.winner_party)
      ? partyColor(lastPres.winner_party) : '';
    const nameEl = document.getElementById('status-pres-name');
    nameEl.textContent = lastPres.winner || '—';
    if (color) nameEl.style.color = color;
    const startY = +lastPres.date.slice(0, 4);
    // 대선 5년 임기 가정 — 잔여
    const endDate = new Date(lastPres.date);
    endDate.setFullYear(endDate.getFullYear() + 5);
    const remDays = Math.ceil((endDate - today) / 86400000);
    const remY = Math.floor(remDays / 365);
    const remM = Math.floor((remDays % 365) / 30);
    document.getElementById('status-pres-meta').textContent =
      `${lastPres.label} · ${lastPres.date} 당선${remDays > 0 ? ` · 잔여 ${remY}년 ${remM}개월` : ''}`;
  }

  // 2) 현 국회 = 가장 최근 national_assembly 회차. 반 도넛으로 시각화.
  const lastAsm = past.find((r) => r.kind === 'national_assembly');
  if (lastAsm) {
    const sw = lastAsm.sidoWinners || {};
    const seatsByParty = {};
    for (const sido of Object.keys(sw)) {
      const w = sw[sido];
      if (w && w.party && w.seats) {
        seatsByParty[w.party] = (seatsByParty[w.party] || 0) + w.seats;
      }
    }
    const sorted = Object.entries(seatsByParty).sort((a, b) => b[1] - a[1]);
    const total = sorted.reduce((s, [, v]) => s + v, 0);
    const topEl = document.getElementById('status-asm-top');
    if (sorted.length && total > 0) {
      topEl.innerHTML = renderHalfDonut(sorted, total);
    }
    document.getElementById('status-asm-meta').textContent =
      `${lastAsm.label} · ${lastAsm.date} 선출 · 임기 4년`;
  }

  // 3) 가장 최근 선거 (대선·총선·지선 통합 최근)
  const latest = past[0];
  if (latest) {
    document.getElementById('status-latest-name').textContent = latest.label;
    const daysAgo = Math.ceil((today - new Date(latest.date)) / 86400000);
    const winnerInfo = latest.winner ? ` · 1위 ${latest.winner}` : '';
    document.getElementById('status-latest-meta').textContent =
      `${latest.date}${daysAgo >= 0 ? ` (${daysAgo}일 전)` : ''}${winnerInfo}`;
  }

  // 4) 다음 선거 = 가장 가까운 미래 회차 (active 우선, 그 다음 예측)
  const next = future[0];
  if (next) {
    document.getElementById('status-next-name').textContent = next.label;
    const dDays = daysBetween(next.date);
    document.getElementById('status-next-meta').textContent =
      `${next.date} · ${dDays > 0 ? `D-${dDays}` : dDays === 0 ? '오늘' : `D+${-dDays}`}`;
  }

  root.hidden = false;
})();

// 반 도넛 의석 차트 — sorted=[[party, seats], ...] 의석수 내림차순, total=총 의석.
// 좌→우 호로 정당 색 분포. 60px 높이 SVG.
function renderHalfDonut(sorted, total) {
  const W = 200, H = 70, cx = W / 2, cy = H - 8, rOut = 56, rIn = 36;
  // 좌→우 순서: 좌측 = 진보(파랑계열), 우측 = 보수(빨강계열) — 의석수 큰 정당 좌측부터
  // 단순화: sorted 순서대로 좌→우.
  let accAngle = Math.PI;  // π = 좌측 끝
  const arcs = sorted.map(([party, seats]) => {
    const span = (seats / total) * Math.PI;
    const a0 = accAngle, a1 = accAngle - span;  // 시계방향(음수)
    accAngle = a1;
    const color = (typeof partyColor === 'function') ? partyColor(party) : '#999';
    const p1 = polarToXY(cx, cy, rOut, a0);
    const p2 = polarToXY(cx, cy, rOut, a1);
    const p3 = polarToXY(cx, cy, rIn, a1);
    const p4 = polarToXY(cx, cy, rIn, a0);
    const large = span > Math.PI ? 1 : 0;
    const d = `M${p1.x},${p1.y} A${rOut},${rOut} 0 ${large} 0 ${p2.x},${p2.y} L${p3.x},${p3.y} A${rIn},${rIn} 0 ${large} 1 ${p4.x},${p4.y} Z`;
    return `<path d="${d}" fill="${color}"><title>${party} ${seats}석</title></path>`;
  }).join('');
  // 중앙 총 의석 텍스트
  const cnt = `<text x="${cx}" y="${cy - 6}" text-anchor="middle" font-size="16" font-weight="800" fill="var(--ink)" font-family="Pretendard, system-ui, sans-serif">${total}</text>`;
  const lbl = `<text x="${cx}" y="${cy + 6}" text-anchor="middle" font-size="9" fill="var(--ink-soft)" font-family="Pretendard, system-ui, sans-serif">지역구</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="auto" preserveAspectRatio="xMidYMid meet">${arcs}${cnt}${lbl}</svg>`;
}

function polarToXY(cx, cy, r, angle) {
  return { x: cx + r * Math.cos(angle), y: cy - r * Math.sin(angle) };
}
