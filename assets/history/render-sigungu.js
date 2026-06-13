// history.js 시군구 hex — 대선·지선 기초단체장 시군구별 결과.

// === 시군구 hex ===

function renderSigunguHex() {
  const svg = $('#hex2');
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  // 대선만 일반구별 개표 단위 (legacy sigungu hex). 지선은 통합 시장이라 base hex.
  // 총선은 지역구(district_hex_*.json) — renderDistrictHex가 별도 처리.
  // 회차별 그 시점 시군구 레이아웃 — 대선(hexPres 2~18대), 지선 기초장(hexLocal 1~9회: 창원·청주
  // 분리 등). 없으면 현대(대선=legacy 25구, 지선=hexData).
  const periodHex = state.type === 'presidential' ? state.hexPres?.[state.n]
    : state.type === 'local' ? state.hexLocal?.[state.n] : null;
  const useLegacy = state.hexLegacy && state.type === 'presidential';
  let data = periodHex || (useLegacy ? state.hexLegacy : state.hexData);
  if (!data?.length) return;
  // 회차별 자동 hide:
  //   1) lifecycle since/until — 행정구역 신설·폐지 (확장 가능, SIGUNGU_HEX_LIFECYCLE 참조)
  //   2) 데이터 매칭 — 그 회차에 결과 없는 cell 자동 숨김
  const el = (state.elections[state.type]?.elections || []).find((x) => x.n === state.n);
  const electionDate = el?.date || '';
  // 각 cell에 그 시점 effective sido/name 주입 후 매칭 — beforeAs/afterAs 처리 일관.
  data = data.flatMap((d) => {
    const eff = effectiveCell(d, electionDate);
    if (!eff) return [];
    // _borrowed: 그 시점 부모 구로 해석된 셀(예 5대 강남→성동). 같은 구로 묶이는 여러 셀 중
    // 원래 이름이 그 구인 셀(canonical)만 클러스터/원, 나머지는 색만 — 중복카운트 방지.
    const borrowed = eff.sido !== d.sido || eff.name !== d.name;
    if (!resultForSigungu(eff.sido, eff.name)) {
      // 현재 직(office) 데이터 없음 — 그 시점 '존재하는' 시군구(광역단체장 데이터 보유)면
      // 숨기지 말고 no-data 회색 셀로 유지(내부 구멍 방지). 세종은 기초단체장이 없어
      // 기초장 뷰에서 구멍이었음. 미존재(통폐합 전 등)는 광역장도 없어 그대로 숨김.
      const gov = state.type === 'local' ? state.results?.offices?.['광역단체장'] : null;
      if (gov && resultForSigungu(eff.sido, eff.name, gov)) {
        return [{ ...d, sido: eff.sido, name: eff.name, _borrowed: borrowed }];
      }
      return [];
    }
    return [{ ...d, sido: eff.sido, name: eff.name, _borrowed: borrowed }];
  });
  if (!data.length) return;  // 매칭 결과 0 → 빈 배열이면 viewBox -Infinity 방지
  const cs = data.map((d) => d.c);
  const rs = data.map((d) => d.r);
  const minC = Math.min(...cs), minR = Math.min(...rs);
  const maxC = Math.max(...cs), maxR = Math.max(...rs);
  const r = 22;
  const colW = r * Math.sqrt(3);
  const rowH = r * 1.5;
  const w = (maxC - minC + 2) * colW;
  const h = (maxR - minR + 2) * rowH;
  const M = SIDO_EDGE_MARGIN;   // 좌우 시도 라벨 세로줄 공간
  svg.setAttribute('viewBox', `${-M} 0 ${Math.ceil(w) + 2 * M} ${Math.ceil(h)}`);
  const offX = -minC * colW + colW / 2;
  const offY = -minR * rowH + rowH;

  // (c,r) → cell lookup (시도 경계 감지에 사용)
  const cellAt = new Map();
  for (const d of data) cellAt.set(`${d.c},${d.r}`, d);
  // nbrs·NBR_TO_EDGE·corner → assets/hexgrid.js (공용)

  // 사이즈 모드: 격자(시군구당 득표 비례 작은 hex·대선 기본) / dorling(원) / 그 외=단일 hex.
  // 지선·총선은 '동일'(단일 hex, 1위 정당색). 제거된 '반지름' 등 stale 값은 단일 hex로 처리.
  const sizingMode = state.sizing || '동일';
  let maxVoted = 0;
  for (const d of data) {
    const result = resultForSigungu(d.sido, d.name);
    if (result?.voted && !result._fill) maxVoted = Math.max(maxVoted, result.voted);  // 차용 셀 제외(전체 모도시라 스케일 왜곡)
  }

  // 격자 hex 모드: 시군구당 N개 작은 hex 패킹 (1 hex = 2만표)
  if (sizingMode === '격자' && maxVoted > 0) {
    const unit = 20000;  // 1 hex = 2만표 (고정 — 회차·선거 동일 단위로 비교 가능)
    const smallR = 3.2;  // unit ↓ → N ↑ (×2.5) → 면적 보존 위해 r √2.5 분의 1
    // axial 좌표 BFS 스파이럴 (1..N hex 배치)
    function hexSpiral(N) {
      const out = [[0, 0]];
      if (N <= 1) return out;
      const seen = new Set(['0,0']);
      let frontier = [[0, 0]];
      const DIRS = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]];
      while (out.length < N) {
        const next = [];
        for (const [q, ar] of frontier) {
          for (const [dq, dr] of DIRS) {
            const nq = q + dq, nr = ar + dr;
            const key = nq + ',' + nr;
            if (seen.has(key)) continue;
            seen.add(key);
            next.push([nq, nr]);
            out.push([nq, nr]);
            if (out.length >= N) return out;
          }
        }
        frontier = next;
      }
      return out;
    }
    // 후보별 hex 개수 — 큰 정수 잔여(largest remainder) 방식으로 N에 정확히 맞춤.
    function allocateByVotes(cands, N) {
      const total = cands.reduce((s, c) => s + (c.votes || 0), 0);
      if (!total) return cands.map(() => 0);
      const raw = cands.map((c) => (c.votes || 0) * N / total);
      const floors = raw.map(Math.floor);
      let rem = N - floors.reduce((a, b) => a + b, 0);
      const fracs = raw.map((v, i) => ({ i, f: v - Math.floor(v) }))
                       .sort((a, b) => b.f - a.f);
      for (let k = 0; k < rem; k++) floors[fracs[k].i] += 1;
      return floors;
    }
    // 시도명 외곽 라벨 (무리 위쪽 바깥, 작게) — 대선·총선·지선 공통.
    drawSidoEdgeLabels(svg, data.map((d) => {
      const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
      return { sido: d.sido, cx, cy };
    }));

    let selectedG = null;
    for (const d of data) {
      const result = resultForSigungu(d.sido, d.name);
      if (!result?.voted) continue;
      // 단일 hex로 그릴 셀: 모도시 broadcast(_fill) 또는 그 시점 부모 구로 병합된 셀(_borrowed).
      // 같은 구의 canonical 셀만 클러스터 → 중복카운트 없음.
      const isFill = !!result._fill || d._borrowed;
      const N = isFill ? 1 : Math.max(1, Math.ceil(result.voted / unit));
      const [cx0, cy0] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
      const cands = (result.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      const alloc = allocateByVotes(cands, N);
      const top = cands[0];
      const isSelected = state.selected
        && state.selected.sido === d.sido && state.selected.name === d.name;
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.style.cursor = 'pointer';
      g.addEventListener('click', () => {
        state.selected = { sido: d.sido, name: d.name, code: d.code };
        renderAll(); renderDetail();
      });
      const tt = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      const _psido = periodSidoName(d.sido, electionDate);
      tt.textContent = top
        ? `${_psido} ${fmtUnitName(d.name)} · ${candLabel(top)} (${top.party}) ${top.uncontested ? '무투표 당선' : top.pct?.toFixed(1) + '%'}${result._fill ? ' · 모도시 결과(당시 미분리)' : d._borrowed ? ' · 당시 미분리(부모 구)' : ' · ' + N + '석/표'}`
        : `${_psido} ${fmtUnitName(d.name)}`;
      g.appendChild(tt);
      // 셀별 footprint(테마 반투명 흰 배경) — stroke 없이 fill만. 같은 구 인접 셀끼리 이어져
      // 병합 구가 한 면처럼 보임. 구 경계선은 루프 후 drawHexBorders(구 키)로 일괄.
      const fp = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      fp.setAttribute('points', hexPoints(cx0, cy0, 22));
      fp.setAttribute('class', 'sig-outline');
      fp.setAttribute('stroke', 'none');
      g.appendChild(fp);
      if (isFill) {
        // 그 구 자체 득표 없음(당시 미분리) — 부모/모도시 1위 색으로 셀 채움. 병합 구가 하나의
        // 면으로 보이게 cell 거의 가득(21). 클러스터는 canonical 셀에만 → 중복카운트/넘침 없음.
        const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        poly.setAttribute('points', hexPoints(cx0, cy0, 21));
        poly.setAttribute('fill', top ? partyColor(top.party) : '#e6e9ef');
        poly.setAttribute('opacity', '0.85');   // 차용(자체 득표 없음)임을 살짝 구분
        g.appendChild(poly);
      } else {
        // 후보별 hex 배정 (스파이럴 순서대로 1위→2위→... 채움)
        const spiral = hexSpiral(N);
        const fills = [];
        for (let i = 0; i < cands.length; i++) {
          for (let k = 0; k < alloc[i]; k++) fills.push(partyColor(cands[i].party));
        }
        while (fills.length < N) fills.push('#e6e9ef');  // 안전 fallback
        // smallR 클램프 — 큰 셀(합산 등)이 셀 반경(22) 밖으로 넘치지 않게.
        let ext = 0;
        for (const [q, ar] of spiral) ext = Math.max(ext, Math.hypot(Math.sqrt(3) * (q + ar / 2), 1.5 * ar));
        const sr = Math.min(smallR, 20 / (ext + 1));
        for (let i = 0; i < spiral.length; i++) {
          const [q, ar] = spiral[i];
          const dx = sr * Math.sqrt(3) * (q + ar / 2);
          const dy = sr * 1.5 * ar;
          const sx = cx0 + dx, sy = cy0 + dy;
          const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
          poly.setAttribute('points', hexPoints(sx, sy, sr - 0.4));
          poly.setAttribute('fill', fills[i] || '#e6e9ef');
          // 작은 hex는 stroke 없음 — selected는 큰 outline에서만 강조.
          g.appendChild(poly);
        }
      }
      // 시군구 라벨 — canonical 셀(클러스터 있는)에만. 병합 구의 차용 셀은 같은 이름 중복이라 생략.
      const label = shortSigunguLabel(d.name, d.sido);
      if (label.short && !isFill) {
        const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        txt.setAttribute('x', cx0);
        txt.setAttribute('text-anchor', 'middle');
        txt.setAttribute('y', cy0 - 8);
        txt.setAttribute('font-size', label.short.length > 3 ? '6' : '8');
        txt.setAttribute('font-weight', '700');
        // 격자 모드 시군구 라벨 — bg halo로 모든 배경 위에 가독성 (테마-인지).
        txt.setAttribute('class', 'hist-sigungu-label');
        txt.setAttribute('pointer-events', 'none');
        txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
        txt.textContent = label.short;
        g.appendChild(txt);
      }
      svg.appendChild(g);
      if (isSelected) selectedG = g;
    }
    // 구 영역 외곽선 (옛 회차 병합 구는 내부선 없이 하나로) — 같은 시점-구끼리 묶음. 테마 인지.
    const guKey = (x) => `${x.sido}|${x.name}`;
    drawHexBorders(svg, data, cellAt, colW, rowH, offX, offY, r, '1.0', false, guKey, 'gu-outline');
    // 시도 경계 굵은 선 — 격자 모드도 cell 위치가 동일 모드와 같으므로 적용 가능.
    drawHexBorders(svg, data, cellAt, colW, rowH, offX, offY, r, '1.8', true);
    // 선택 cell cluster를 위로 + 선택 구 영역 외곽선을 맨 위에 — 경계·인접 셀이 가리지 않게.
    if (selectedG) svg.appendChild(selectedG);
    if (state.selected) {
      const selCells = data.filter((x) => x.sido === state.selected.sido && x.name === state.selected.name);
      if (selCells.length) {
        const selAt = new Map(selCells.map((x) => [`${x.c},${x.r}`, x]));
        drawHexBorders(svg, selCells, selAt, colW, rowH, offX, offY, r, '3.5', true, guKey, 'gu-outline is-selected');
      }
    }
    return;
  }

  // Dorling cartogram: 원, force-directed packing
  if (sizingMode === 'dorling' && maxVoted > 0) {
    // 차용 셀(병합 구) 제외 — 구당 원 하나(canonical 셀 위치)로 중복 방지.
    const nodes = data.filter((d) => !d._borrowed).map((d) => {
      const result = resultForSigungu(d.sido, d.name);
      // 차용(_fill) 셀은 모도시 전체 득표라 v-비례 금지 — 작은 대표 원.
      const v = (result && !result._fill) ? (result.voted || 0) : 0;
      const top = topCandidate(result);
      const sec = result?.candidates?.length >= 2 ? result.candidates[1] : null;
      const gap = top && sec ? top.pct - sec.pct : null;
      const [cx0, cy0] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
      return {
        d, result, top,
        cx0, cy0,
        radius: v > 0 ? Math.max(3, (r - 0.7) * Math.sqrt(v / maxVoted)) : 3,
        fill: top ? partyColor(top.party) : '#e6e9ef',
        op: top ? gapOpacity(gap) : 1,
      };
    });
    for (const n of nodes) { n.cx = n.cx0; n.cy = n.cy0; }
    // Force-directed (30 iterations): repel overlaps + anchor to original
    for (let iter = 0; iter < 40; iter++) {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = b.cx - a.cx, dy = b.cy - a.cy;
          const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
          const overlap = a.radius + b.radius - dist;
          if (overlap > 0) {
            const push = overlap * 0.5 / dist;
            a.cx -= push * dx; a.cy -= push * dy;
            b.cx += push * dx; b.cy += push * dy;
          }
        }
      }
      // Anchor towards original position
      for (const n of nodes) {
        n.cx += (n.cx0 - n.cx) * 0.05;
        n.cy += (n.cy0 - n.cy) * 0.05;
      }
    }
    // 시도별 그룹핑 (권역 테두리 + 라벨 centroid 공용)
    const sidoGroups = new Map();
    for (const n of nodes) {
      const k = n.d.sido;
      const list = sidoGroups.get(k) || [];
      list.push(n);
      sidoGroups.set(k, list);
    }
    // 권역 테두리 — 시도별 convex hull (각 node의 원 외곽 padding 포함).
    // monotone chain 알고리즘. nodes 적어 성능 부담 X.
    function _convexHull(pts) {
      const arr = [...pts].sort((a, b) => a.x - b.x || a.y - b.y);
      const cross = (O, A, B) => (A.x - O.x) * (B.y - O.y) - (A.y - O.y) * (B.x - O.x);
      const lower = [];
      for (const p of arr) {
        while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
        lower.push(p);
      }
      const upper = [];
      for (let i = arr.length - 1; i >= 0; i--) {
        const p = arr[i];
        while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
        upper.push(p);
      }
      return lower.slice(0, -1).concat(upper.slice(0, -1));
    }
    for (const [sido, list] of sidoGroups) {
      const expanded = [];
      for (const n of list) {
        const pad = n.radius + 3;
        for (let k = 0; k < 12; k++) {
          const a = (k * Math.PI * 2) / 12;
          expanded.push({ x: n.cx + Math.cos(a) * pad, y: n.cy + Math.sin(a) * pad });
        }
      }
      const hull = _convexHull(expanded);
      if (hull.length < 3) continue;
      const points = hull.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
      const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      poly.setAttribute('points', points);
      poly.setAttribute('fill', 'rgba(10,14,26,0.04)');
      poly.setAttribute('stroke', 'rgba(10,14,26,0.45)');
      poly.setAttribute('stroke-width', '1.5');
      poly.setAttribute('stroke-linejoin', 'round');
      poly.setAttribute('pointer-events', 'none');
      svg.appendChild(poly);
    }
    // 시도명 외곽 라벨 (무리 위쪽 바깥, 작게) — grid 모드와 동일.
    drawSidoEdgeLabels(svg, [...sidoGroups].flatMap(([s, list]) =>
      list.map((n) => ({ sido: s, cx: n.cx, cy: n.cy }))));
    // 파이 슬라이스 path (top 기준 시계방향). 면적=표수(원), 파이=후보 구성.
    const pieSlice = (cx, cy, rad, a0, a1) => {
      const x0 = cx + rad * Math.cos(a0), y0 = cy + rad * Math.sin(a0);
      const x1 = cx + rad * Math.cos(a1), y1 = cy + rad * Math.sin(a1);
      const large = (a1 - a0) > Math.PI ? 1 : 0;
      return `M ${cx.toFixed(2)} ${cy.toFixed(2)} L ${x0.toFixed(2)} ${y0.toFixed(2)} `
           + `A ${rad.toFixed(2)} ${rad.toFixed(2)} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
    };
    for (const n of nodes) {
      const isSelected = state.selected
        && state.selected.sido === n.d.sido && state.selected.name === n.d.name;
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.style.cursor = 'pointer';
      g.addEventListener('click', () => {
        state.selected = { sido: n.d.sido, name: n.d.name, code: n.d.code };
        renderAll(); renderDetail();
      });
      // 득표 비례 파이 — 셀 안에서 후보 구성 표시(승자독식 색 왜곡 제거).
      const cands = (n.result?.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
      const totalV = cands.reduce((s, c) => s + (c.votes || 0), 0);
      if (totalV > 0 && cands.filter((c) => (c.votes || 0) > 0).length > 1) {
        let a0 = -Math.PI / 2;
        for (const cand of cands) {
          const frac = (cand.votes || 0) / totalV;
          if (frac <= 0) continue;
          const a1 = a0 + frac * 2 * Math.PI;
          const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          p.setAttribute('d', pieSlice(n.cx, n.cy, n.radius, a0, a1));
          p.setAttribute('fill', partyColor(cand.party));
          g.appendChild(p);
          a0 = a1;
        }
        const ring = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        ring.setAttribute('cx', n.cx); ring.setAttribute('cy', n.cy); ring.setAttribute('r', n.radius);
        ring.setAttribute('fill', 'none');
        ring.setAttribute('stroke', '#0a0e1a');
        ring.setAttribute('stroke-width', isSelected ? '1.6' : '0.5');
        g.appendChild(ring);
      } else {
        // 단독·무투표 등 후보 1명 — 단색 원
        const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        c.setAttribute('cx', n.cx);
        c.setAttribute('cy', n.cy);
        c.setAttribute('r', n.radius);
        c.setAttribute('fill', n.fill);
        c.setAttribute('stroke', '#0a0e1a');
        c.setAttribute('stroke-width', isSelected ? '1.6' : '0.5');
        g.appendChild(c);
      }
      const tt = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      tt.textContent = n.top
        ? `${n.d.sido} ${n.d.name} · ${candLabel(n.top)} (${n.top.party}) ${n.top.uncontested ? '무투표 당선' : n.top.pct?.toFixed(1) + '%'}`
        : `${n.d.sido} ${n.d.name}`;
      g.appendChild(tt);
      // 라벨 — 큰 원만
      if (n.radius >= 10 && n.top) {
        const lbl = shortSigunguLabel(n.d.name, n.d.sido);
        if (lbl.short) {
          const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          txt.setAttribute('x', n.cx);
          txt.setAttribute('y', n.cy + 3);
          txt.setAttribute('text-anchor', 'middle');
          txt.setAttribute('font-size', '7');
          txt.setAttribute('font-weight', '600');
          // dorling 원 내부 텍스트 — 배경(1위 정당색)에 맞춰 자동.
          txt.setAttribute('fill', n.fill ? pickTextColor(n.fill) : 'var(--ink)');
          txt.setAttribute('pointer-events', 'none');
          txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
          txt.textContent = lbl.short;
          g.appendChild(txt);
        }
      }
      svg.appendChild(g);
    }
    return;
  }

  // fallback(무투표·결과없음) — 시도 라벨 백그라운드 (cells보다 먼저 그려 hex 위에 덮이도록).
  {
    const sidoCenters = new Map();
    for (const d of data) {
      const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
      const k = d.sido;
      const c = sidoCenters.get(k) || { sx: 0, sy: 0, n: 0 };
      c.sx += cx; c.sy += cy; c.n += 1;
      sidoCenters.set(k, c);
    }
    for (const [sido, c] of sidoCenters) {
      const lbl = SIDO_LABEL_SHORT[sido] || sido;
      const tx = c.sx / c.n;
      const ty = c.sy / c.n;
      const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t.setAttribute('x', tx);
      t.setAttribute('y', ty);
      t.setAttribute('text-anchor', 'middle');
      t.setAttribute('dominant-baseline', 'middle');
      t.setAttribute('font-size', '44');
      t.setAttribute('font-weight', '800');
      t.setAttribute('class', 'hist-sido-bg-label');
      t.setAttribute('pointer-events', 'none');
      t.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      t.textContent = lbl;
      svg.appendChild(t);
    }
  }

  for (const d of data) {
    const [cx, cy] = hexCenter(d.c, d.r, colW, rowH, offX, offY);
    const result = resultForSigungu(d.sido, d.name);
    const top = topCandidate(result);
    const sec = result?.candidates?.length >= 2 ? result.candidates[1] : null;
    const gap = top && sec ? top.pct - sec.pct : null;
    const fill = top ? partyColor(top.party) : '#e6e9ef';
    const opacity = top ? gapOpacity(gap) : 1;
    const cellR = r - 0.7;  // 균일 단일 hex (무투표·결과없음 fallback)
    const isSelected = state.selected
      && state.selected.sido === d.sido && state.selected.name === d.name;

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.style.cursor = result ? 'pointer' : 'default';
    g.addEventListener('click', () => {
      state.selected = { sido: d.sido, name: d.name, code: d.code };
      renderAll();
      renderDetail();
    });

    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('class', 'hex-cell ' + (top ? 'has-data' : 'no-data') + (isSelected ? ' is-selected' : ''));
    poly.setAttribute('points', hexPoints(cx, cy, cellR));
    poly.setAttribute('fill', fill);
    poly.setAttribute('stroke', '#0a0e1a');
    poly.setAttribute('stroke-width', isSelected ? '1.6' : '0.7');
    poly.setAttribute('fill-opacity', opacity);
    g.appendChild(poly);

    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = top
      ? `${d.sido} ${d.name} · ${candLabel(top)} (${top.party}) ${top.uncontested ? '무투표 당선' : top.pct?.toFixed(1) + '%'}`
      : `${d.sido} ${d.name} · 데이터 없음`;
    g.appendChild(title);

    // 라벨 — 작은 hex는 라벨 생략 (가독성)
    const label = shortSigunguLabel(d.name, d.sido);
    if (label.short && cellR >= 8) {
      const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      txt.setAttribute('x', cx);
      txt.setAttribute('text-anchor', 'middle');
      txt.setAttribute('font-weight', '600');
      // 단일 hex 셀 라벨 — 배경(정당색·투명도)에 맞춰 흰/검 자동.
      txt.setAttribute('fill', top ? pickTextColor(fill, opacity) : 'var(--ink)');
      txt.setAttribute('pointer-events', 'none');
      txt.setAttribute('font-family', 'Pretendard, system-ui, sans-serif');
      if (label.prefix) {
        const tp1 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        tp1.setAttribute('x', cx);
        tp1.setAttribute('y', cy - 2);
        tp1.setAttribute('font-size', '6');
        tp1.setAttribute('opacity', '0.75');
        tp1.textContent = label.prefix;
        txt.appendChild(tp1);
        const tp2 = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        tp2.setAttribute('x', cx);
        tp2.setAttribute('y', cy + 8);
        tp2.setAttribute('font-size', label.short.length > 3 ? '7' : '9');
        tp2.textContent = label.short;
        txt.appendChild(tp2);
      } else {
        txt.setAttribute('y', cy + 3);
        txt.setAttribute('font-size', label.short.length > 3 ? '7' : '9');
        txt.textContent = label.short;
      }
      g.appendChild(txt);
    }
    svg.appendChild(g);
  }

  // 시도 경계 굵은 선 + 한반도 외곽 — dorling 제외 (원 위치가 force-directed로 이동해 경계 불일치).
  // 격자 모드는 spiral 그린 뒤 위쪽에서 별도 호출.
  if (sizingMode === 'dorling') return;
  drawHexBorders(svg, data, cellAt, colW, rowH, offX, offY, r, '1.8', true);
}

