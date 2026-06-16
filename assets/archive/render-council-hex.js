// 9회·8회 archive — 시군구 hex cluster 위에 의석 정당별 spiral.
// 부모 hex = sigungu_hex.json 좌표 / 자식 = 의석 수 N spiral (render-sigungu 패턴 reuse).
// 데이터: races[] tc=6(지역구) + tc=9(비례). 8회는 sigungu_summary scope, 9회는 race winner count.

(function () {
  const NS = 'http://www.w3.org/2000/svg';
  // 커서 따라다니는 커스텀 툴팁(네이티브 <title>보다 즉각). 시군구 hex 호버용.
  let _tip;
  function tipEl() {
    if (!_tip) { _tip = document.createElement('div'); _tip.className = 'hex-tip'; _tip.hidden = true; document.body.appendChild(_tip); }
    return _tip;
  }
  function bindTip(g, text) {
    g.style.cursor = 'default';
    g.addEventListener('mouseenter', () => { const t = tipEl(); t.textContent = text; t.hidden = false; });
    g.addEventListener('mousemove', (e) => { const t = tipEl(); t.style.left = (e.clientX + 12) + 'px'; t.style.top = (e.clientY + 14) + 'px'; });
    g.addEventListener('mouseleave', () => { tipEl().hidden = true; });
  }
  // hexgrid.js 헬퍼
  const COL_W = 24, ROW_H = 21, OFF_X = 30, OFF_Y = 30;
  function hexCenter(c, r) {
    const x = OFF_X + c * COL_W + (r % 2 ? COL_W / 2 : 0);
    const y = OFF_Y + r * ROW_H;
    return [x, y];
  }
  function hexPoints(cx, cy, R) {
    const pts = [];
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 6 + i * Math.PI / 3;
      pts.push(`${cx + R * Math.cos(a)},${cy + R * Math.sin(a)}`);
    }
    return pts.join(' ');
  }
  // 표준 axial hex 이웃 (pointy-top, 시계방향).
  const NEIGHBORS = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
  // 거리 layer의 ring 6L 개 cells 생성. 시작 = layer steps in NEIGHBORS[4] direction = (-L, L).
  function hexRing(layer) {
    const ring = [];
    let q = -layer, r = layer;
    for (let side = 0; side < 6; side++) {
      const [dq, dr] = NEIGHBORS[side];
      for (let step = 0; step < layer; step++) {
        ring.push([q, r]);
        q += dq; r += dr;
      }
    }
    return ring;
  }
  // Compact cluster — 중심(0,0) + 완전 ring 1..L-1 + partial ring L 둘레 균등 sample.
  function hexSpiral(N) {
    if (N <= 0) return [];
    const out = [[0, 0]];
    let layer = 0;
    while (out.length < N) {
      layer += 1;
      const ring = hexRing(layer);
      const ringSize = ring.length;  // 6 * layer
      const remaining = N - out.length;
      // 연속 채움 — 마지막 부분 링도 한쪽부터 이어서(듬성듬성 분산 안 함).
      for (let i = 0; i < Math.min(remaining, ringSize); i++) out.push(ring[i]);
    }
    return out;
  }

  // 권역(시도) 테두리 — 같은 시도 시군구 hex 그룹의 외곽선. 인접 셀의 시도가 다르거나(또는 없으면)
  // 그 변(edge)을 그어 시도 경계를 만든다. pointy-top odd-r 오프셋 격자 기준.
  function drawSidoBorders(svg, cells, R) {
    const k = (c, r) => c + ',' + r;
    const sidoAt = new Map();
    for (const c of cells) sidoAt.set(k(c.c, c.r), c.sido);
    // edge i(꼭짓점 i→i+1)가 향하는 이웃 방향. 꼭짓점 각 = PI/6 + i*PI/3.
    const EDGE_DIR = ['SE', 'SW', 'W', 'NW', 'NE', 'E'];
    const OFF = {
      0: { E: [1, 0], W: [-1, 0], SE: [0, 1], SW: [-1, 1], NE: [0, -1], NW: [-1, -1] },  // even row
      1: { E: [1, 0], W: [-1, 0], SE: [1, 1], SW: [0, 1], NE: [1, -1], NW: [0, -1] },     // odd row
    };
    const vert = (cx, cy, j) => [cx + R * Math.cos(Math.PI / 6 + j * Math.PI / 3),
      cy + R * Math.sin(Math.PI / 6 + j * Math.PI / 3)];
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'sido-border-layer');
    for (const cell of cells) {
      const [cx, cy] = hexCenter(cell.c, cell.r);
      const off = OFF[cell.r % 2];
      for (let i = 0; i < 6; i++) {
        const [dc, dr] = off[EDGE_DIR[i]];
        if (sidoAt.get(k(cell.c + dc, cell.r + dr)) === cell.sido) continue;  // 내부 경계 숨김
        const [x1, y1] = vert(cx, cy, i), [x2, y2] = vert(cx, cy, (i + 1) % 6);
        const ln = document.createElementNS(NS, 'line');
        ln.setAttribute('x1', x1.toFixed(1)); ln.setAttribute('y1', y1.toFixed(1));
        ln.setAttribute('x2', x2.toFixed(1)); ln.setAttribute('y2', y2.toFixed(1));
        ln.setAttribute('class', 'sido-border');
        g.appendChild(ln);
      }
    }
    svg.appendChild(g);
  }

  // sigungu별 의석 (지역구·비례) by party.
  // 구가 있는 시(부천시·용인시·수원시 등): tc=6 race.sigungu가 '부천시원미구' 등 →
  // hex의 '부천시' key와 매칭 위해 부모 sigungu 추출 (시·군·구 suffix 직전).
  function parentSigungu(sd, sg) {
    if (!sg) return sg;
    sg = sg.replace(/\([^)]*\)\s*$/, '')          // '중구(부산)' → '중구' (동음이의 — sido가 키에 있음)
      .replace(/제\d+(선거구)?$/, '')              // '인천시제1' → '인천시' (옛 대선 시 분할 선거구)
      .replace(/(시|군)[갑을병정무]구$/, '$1')      // '인천시갑구' → '인천시' (시·군 분할, 구=선거구)
      .replace(/([가-힣]+)[갑을병정무]구$/, '$1구')  // '동대문갑구' → '동대문구' (자치구 갑/을 분할)
      .replace(/구\s*[갑을병정무]$/, '구');         // '강남구갑' → '강남구' (현대 국회의원 표기)
    // '수원시장안구' → '수원시', '청주시상당구' → '청주시', '천안시동남구' → '천안시'
    const m = sg.match(/^(.+?[시군])(.+[구])$/);
    return m ? m[1] : sg;
  }
  function aggregateSigunguSeats(races) {
    const byKey = new Map();
    function add(sd, sg, party, n) {
      if (!n) return;
      const parent = parentSigungu(sd, sg);
      const k = `${sd}|${parent}`;
      const m = byKey.get(k) || new Map();
      m.set(party, (m.get(party) || 0) + n);
      byKey.set(k, m);
    }
    for (const r of races) {
      const sd = r.sido || '';
      const sg = r.sigungu || '';
      if (r.sg_typecode === '6') {
        if (r.scope === 'sigungu_summary') {
          for (const c of r.candidates || []) add(sd, sg, c.party || '무소속', c.seats || 0);
        } else if (r.scope === 'district') {
          // 중선거구 — 당선자(won) 전원 = 의석. won 없으면 1위만(fallback).
          const won = (r.candidates || []).filter((c) => c.won);
          if (won.length) {
            for (const c of won) add(sd, sg, c.party || '무소속', 1);
          } else {
            const top = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0))[0];
            if (top) add(sd, sg, top.party || '무소속', 1);
          }
        }
      } else if (r.sg_typecode === '9' && r.scope === 'proportional_sigungu') {
        for (const c of r.candidates || []) add(sd, sg, c.party || '무소속', c.seats || 0);
      }
    }
    return byKey;
  }

  // sigungu hex 위치 + 이름. 회차별 period 레이아웃을 우선 — 그 시점 시군구·이름(연기군·옛 군·
  // 도농통합 전 시 등)을 반영. 지선=sigungu_hex_local[회차], 대선=sigungu_hex_pres[회차]
  // (둘 다 그 시점 지리). 없으면 현대 sigungu_hex.json fallback.
  async function loadHexLayout(n, kind) {
    if (n != null) {
      const file = kind === 'presidential' ? 'sigungu_hex_pres.json' : 'sigungu_hex_local.json';
      const period = await fetch('data/geo/' + file)
        .then((r) => r.json()).then((m) => m[String(n)]).catch(() => null);
      if (period && period.length) return period;
    }
    return await fetch('data/geo/sigungu_hex.json').then((r) => r.json()).catch(() => []);
  }

  // 데이터 키 정규화 — 통합특별시·과거 행정명 매핑
  function normalizeKey(sido, sigungu) {
    // 전남광주통합특별시 / 전남광주특별시 → 광주광역시·전라남도 분리 매칭 위해 그대로 둠
    return `${sido}|${sigungu}`;
  }

  function render(svg, hexCells, sigunguSeats) {
    const maxC = Math.max(...hexCells.map((c) => c.c));
    const maxR = Math.max(...hexCells.map((c) => c.r));
    const w = OFF_X * 2 + (maxC + 1) * COL_W;
    const h = OFF_Y * 2 + (maxR + 1) * ROW_H;
    const EM = (typeof SIDO_EDGE_MARGIN !== 'undefined') ? SIDO_EDGE_MARGIN : 78;  // 좌우 외곽 라벨 여백
    svg.setAttribute('viewBox', `${-EM} 0 ${w + 2 * EM} ${h}`);
    svg.setAttribute('width', w + 2 * EM);
    svg.setAttribute('height', h);

    // 부모 hex 격자 콜리전 — pointy-top tiling spacing 정확:
    //   colW = R * sqrt(3),  rowH = R * 1.5.
    // COL_W=24 → R ≤ 24/sqrt(3) ≈ 13.86. ROW_H=21 → R ≤ 14.
    const PARENT_R = 13.85;
    const SMALL_R = 2.4;  // 모든 시군구 공통 hex 크기 (1석 = 1 hex 동일)

    // 시도명은 중앙 워터마크 대신 좌우 외곽 세로줄 라벨(history 방식)로 — 아래 hex 뒤 drawSidoEdgeLabels.

    let totalSeats = 0;
    const partyTotal = new Map();

    for (const cell of hexCells) {
      const seats = sigunguSeats.get(normalizeKey(cell.sido, cell.name));
      const [cx, cy] = hexCenter(cell.c, cell.r);
      const g = document.createElementNS(NS, 'g');
      // 클릭 → 아래 당선인 섹션을 그 시군구 기초의원으로 필터·스크롤(의석 있는 셀만).
      if (seats && seats.size) {
        g.style.cursor = 'pointer';
        g.addEventListener('click', () => window.Archive?.winners?.focus?.({ sido: cell.sido, q: cell.name, level: '기초의원' }));
      }
      // 부모 outline
      const outline = document.createElementNS(NS, 'polygon');
      outline.setAttribute('points', hexPoints(cx, cy, PARENT_R));
      outline.setAttribute('class', 'council-outline');
      outline.setAttribute('stroke-width', '0.8');
      g.appendChild(outline);
      // 시군구명 hover tooltip
      const tt = document.createElementNS(NS, 'title');
      const seatsStr = seats ? Array.from(seats.entries()).sort((a, b) => b[1] - a[1])
        .map(([p, n]) => `${p} ${n}`).join(' · ') : '데이터 없음';
      tt.textContent = `${cell.sido} ${cell.name} · ${seatsStr}`;
      g.appendChild(tt);
      // single-tier (세종·제주시·서귀포 등) — 회색 X
      if (cell.single_tier || !seats || seats.size === 0) {
        outline.setAttribute('class', 'council-outline no-data');
        svg.appendChild(g);
        continue;
      }
      const sorted = Array.from(seats.entries()).sort((a, b) => b[1] - a[1]);
      const N = sorted.reduce((s, [, n]) => s + n, 0);
      totalSeats += N;
      for (const [p, n] of sorted) partyTotal.set(p, (partyTotal.get(p) || 0) + n);
      const fills = [];
      for (const [p, n] of sorted) {
        for (let k = 0; k < n; k++) fills.push((typeof partyColor === 'function') ? partyColor(p) : '#999');
      }
      // small hex radius — N이 클수록 작게
      const smallR = SMALL_R;
      const spiral = hexSpiral(N);
      for (let i = 0; i < spiral.length; i++) {
        const [q, ar] = spiral[i];
        const dx = smallR * Math.sqrt(3) * (q + ar / 2);
        const dy = smallR * 1.5 * ar;
        const sx = cx + dx, sy = cy + dy;
        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', hexPoints(sx, sy, smallR * 0.95));
        poly.setAttribute('fill', fills[i] || '#e6e9ef');
        poly.setAttribute('stroke', 'rgba(255,255,255,0.5)');
        poly.setAttribute('stroke-width', '0.3');
        g.appendChild(poly);
      }
      svg.appendChild(g);
    }
    // 시도명 외곽 세로줄 라벨 (history 방식) — 헥스 위(여백)에.
    drawSidoBorders(svg, hexCells, PARENT_R);
    if (typeof drawSidoEdgeLabels === 'function') {
      const pts = hexCells.map((c) => { const [cx, cy] = hexCenter(c.c, c.r); return { sido: c.sido, cx, cy }; });
      drawSidoEdgeLabels(svg, pts);
    }
    return { totalSeats, partyTotal };
  }

  async function init(ctx) {
    const host = document.getElementById('ar-council-hex');
    if (!host) return;
    const races = ctx?.results?.races || [];
    const hexCells = await loadHexLayout(ctx?.meta?.electionN);
    if (!hexCells.length) return;
    const seats = aggregateSigunguSeats(races);
    if (seats.size === 0) {
      host.parentElement?.setAttribute('hidden', '');
      return;
    }
    host.parentElement?.removeAttribute('hidden');
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS);
    svg.setAttribute('class', 'council-hex-svg');
    const { totalSeats, partyTotal } = render(svg, hexCells, seats);
    host.innerHTML = '';
    host.appendChild(svg);
    // 범례 — 정당별 합계
    const legend = document.getElementById('ar-council-hex-legend');
    if (legend) {
      const sorted = Array.from(partyTotal.entries()).sort((a, b) => b[1] - a[1]);
      legend.innerHTML = sorted.map(([p, n]) => {
        const col = (typeof partyColor === 'function') ? partyColor(p) : '#999';
        return `<span class="ch-leg" style="color:${col}"><b>${n}</b> ${p}</span>`;
      }).join(' · ');
      const tot = document.getElementById('ar-council-hex-total');
      if (tot) tot.textContent = `${totalSeats}석 (시군구 의회) · hex 클릭 → 당선인`;
    }
  }

  // ── 시군구 투표율 맵 ──────────────────────────────────────────────
  // 같은 시군구 hex 레이아웃을 단색(투표율 그라데이션)으로. 소스 = 광역단체장(tc=3)의
  // 시군구 분해(가장 완전 — 세종/제주 자치구 등 기초장 없는 곳 포함). 없으면 기초장(tc=4).
  function turnoutBySigungu(races) {
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    // 투표율은 같은 날 같은 유권자라 어느 투표든 거의 동일 → 가장 완전한 소스부터 누적해
    // 빈 시군구를 메운다. 우선순위: 광역장 시군구분해(3) → 광역의원 합산(5, 전 시군구 커버) →
    // 기초장(4, 무투표 구멍) → 기초의원 합산(6) → 대선(1). sido 캐논·일반구→시 롤업(투·선 합산 후 율).
    const stripSfx = (s) => (s || '').replace(/\([^)]*\)\s*$/, '');
    const SOURCES = [
      ['3', 'sigungu'], ['5', 'district'], ['4', 'sigungu'], ['6', 'district'], ['1', 'sigungu'],
    ];
    const m = new Map();
    for (const [tc, scope] of SOURCES) {
      // 구 단위(period 레이아웃=수원시장안구)·시 단위(modern=수원시) 둘 다 키로 저장 — 레이아웃
      // 입도에 맞게 renderTurnout이 골라 씀. exact=접미사만 제거, rolled=일반구→시 합산.
      const exact = new Map(), rolled = new Map();
      for (const r of races || []) {
        if (r.scope !== scope || r.sg_typecode !== tc) continue;
        const el = r.electors || 0, vt = r.voters ?? r.voted ?? 0;
        if (el <= 0 || vt <= 0) continue;
        const sido = canon(r.sido);
        const ek = normalizeKey(sido, stripSfx(r.sigungu));
        const ea = exact.get(ek) || { e: 0, v: 0 }; ea.e += el; ea.v += vt; exact.set(ek, ea);
        const rk = normalizeKey(sido, parentSigungu(sido, r.sigungu));
        const ra = rolled.get(rk) || { e: 0, v: 0 }; ra.e += el; ra.v += vt; rolled.set(rk, ra);
      }
      for (const [k, a] of exact) if (!m.has(k)) m.set(k, a.v / a.e * 100);
      for (const [k, a] of rolled) if (!m.has(k)) m.set(k, a.v / a.e * 100);
    }
    return m;
  }

  // 단층제 시(세종특별자치시)는 기초 시군구가 없어 광역장 투표율이 sido scope에만 있음 →
  // 그 sido 셀을 sido 투표율로 채운다. 제주 행정시(sido=…도)는 도 평균이라 제외(시로 끝나는 sido만).
  function turnoutBySido(races) {
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    for (const tc of ['3', '4', '1']) {
      const m = new Map();
      for (const r of races || []) {
        if (r.scope !== 'sido' || r.sg_typecode !== tc) continue;
        const el = r.electors || 0, vt = r.voters ?? r.voted ?? 0;
        if (el > 0 && vt > 0) m.set(canon(r.sido), vt / el * 100);
      }
      if (m.size) return m;
    }
    return new Map();
  }

  function renderTurnout(svg, hexCells, tmap, sidoMap) {
    const maxC = Math.max(...hexCells.map((c) => c.c));
    const maxR = Math.max(...hexCells.map((c) => c.r));
    const w = OFF_X * 2 + (maxC + 1) * COL_W;
    const h = OFF_Y * 2 + (maxR + 1) * ROW_H;
    const EM = (typeof SIDO_EDGE_MARGIN !== 'undefined') ? SIDO_EDGE_MARGIN : 78;
    svg.setAttribute('viewBox', `${-EM} 0 ${w + 2 * EM} ${h}`);
    svg.setAttribute('width', w + 2 * EM); svg.setAttribute('height', h);
    const PARENT_R = 13.85;
    const color = window.Archive?.turnout?.color || (() => '#88a');
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    const stripSfx = (s) => (s || '').replace(/\([^)]*\)\s*$/, '');
    const valueOf = (c) => {
      const s = canon(c.sido);
      // exact(구 단위, period 레이아웃) 먼저 → rolled(시 단위, modern 레이아웃)
      let v = tmap.get(normalizeKey(s, stripSfx(c.name)));
      if (v == null) v = tmap.get(normalizeKey(s, parentSigungu(s, c.name)));
      if (v != null) return v;
      // 세종(유일한 특별자치시)은 기초 시군구가 없어 시군구 투표율이 없음 → sido 투표율로 채움.
      // 광역시 자치구 오인 방지로 '특별자치시'로만 한정(period 레이아웃엔 single_tier 플래그 없음).
      if (sidoMap && s.endsWith('특별자치시')) return sidoMap.get(s);
      return undefined;
    };
    // 상대 스케일 — 표시될 셀들의 최저~최고로 정규화(절대 스케일은 대선처럼 고투표율대에서 뭉침).
    const shownVals = hexCells.map(valueOf).filter((v) => v != null);
    const lo = shownVals.length ? Math.min(...shownVals) : 0;
    const hi = shownVals.length ? Math.max(...shownVals) : 1;
    let shown = 0;
    for (const cell of hexCells) {
      const [cx, cy] = hexCenter(cell.c, cell.r);
      const to = valueOf(cell);
      const g = document.createElementNS(NS, 'g');
      const poly = document.createElementNS(NS, 'polygon');
      poly.setAttribute('points', hexPoints(cx, cy, PARENT_R));
      if (to != null) {
        poly.setAttribute('fill', color(to, lo, hi));
        poly.setAttribute('class', 'council-turnout-cell');
        shown += 1;
      } else {
        poly.setAttribute('class', 'council-outline no-data');
      }
      poly.setAttribute('stroke', 'var(--bg, #fff)'); poly.setAttribute('stroke-width', '0.6');
      g.appendChild(poly);
      const label = `${cell.sido} ${cell.name} · ${to != null ? '투표율 ' + to.toFixed(1) + '%' : '데이터 없음'}`;
      const tt = document.createElementNS(NS, 'title');
      tt.textContent = label;
      g.appendChild(tt);
      bindTip(g, label);   // 커서 따라 즉각 툴팁(어디·몇 %)
      svg.appendChild(g);
    }
    drawSidoBorders(svg, hexCells, PARENT_R);
    if (typeof drawSidoEdgeLabels === 'function') {
      const pts = hexCells.map((c) => { const [cx, cy] = hexCenter(c.c, c.r); return { sido: c.sido, cx, cy }; });
      drawSidoEdgeLabels(svg, pts);
    }
    return { lo, hi, shown };
  }

  // 동적 섹션 주입 — #ar-council-hex 섹션 뒤(없으면 미주입). HTML 템플릿 변경 불필요.
  async function initTurnout(ctx) {
    const races = ctx?.results?.races || [];
    const tmap = turnoutBySigungu(races);
    if (tmap.size < 4) return;                       // 시군구 투표율 데이터 거의 없으면 생략
    const hexCells = await loadHexLayout(ctx?.meta?.electionN, ctx?.meta?.electionKind);
    if (!hexCells.length) return;
    // 앵커: 지선=#ar-council-hex 섹션 뒤, 대선=시도 투표율 뷰(#ar-pres-sido-hex) 섹션 뒤.
    const base = document.getElementById('ar-council-hex') || document.getElementById('ar-pres-sido-hex');
    const anchor = base?.closest('.ar-section') || base?.parentElement;
    if (!anchor || !anchor.parentElement) return;
    let sec = document.getElementById('ar-sgg-turnout');
    if (!sec) {
      sec = document.createElement('section');
      sec.className = 'ar-section'; sec.id = 'ar-sgg-turnout';
      sec.innerHTML = '<h2 class="ar-section-title">시군구 투표율</h2>'
        + '<p class="ar-source-line">시·군·구별 투표율(투표수/선거인수) — 짙을수록 높음.</p>'
        + '<div class="ar-sgg-turnout-host"></div><div class="ar-turnout-legend"></div>';
      anchor.parentElement.insertBefore(sec, anchor.nextSibling);
    }
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS); svg.setAttribute('class', 'council-hex-svg turnout-map');
    const { lo, hi, shown } = renderTurnout(svg, hexCells, tmap, turnoutBySido(races));
    const host = sec.querySelector('.ar-sgg-turnout-host');
    host.innerHTML = ''; host.appendChild(svg);
    const stops = window.Archive?.turnout?.stops || [[238, 243, 241], [78, 163, 145], [10, 74, 66]];
    const ramp = `rgb(${stops[0]}), rgb(${stops[1]}), rgb(${stops[2]})`;
    const leg = sec.querySelector('.ar-turnout-legend');
    leg.innerHTML = `<span>${lo.toFixed(1)}%</span><span class="ar-turnout-bar" style="background:linear-gradient(90deg,${ramp})"></span>`
      + `<span>${hi.toFixed(1)}%</span><span class="ar-turnout-range">이 선거 최저–최고 · ${shown}개 시군구</span>`;
  }

  // ── 시군구 1위 후보 결과 맵 (대선) ──────────────────────────────
  // 1위 후보 정당색 + 격차(1위−2위 pct) 명도. 승자독식 단색 금지를 명도로 절충 — 박빙 옅게·압도 진하게.
  function resultBySigungu(races, tc) {
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    const stripSfx = (s) => (s || '').replace(/\([^)]*\)\s*$/, '');
    const put = (m, k, w) => { if (!m.has(k)) m.set(k, w); };
    const m = new Map();
    for (const r of races || []) {
      if (r.scope !== 'sigungu' || r.sg_typecode !== tc) continue;
      const cs = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      if (!cs.length || !cs[0].party) continue;
      const win = { party: cs[0].party, name: cs[0].name, pct: cs[0].pct || 0,
        margin: (cs[0].pct || 0) - (cs[1] ? (cs[1].pct || 0) : 0) };
      const sido = canon(r.sido);
      put(m, normalizeKey(sido, stripSfx(r.sigungu)), win);
      put(m, normalizeKey(sido, parentSigungu(sido, r.sigungu)), win);
    }
    return m;
  }
  function marginOpacity(margin) { return 0.4 + 0.6 * Math.max(0, Math.min(1, margin / 40)); }

  function renderResult(svg, hexCells, rmap) {
    const maxC = Math.max(...hexCells.map((c) => c.c)), maxR = Math.max(...hexCells.map((c) => c.r));
    const w = OFF_X * 2 + (maxC + 1) * COL_W, h = OFF_Y * 2 + (maxR + 1) * ROW_H;
    const EM = (typeof SIDO_EDGE_MARGIN !== 'undefined') ? SIDO_EDGE_MARGIN : 78;
    svg.setAttribute('viewBox', `${-EM} 0 ${w + 2 * EM} ${h}`);
    svg.setAttribute('width', w + 2 * EM); svg.setAttribute('height', h);
    const PARENT_R = 13.85;
    const canon = (typeof canonSido === 'function') ? canonSido : (x) => x;
    const stripSfx = (s) => (s || '').replace(/\([^)]*\)\s*$/, '');
    const pcol = (typeof partyColor === 'function') ? partyColor : () => '#888';
    const valueOf = (c) => rmap.get(normalizeKey(canon(c.sido), stripSfx(c.name)))
      || rmap.get(normalizeKey(canon(c.sido), parentSigungu(canon(c.sido), c.name)));
    let shown = 0; const parties = new Set();
    for (const cell of hexCells) {
      const [cx, cy] = hexCenter(cell.c, cell.r);
      const win = valueOf(cell);
      const g = document.createElementNS(NS, 'g');
      const poly = document.createElementNS(NS, 'polygon');
      poly.setAttribute('points', hexPoints(cx, cy, PARENT_R));
      if (win) {
        poly.setAttribute('fill', pcol(win.party));
        poly.setAttribute('fill-opacity', marginOpacity(win.margin).toFixed(2));
        poly.setAttribute('class', 'council-result-cell');
        shown += 1; parties.add(win.party);
      } else { poly.setAttribute('class', 'council-outline no-data'); }
      poly.setAttribute('stroke', 'var(--bg, #fff)'); poly.setAttribute('stroke-width', '0.6');
      g.appendChild(poly);
      const label = win ? `${cell.sido} ${cell.name} · ${win.name}(${win.party}) ${win.pct.toFixed(1)}% · 격차 ${win.margin.toFixed(1)}%p`
        : `${cell.sido} ${cell.name} · 데이터 없음`;
      const tt = document.createElementNS(NS, 'title'); tt.textContent = label; g.appendChild(tt);
      bindTip(g, label);
      svg.appendChild(g);
    }
    drawSidoBorders(svg, hexCells, PARENT_R);
    if (typeof drawSidoEdgeLabels === 'function') {
      const pts = hexCells.map((c) => { const [cx, cy] = hexCenter(c.c, c.r); return { sido: c.sido, cx, cy }; });
      drawSidoEdgeLabels(svg, pts);
    }
    return { shown, parties: [...parties] };
  }

  // 시군구 1위 후보 결과 맵. host 주면 거기 렌더(폴), 없으면 아카이브 섹션 자동 생성(종합).
  async function initResult(ctx, host) {
    const rmap = resultBySigungu(ctx?.results?.races || [], '1');
    if (rmap.size < 4) return null;
    const hexCells = await loadHexLayout(ctx?.meta?.electionN, ctx?.meta?.electionKind);
    if (!hexCells.length) return null;
    let legHost = null, mapHost = host;
    if (!mapHost) {   // 아카이브(종합) — 시군구 투표율 섹션 앞에 '결과(격차 명도)' 섹션 주입
      const turn = document.getElementById('ar-sgg-turnout');
      const sidoSec = document.getElementById('ar-pres-sido-hex');
      const anchor = turn || (sidoSec && sidoSec.closest('.ar-section'));
      if (!anchor || !anchor.parentElement) return null;
      let sec = document.getElementById('ar-sgg-result');
      if (!sec) {
        sec = document.createElement('section'); sec.className = 'ar-section'; sec.id = 'ar-sgg-result';
        sec.innerHTML = '<h2 class="ar-section-title">시·군·구 1위 후보</h2>'
          + '<p class="ar-source-line">1위 후보 정당색 · 짙을수록 1·2위 격차 큼(승자독식 단색 대신 격차 명도).</p>'
          + '<div class="ar-sgg-result-host"></div><div class="ar-sgg-result-legend ch-leg-row"></div>';
        anchor.parentElement.insertBefore(sec, turn || anchor.nextSibling);
      }
      mapHost = sec.querySelector('.ar-sgg-result-host');
      legHost = sec.querySelector('.ar-sgg-result-legend');
    }
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS); svg.setAttribute('class', 'council-hex-svg result-map');
    const info = renderResult(svg, hexCells, rmap);
    mapHost.innerHTML = ''; mapHost.appendChild(svg);
    if (legHost && info.parties) {
      const pcol = (typeof partyColor === 'function') ? partyColor : () => '#888';
      legHost.innerHTML = info.parties.map((p) => `<span class="ch-leg" style="color:${pcol(p)}">■ ${p}</span>`).join(' ')
        + ' <span class="ar-genhex-note">· 명도 = 1·2위 격차</span>';
    }
    return info;
  }

  // archive/local.js render 끝나면 호출. window.Archive 네임스페이스 attach.
  window.Archive = window.Archive || {};
  window.Archive.councilHex = { init, initTurnout, initResult };
})();
