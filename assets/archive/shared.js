// archive 공통 — 모든 모드가 쓰는 SIDO_ORDER · helpers · 필터 · 폴 목록.
// window.Archive 네임스페이스에 attach. 다른 모드 모듈이 여기서 destructure 가능.

(function () {
  const Archive = (window.Archive = window.Archive || {});

  Archive.SIDO_ORDER = [
    '서울특별시', '인천광역시', '경기도', '강원특별자치도',
    '세종특별자치시', '대전광역시', '충청북도', '충청남도',
    '광주광역시', '전북특별자치도', '전라남도',
    '대구광역시', '부산광역시', '울산광역시', '경상북도', '경상남도',
    '제주특별자치도',
  ];

  Archive.ssh = (s) => (typeof SIDO_LABEL_SHORT !== 'undefined') ? (SIDO_LABEL_SHORT[s] || s) : s;
  Archive.pcol = (p) => (typeof partyColor === 'function') ? partyColor(p) : '#999';

  // 위성정당 → 본정당: assets/parties.js 의 SATELLITE_TO_MAIN/mainParty 전역 사용.
  // 단일 출처: data/parties/satellites.json → sync_satellites_js.py가 parties.js로 sync.
  Archive.SATELLITE_TO_MAIN = (typeof SATELLITE_TO_MAIN !== 'undefined') ? SATELLITE_TO_MAIN : {};
  Archive.mainParty = (typeof mainParty === 'function') ? mainParty : ((p) => Archive.SATELLITE_TO_MAIN[p] || p);

  // 폴 필터: pollsWindow (meta) 안 period_start 인 폴만 통과. window 없으면 1년 전 ~ 회차일.
  Archive.filterPoll = function (poll, meta) {
    const ps = poll.period_start || '';
    if (!ps) return false;
    const w = meta.pollsWindow || {};
    const start = w.start || (() => {
      const d = new Date(meta.date); d.setFullYear(d.getFullYear() - 1);
      return d.toISOString().slice(0, 10);
    })();
    const end = w.end || meta.date;
    return ps >= start && ps <= end;
  };

  // 조사 목록 — 회차·모드 무관 공통 렌더. 모든 모드에서 마지막에 호출.
  Archive.renderPollsList = function (polls) {
    if (!polls?.length) return;
    const host = document.getElementById('ar-polls-list-host');
    polls.slice()
      .sort((a, b) => (b.period_end || '').localeCompare(a.period_end || ''))
      .slice(0, 60)
      .forEach((p) => {
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
  };

  // 후보·정당 시계열 SVG — 대선(후보별)·총선(정당별) 둘 다 쓰는 공용 차트.
  // series: [{ label, color, points: [{d, pct}] }]
  Archive.renderTrendSVG = function (host, series, opts = {}) {
    if (!series.length) return false;
    const W = opts.width || 720, H = opts.height || 280;
    const P = { l: 36, r: 12, t: 12, b: 28 };
    const innerW = W - P.l - P.r, innerH = H - P.t - P.b;
    const allD = series.flatMap((s) => s.points.map((p) => p.d)).filter(Boolean).sort();
    if (!allD.length) return false;
    const d0 = new Date(allD[0]).getTime();
    const d1 = new Date(allD[allD.length - 1]).getTime();
    const allV = series.flatMap((s) => s.points.map((p) => p.pct));
    const yMax = Math.max(opts.yMin || 50, Math.ceil(Math.max(...allV) / 10) * 10);
    const yStep = opts.yStep || 10;
    const xf = (d) => P.l + ((new Date(d).getTime() - d0) / (d1 - d0 || 1)) * innerW;
    const yf = (v) => P.t + innerH - (v / yMax) * innerH;
    let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-height:340px">`;
    for (let v = 0; v <= yMax; v += yStep) {
      const y = yf(v);
      svg += `<line x1="${P.l}" x2="${W - P.r}" y1="${y}" y2="${y}" stroke="var(--line)" stroke-width="0.5"/>`;
      svg += `<text x="${P.l - 6}" y="${y + 3}" text-anchor="end" font-size="10" fill="var(--ink-mute)">${v}%</text>`;
    }
    const dt0 = new Date(d0), dt1 = new Date(d1);
    const months = (dt1.getFullYear() - dt0.getFullYear()) * 12 + (dt1.getMonth() - dt0.getMonth());
    const step = Math.max(1, Math.ceil(months / 6));
    for (let i = 0; i <= months; i += step) {
      const dx = new Date(dt0.getFullYear(), dt0.getMonth() + i, 1);
      if (dx.getTime() > d1) break;
      const x = xf(dx.toISOString().slice(0, 10));
      svg += `<text x="${x}" y="${H - 8}" text-anchor="middle" font-size="10" fill="var(--ink-mute)">${dx.getFullYear() % 100}.${(dx.getMonth() + 1).toString().padStart(2, '0')}</text>`;
    }
    for (const s of series) {
      const sorted = s.points.slice().sort((a, b) => (a.d || '').localeCompare(b.d || ''));
      const path = sorted.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xf(p.d).toFixed(1)} ${yf(p.pct).toFixed(1)}`).join(' ');
      svg += `<path d="${path}" stroke="${s.color}" stroke-width="1.4" fill="none" opacity="0.85"/>`;
      const last = sorted[sorted.length - 1];
      svg += `<circle cx="${xf(last.d)}" cy="${yf(last.pct)}" r="2.5" fill="${s.color}"/>`;
      svg += `<text x="${xf(last.d) + 5}" y="${yf(last.pct) + 3}" font-size="10" fill="${s.color}" font-weight="700">${s.label}</text>`;
    }
    svg += '</svg>';
    host.innerHTML = svg;
    return true;
  };
})();
