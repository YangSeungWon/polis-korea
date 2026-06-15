// 선거별 여론조사 디렉터리 — data/polls/election_index.json(build_static 생성)을 3레인 타임라인으로.
//   대선/총선/지선 3줄을 같은 시간축에 → 각 유형의 4~5년 주기·선거 리듬이 한눈에. 노드 클릭 → /polls/{slug}/.
//   허브(/polls.html)·각 per-election 페이지 모두에 노출(현재/최근 회차 강조).
(function () {
  'use strict';
  const host = document.getElementById('poll-election-index');
  if (!host) return;
  const sec = host.closest('.poll-index-sec');
  const cur = (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.election
    && window.__INITIAL_STATE__.election.slug) || null;

  const LANE = {
    pres:    { label: '대선', color: '#5b54d6', y: 44 },
    general: { label: '총선', color: '#168f8f', y: 82 },
    local:   { label: '지선', color: '#c98a2e', y: 120 },
  };
  const typeOf = (slug) => (/pres/.test(slug) ? 'pres' : /general/.test(slug) ? 'general' : 'local');
  const shortLabel = (e) => (typeOf(e.slug) === 'local' ? `${e.n}회` : `${e.n}대`);

  function buildSVG(list) {
    const W = 720, H = 146, padL = 50, padR = 18, padT = 12, padB = 24;
    const ts = (e) => Date.parse(e.date);
    let min = Math.min(...list.map(ts)), max = Math.max(...list.map(ts));
    const span = (max - min) || 1; min -= span * 0.05; max += span * 0.05;
    const X = (t) => padL + (t - min) / (max - min) * (W - padL - padR);
    const curSlug = cur || list.slice().sort((a, b) => ts(b) - ts(a))[0].slug;  // 허브엔 최신 강조

    // 연도 눈금(2년 간격) + 세로 가이드
    const y0 = new Date(min).getFullYear(), y1 = new Date(max).getFullYear();
    let axis = '';
    for (let y = Math.ceil(y0 / 2) * 2; y <= y1; y += 2) {
      const x = X(Date.parse(`${y}-01-01`));
      if (x < padL - 2 || x > W - padR + 2) continue;
      axis += `<line x1="${x.toFixed(1)}" y1="${padT}" x2="${x.toFixed(1)}" y2="${H - padB + 4}" stroke="var(--rule,#e6e9ef)" stroke-width="0.6"/>`;
      axis += `<text x="${x.toFixed(1)}" y="${H - 8}" font-size="10" fill="var(--ink-mute,#8a93a3)" text-anchor="middle">${y}</text>`;
    }

    let lanes = '', nodes = '';
    for (const key of ['pres', 'general', 'local']) {
      const L = LANE[key];
      lanes += `<line x1="${padL}" y1="${L.y}" x2="${W - padR}" y2="${L.y}" stroke="${L.color}" stroke-width="1" opacity="0.25"/>`;
      lanes += `<text x="${padL - 10}" y="${L.y + 4}" font-size="12" font-weight="700" fill="${L.color}" text-anchor="end">${L.label}</text>`;
    }
    for (const e of list) {
      const L = LANE[typeOf(e.slug)];
      const x = X(ts(e)), isCur = e.slug === curSlug;
      const r = isCur ? 7.5 : 5.5;
      nodes += `<a href="/polls/${e.slug}/" class="poll-tl-node${isCur ? ' is-current' : ''}" aria-label="${e.name} 여론조사 vs 실제">`
        + `<title>${e.name} · ${e.date}${isCur ? ' (최근)' : ''}</title>`
        + (isCur ? `<circle cx="${x.toFixed(1)}" cy="${L.y}" r="${(r + 3).toFixed(1)}" fill="none" stroke="${L.color}" stroke-width="1.4" opacity="0.5"/>` : '')
        + `<circle cx="${x.toFixed(1)}" cy="${L.y}" r="${r}" fill="${L.color}"/>`
        + (isCur ? `<circle cx="${x.toFixed(1)}" cy="${L.y}" r="2" fill="#fff"/>` : '')
        + `<text x="${x.toFixed(1)}" y="${(L.y - r - 4).toFixed(1)}" font-size="10.5" font-weight="700" fill="${L.color}" text-anchor="middle">${shortLabel(e)}</text>`
        + '</a>';
    }
    // 모바일용 컴팩트 칩 — SVG 타임라인 대신 유형별 3줄(연도순). CSS 미디어쿼리로 토글.
    let chips = '<div class="poll-tl-chips" aria-label="선거별 여론조사 (유형별)">';
    for (const key of ['pres', 'general', 'local']) {
      const L = LANE[key];
      const row = list.filter((e) => typeOf(e.slug) === key).sort((a, b) => ts(a) - ts(b));
      if (!row.length) continue;
      chips += `<div class="ptc-row"><span class="ptc-lane" style="color:${L.color}">${L.label}</span>`;
      for (const e of row) {
        const isCur = e.slug === curSlug;
        chips += `<a class="ptc-chip${isCur ? ' is-current' : ''}" href="/polls/${e.slug}/"`
          + ` style="--c:${L.color}" title="${e.name} · ${e.date}">${shortLabel(e)}${isCur ? ' ★' : ''}</a>`;
      }
      chips += '</div>';
    }
    chips += '</div>';

    return `<div class="poll-tl-scroll"><svg class="poll-tl-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="선거별 여론조사 타임라인">`
      + `${axis}${lanes}${nodes}</svg></div>`
      + chips
      + '<p class="poll-tl-note">2016년 이후 선거만 (NESDC 등록 시작). 그 이전은 <a href="/history.html">역대 결과 →</a></p>';
  }

  fetch('data/polls/election_index.json')
    .then((r) => (r.ok ? r.json() : []))
    .then((list) => {
      if (!Array.isArray(list) || !list.length) { sec && sec.remove(); return; }
      host.innerHTML = buildSVG(list);
    })
    .catch(() => { sec && sec.remove(); });
})();
