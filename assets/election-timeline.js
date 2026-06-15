// 선거별 3레인 타임라인 디렉터리 — 폴 허브(폴 링크)·대시보드(아카이브 링크) 공용 렌더러.
//   ElectionTimeline.render(host, list, opts)
//     list = [{slug, name, date, n, type?}]   (type 없으면 slug로 대선/총선/지선 판별)
//     opts = { hrefFn(e)→url, current(slug|null, 없으면 최신 강조), ariaFn(e)→str, note(html), curSuffix }
//   데스크톱=SVG 타임라인, 모바일=유형별 칩(CSS 미디어쿼리 토글). 스타일은 components.css(.poll-tl-*/.ptc-*).
(function () {
  'use strict';
  const LANE = {
    pres: { label: '대선', color: '#5b54d6', y: 44 },
    general: { label: '총선', color: '#168f8f', y: 82 },
    local: { label: '지선', color: '#c98a2e', y: 120 },
  };
  const typeOf = (e) => { const t = e.type || e.slug || ''; return /pres/.test(t) ? 'pres' : (/general|national/.test(t) ? 'general' : 'local'); };
  const shortLabel = (e) => (typeOf(e) === 'local' ? `${e.n}회` : `${e.n}대`);

  function render(host, list, opts) {
    opts = opts || {};
    if (!host) return;
    if (!Array.isArray(list) || !list.length) { host.innerHTML = ''; return; }
    const href = opts.hrefFn || ((e) => `/archive/${e.slug}/`);
    const aria = opts.ariaFn || ((e) => e.name);
    const colorOf = (e, lane, cur) => (opts.nodeColorFn ? opts.nodeColorFn(e, lane, cur) : lane);  // 노드 색(기본=레인색)
    const ts = (e) => Date.parse(e.date);
    const curSlug = opts.current || list.slice().sort((a, b) => ts(b) - ts(a))[0].slug;
    const W = 720, H = 146, padL = 62, padR = 18, padT = 12, padB = 24;   // padL = 레인 라벨 전용 거터
    let min = Math.min(...list.map(ts)), max = Math.max(...list.map(ts));
    const span = (max - min) || 1; min -= span * 0.05; max += span * 0.05;
    const X = (t) => padL + (t - min) / (max - min) * (W - padL - padR);

    const y0 = new Date(min).getFullYear(), y1 = new Date(max).getFullYear();
    // 연도 눈금 간격 — 범위가 넓으면(역대 전체) 10년, 좁으면 2년.
    const step = (y1 - y0) > 30 ? 10 : 2;
    let axis = '';
    for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step) {
      const x = X(Date.parse(`${y}-01-01`));
      if (x < padL - 2 || x > W - padR + 2) continue;
      axis += `<line x1="${x.toFixed(1)}" y1="${padT}" x2="${x.toFixed(1)}" y2="${H - padB + 4}" stroke="var(--rule,#e6e9ef)" stroke-width="0.6"/>`;
      axis += `<text x="${x.toFixed(1)}" y="${H - 8}" font-size="10" fill="var(--ink-mute,#8a93a3)" text-anchor="middle">${y}</text>`;
    }
    let lanes = '', nodes = '';
    for (const key of ['pres', 'general', 'local']) {
      const L = LANE[key];
      lanes += `<line x1="${padL}" y1="${L.y}" x2="${W - padR}" y2="${L.y}" stroke="${L.color}" stroke-width="1" opacity="0.25"/>`;
      lanes += `<text x="${padL - 14}" y="${L.y + 4}" font-size="12" font-weight="700" fill="${L.color}" text-anchor="end">${L.label}</text>`;
    }
    for (const e of list) {
      const L = LANE[typeOf(e)];
      const x = X(ts(e)), isCur = e.slug === curSlug;
      const r = 6;   // 노드 크기 균일 — 선택은 외곽 링·중앙 흰점으로만 구분(크기 안 키움)
      const fill = colorOf(e, L.color, isCur);   // 노드 색(폴 허브=레인색 / 대시보드=중립+최신만 포인트)
      nodes += `<a href="${href(e)}" class="poll-tl-node${isCur ? ' is-current' : ''}" aria-label="${aria(e)}">`
        + `<title>${e.name} · ${e.date}${e.party ? ' · ' + e.party : ''}${isCur && opts.curSuffix ? ' ' + opts.curSuffix : ''}</title>`
        + (isCur ? `<circle cx="${x.toFixed(1)}" cy="${L.y}" r="${(r + 3).toFixed(1)}" fill="none" stroke="${L.color}" stroke-width="1.4" opacity="0.5"/>` : '')
        + `<circle cx="${x.toFixed(1)}" cy="${L.y}" r="${r}" fill="${fill}"/>`
        + (isCur ? `<circle cx="${x.toFixed(1)}" cy="${L.y}" r="2" fill="#fff"/>` : '')
        + `<text x="${x.toFixed(1)}" y="${(L.y - r - 4).toFixed(1)}" font-size="10.5" font-weight="700" fill="${L.color}" text-anchor="middle">${shortLabel(e)}</text>`
        + '</a>';
    }
    let chips = '<div class="poll-tl-chips">';
    for (const key of ['pres', 'general', 'local']) {
      const L = LANE[key];
      const row = list.filter((e) => typeOf(e) === key).sort((a, b) => ts(a) - ts(b));
      if (!row.length) continue;
      chips += `<div class="ptc-row"><span class="ptc-lane" style="color:${L.color}">${L.label}</span>`;
      for (const e of row) {
        const isCur = e.slug === curSlug;
        chips += `<a class="ptc-chip${isCur ? ' is-current' : ''}" href="${href(e)}" style="--c:${colorOf(e, L.color, isCur)}" title="${e.name} · ${e.date}${e.party ? ' · ' + e.party : ''}">${shortLabel(e)}</a>`;
      }
      chips += '</div>';
    }
    chips += '</div>';

    host.innerHTML = `<div class="poll-tl-scroll"><svg class="poll-tl-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="선거별 타임라인">${axis}${lanes}${nodes}</svg></div>`
      + chips + (opts.note ? `<p class="poll-tl-note">${opts.note}</p>` : '');
  }

  window.ElectionTimeline = { render };
})();
