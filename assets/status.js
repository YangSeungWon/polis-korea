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

  // 2) 현 국회 = 가장 최근 national_assembly 회차 + sidoWinners 합산
  const lastAsm = past.find((r) => r.kind === 'national_assembly');
  if (lastAsm) {
    const sw = lastAsm.sidoWinners || {};
    const seatsByParty = {};
    let totalDistricts = 0;
    for (const sido of Object.keys(sw)) {
      const w = sw[sido];
      if (w && w.party && w.seats) {
        seatsByParty[w.party] = (seatsByParty[w.party] || 0) + w.seats;
        totalDistricts += w.total || w.seats;
      }
    }
    const sorted = Object.entries(seatsByParty).sort((a, b) => b[1] - a[1]).slice(0, 3);
    const topEl = document.getElementById('status-asm-top');
    if (sorted.length) {
      topEl.innerHTML = sorted.map(([p, s]) => {
        const col = (typeof partyColor === 'function') ? partyColor(p) : '#999';
        return `<span style="color:${col}">${p} ${s}</span>`;
      }).join(' · ');
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
    document.getElementById('status-next-name').textContent =
      `${next.label}${next.predicted ? ' (예측)' : ''}`;
    const dDays = daysBetween(next.date);
    document.getElementById('status-next-meta').textContent =
      `${next.date} · ${dDays > 0 ? `D-${dDays}` : dDays === 0 ? '오늘' : `D+${-dDays}`}`;
  }

  root.hidden = false;
})();
