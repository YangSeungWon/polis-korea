// 선거별 3레인 타임라인 디렉터리 — 폴 허브(폴 링크)·대시보드(아카이브 링크) 공용 렌더러.
//   ElectionTimeline.render(host, list, opts)
//     list = [{slug, name, date, n, type?}]   (type 없으면 slug로 대선/총선/지선 판별)
//     opts = { hrefFn(e)→url, current(slug|null, 없으면 최신 강조), ariaFn(e)→str, note(html), curSuffix }
//   데스크톱=SVG 타임라인, 모바일=유형별 칩(CSS 미디어쿼리 토글). 스타일은 components.css(.poll-tl-*/.ptc-*).
(function () {
  'use strict';
  const LANE = {
    pres: { label: '대선', color: '#5b54d6', y: 30 },
    general: { label: '총선', color: '#168f8f', y: 62 },
    local: { label: '지선', color: '#c98a2e', y: 94 },
  };
  const typeOf = (e) => { const t = e.type || e.slug || ''; return /pres/.test(t) ? 'pres' : (/general|national/.test(t) ? 'general' : 'local'); };
  const shortLabel = (e) => (typeOf(e) === 'local' ? `${e.n}회` : `${e.n}대`);
  // 호버 미니맵 — 그 선거 대표 결과지도(아카이브 목록 썸네일과 같은 뷰).
  // 우선순위 표는 아래 생성 블록이다 — data/view_registry.json에서 sync된다.
  // 2026-08까지 여기 'dorling' 폴백이 손으로 적혀 있었고, 뷰 이름이 바뀌면 실패
  // 경로가 스스로를 display:none으로 숨겨 **조용히** 사라지는 자리였다.
  const KIND = { local: 'local', pres: 'presidential', general: 'general_election' };
// === VIEW_THUMBS auto-generated ===
  // data/view_registry.json thumb_priority에서 sync. 손으로 고치지 말 것 —
  // scripts/build/sync_view_thumbs_js.py 재실행으로 갱신.
  // 목록 썸네일·og 카드·타임라인 호버가 같은 그림을 고르게 하는 표다.
  const VIEW_THUMBS = {
    local: ['gov-hex', 'sgg-flat', 'council'],
    presidential: ['sido-hex', 'sido-grid', 'sgg-flat', 'sggturn-hex', 'electors'],
    general_election: ['seats', 'sidoseat-hex', 'district-hex', 'prop-grid'],
  };
// === /VIEW_THUMBS ===
  const chainOf = (e) => (VIEW_THUMBS[KIND[typeOf(e)]] || []);
  const mapUrl = (e) => {
    const c = chainOf(e);
    return c.length ? `/og/maps/${e.slug}/${c[0]}.png` : '';
  };

  function attachMiniMap(host) {
    let tip = document.getElementById('poll-tl-map-tip');
    if (!tip) {
      tip = document.createElement('div'); tip.id = 'poll-tl-map-tip';
      tip.innerHTML = '<img alt="">'; document.body.appendChild(tip);
    }
    const img = tip.querySelector('img');
    // 대표 뷰가 없는 회차(옛 선거·재캡처 전)면 우선순위를 따라 내려가고, 다 없으면 숨김.
    img.addEventListener('error', () => {
      const chain = img.dataset.chain ? img.dataset.chain.split(',') : [];
      const next = chain.shift();
      img.dataset.chain = chain.join(',');
      if (next) { img.src = img.src.replace(/\/[^/]+\.png$/, `/${next}.png`); return; }
      tip.style.display = 'none';
    });
    host.querySelectorAll('.poll-tl-node[data-map]').forEach((node) => {
      const url = node.getAttribute('data-map');
      node.addEventListener('mouseenter', () => {
        img.dataset.chain = (node.getAttribute('data-map-alt') || '');
        img.src = url; tip.style.display = 'block';
      });
      node.addEventListener('mousemove', (ev) => {
        const left = ev.clientX > window.innerWidth - 230 ? ev.clientX - 206 : ev.clientX + 16;
        tip.style.left = left + 'px';
        tip.style.top = Math.max(8, ev.clientY - 70) + 'px';
      });
      node.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
    });
  }

  function render(host, list, opts) {
    opts = opts || {};
    if (!host) return;
    if (!Array.isArray(list) || !list.length) { host.innerHTML = ''; return; }
    const href = opts.hrefFn || ((e) => `/archive/${e.slug}/`);
    const aria = opts.ariaFn || ((e) => e.name);
    const colorOf = (e, lane, cur) => (opts.nodeColorFn ? opts.nodeColorFn(e, lane, cur) : lane);  // 노드 색(기본=레인색)
    const ts = (e) => Date.parse(e.date);
    const curSlug = opts.current || list.slice().sort((a, b) => ts(b) - ts(a))[0].slug;
    const W = 720, H = 120, padL = 62, padR = 18, padT = 10, padB = 16;   // padL = 레인 라벨 거터. 숫자-인-서클이라 라벨 위 공간 불필요 → 세로 컴팩트
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
    const r = 10;   // 동그라미 안에 회차 숫자 — 라벨 겹침 해소(레인이 대선/총선/지선 구분, 접미사 불필요)
    const minGap = 2 * r + 1.5;   // 같은 레인 원이 안 겹치게 최소 간격(촘촘한 1979~81 대선 등)
    for (const key of ['pres', 'general', 'local']) {
      const L = LANE[key];
      const laneEvents = list.filter((e) => typeOf(e) === key).sort((a, b) => ts(a) - ts(b));
      let prevX = -Infinity;
      for (const e of laneEvents) {
        let x = X(ts(e));
        if (x < prevX + minGap) x = prevX + minGap;   // 겹치면 최소 간격만큼 오른쪽으로 밀어 모두 보이게(시간순 유지)
        prevX = x;
        const isCur = e.slug === curSlug;
        const fill = colorOf(e, L.color, isCur);   // 노드 색(폴 허브=레인색 / 대시보드=중립+최신만 포인트)
        const cx = x.toFixed(1);
        nodes += `<a href="${href(e)}" class="poll-tl-node${isCur ? ' is-current' : ''}" aria-label="${aria(e)}" data-map="${mapUrl(e)}" data-map-alt="${chainOf(e).slice(1).join(',')}">`
          + `<title>${e.name} · ${e.date}${e.party ? ' · ' + e.party : ''}${isCur && opts.curSuffix ? ' ' + opts.curSuffix : ''}</title>`
          + (isCur ? `<circle cx="${cx}" cy="${L.y}" r="${r + 3.5}" fill="none" stroke="${L.color}" stroke-width="1.6" opacity="0.55"/>` : '')
          + `<circle cx="${cx}" cy="${L.y}" r="${r}" fill="${fill}"/>`
          + `<text x="${cx}" y="${L.y}" dy=".34em" font-size="11" font-weight="700" fill="#fff" text-anchor="middle">${e.n}</text>`
          + '</a>';
      }
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
    attachMiniMap(host);
  }

  window.ElectionTimeline = { render };
})();
