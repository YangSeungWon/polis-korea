// history.js 시군구 hex — 대선·지선 기초단체장 시군구별 결과.

// === 시군구 hex ===

function renderSigunguHex() {
  const svg = $('#hex2');
  svg.innerHTML = '';
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  // 대선만 일반구별 개표 단위 (legacy sigungu hex). 지선은 통합 시장이라 base hex.
  // 총선은 지역구(district_hex_*.json) — renderDistrictHex가 별도 처리.
  const useLegacy = state.hexLegacy && state.type === 'presidential';
  let data = useLegacy ? state.hexLegacy : state.hexData;
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
    if (!resultForSigungu(eff.sido, eff.name)) return [];
    return [{ ...d, sido: eff.sido, name: eff.name }];
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
  svg.setAttribute('viewBox', `0 0 ${Math.ceil(w)} ${Math.ceil(h)}`);
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
    if (result?.voted) maxVoted = Math.max(maxVoted, result.voted);
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
    // 시도 라벨 백그라운드 — cells보다 먼저 그려 spiral 색이 위에 덮이도록.
    // cluster centroid 큰 글씨, spiral 사이/외곽에서 살짝 비침.
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

    let selectedG = null;
    for (const d of data) {
      const result = resultForSigungu(d.sido, d.name);
      if (!result?.voted) continue;
      const N = Math.max(1, Math.ceil(result.voted / unit));
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
      tt.textContent = top
        ? `${d.sido} ${d.name} · ${candLabel(top)} (${top.party}) ${top.pct?.toFixed(1)}% · ${N}석/표`
        : `${d.sido} ${d.name}`;
      g.appendChild(tt);
      // 시군구 boundary outline — 작은 hex cluster 둘러쌈 (시각 통합, 인접 격자 겹침 방지)
      const sigOutline = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      sigOutline.setAttribute('points', hexPoints(cx0, cy0, 22));
      sigOutline.setAttribute('class', 'sig-outline' + (isSelected ? ' is-selected' : ''));
      sigOutline.setAttribute('stroke-width', isSelected ? '3.5' : '1.0');
      g.appendChild(sigOutline);
      // 후보별 hex 배정 (스파이럴 순서대로 1위→2위→... 채움)
      const spiral = hexSpiral(N);
      const fills = [];
      for (let i = 0; i < cands.length; i++) {
        for (let k = 0; k < alloc[i]; k++) fills.push(partyColor(cands[i].party));
      }
      while (fills.length < N) fills.push('#e6e9ef');  // 안전 fallback
      for (let i = 0; i < spiral.length; i++) {
        const [q, ar] = spiral[i];
        const dx = smallR * Math.sqrt(3) * (q + ar / 2);
        const dy = smallR * 1.5 * ar;
        const sx = cx0 + dx, sy = cy0 + dy;
        const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        poly.setAttribute('points', hexPoints(sx, sy, smallR - 0.4));
        poly.setAttribute('fill', fills[i] || '#e6e9ef');
        // 작은 hex는 stroke 없음 — selected는 큰 outline에서만 강조.
        g.appendChild(poly);
      }
      // 시군구 라벨 — short(시군구 약칭)만 cell 상단에 작게. 시도 prefix는 cluster centroid에 별도(아래).
      const label = shortSigunguLabel(d.name, d.sido);
      if (label.short) {
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
    // 시도 경계 굵은 선 — 격자 모드도 cell 위치가 동일 모드와 같으므로 적용 가능.
    drawHexBorders(svg, data, cellAt, colW, rowH, offX, offY, r, '1.8', true);
    // 선택 cell을 마지막에 다시 append → SVG z-order 최상위 (인접 cell·경계선이
    // selected outline 가리지 않게).
    if (selectedG) svg.appendChild(selectedG);
    return;
  }

  // Dorling cartogram: 원, force-directed packing
  if (sizingMode === 'dorling' && maxVoted > 0) {
    const nodes = data.map((d) => {
      const result = resultForSigungu(d.sido, d.name);
      const v = result?.voted || 0;
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
    // 시도 라벨 백그라운드 — 권역 테두리 안 centroid에 큰 글씨
    for (const [sido, list] of sidoGroups) {
      const cx = list.reduce((s, n) => s + n.cx, 0) / list.length;
      const cy = list.reduce((s, n) => s + n.cy, 0) / list.length;
      const lbl = SIDO_LABEL_SHORT[sido] || sido;
      const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t.setAttribute('x', cx);
      t.setAttribute('y', cy);
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
        ? `${n.d.sido} ${n.d.name} · ${candLabel(n.top)} (${n.top.party}) ${n.top.pct?.toFixed(1)}%`
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
      ? `${d.sido} ${d.name} · ${candLabel(top)} (${top.party}) ${top.pct?.toFixed(1)}%`
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

