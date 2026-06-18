// 의회 반원 차트 — history detail · index status · 역대판세 상세 · 아카이브 총선 hero 공용.
// parties: [{party, seats, color}] 의석 desc 정렬, total: 총 의석.
//   mode 'dots'(기본) = 동그라미 하나=의석 하나(크게 볼 때 정보량↑).
//   mode 'donut'      = 정당별 채운 호(작은 썸네일/공유 카드 — 점이 안 보일 때 빈공간↓).

// 환형 섹터 폴리곤 — 각도 aL→aR(라디안, aL>aR) 사이를 바깥/안쪽 반지름으로 샘플링(arc-flag 회피).
function _annulusSector(cx, cy, rIn, rOut, aL, aR) {
  const steps = Math.max(2, Math.round((aL - aR) / 0.08));
  const pts = [];
  for (let i = 0; i <= steps; i++) { const a = aL + (aR - aL) * i / steps; pts.push([cx + rOut * Math.cos(a), cy - rOut * Math.sin(a)]); }
  for (let i = steps; i >= 0; i--) { const a = aL + (aR - aL) * i / steps; pts.push([cx + rIn * Math.cos(a), cy - rIn * Math.sin(a)]); }
  return 'M' + pts.map((p) => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' L') + 'Z';
}

function _parliamentDonut(parties, total, width, height) {
  const cx = width / 2, cy = height - 14;
  const rOuter = Math.min(width / 2 - 8, height - 18);
  const rInner = rOuter * 0.42;
  let svg = `<svg class="parliament-chart" viewBox="0 0 ${width} ${height}" width="100%" preserveAspectRatio="xMidYMax meet">`;
  let acc = 0;
  for (const p of parties) {
    if (!p.seats) continue;
    const aL = Math.PI * (1 - acc / total);
    acc += p.seats;
    const aR = Math.PI * (1 - acc / total);
    svg += `<path d="${_annulusSector(cx, cy, rInner, rOuter, aL, aR)}" fill="${p.color || '#bbb'}" stroke="var(--bg, #fff)" stroke-width="1" stroke-linejoin="round"><title>${p.party || ''} ${p.seats}석</title></path>`;
  }
  return svg + '</svg>';
}

function _parliamentDots(parties, total, width, height) {
  const cx = width / 2, cy = height - 14;
  const rings = total > 280 ? 7 : total > 180 ? 6 : total > 100 ? 5 : 4;
  const rOuter = Math.min(width / 2 - 8, height - 18);
  const rInner = rOuter * (0.40 + 0.04 * (rings - 4));
  const dr = (rOuter - rInner) / Math.max(1, rings - 1);
  const ringR = Array.from({ length: rings }, (_, i) => rInner + i * dr);
  const seatRadius = dr * 0.46;
  const spacing = 1.15;
  let cap = ringR.map(r => Math.floor((Math.PI * r) / (2 * seatRadius * spacing))).reduce((a, b) => a + b, 0);
  let adjRadius = seatRadius;
  while (cap < total && adjRadius > 0.5) {
    adjRadius *= 0.97;
    cap = ringR.map(r => Math.floor((Math.PI * r) / (2 * adjRadius * spacing))).reduce((a, b) => a + b, 0);
  }
  const finalCap = ringR.map(r => Math.floor((Math.PI * r) / (2 * adjRadius * spacing)));
  const weight = ringR.map(r => Math.PI * r);
  const totalW = weight.reduce((a, b) => a + b, 0);
  const ringSeats = weight.map(w => Math.floor(total * w / totalW));
  let diff = total - ringSeats.reduce((a, b) => a + b, 0);
  for (let i = rings - 1; diff > 0 && i >= 0; i--) {
    const room = finalCap[i] - ringSeats[i];
    const add = Math.min(diff, room);
    ringSeats[i] += add; diff -= add;
  }
  const allSeats = [];
  for (let i = 0; i < rings; i++) {
    const r = ringR[i], n = ringSeats[i];
    if (!n) continue;
    for (let k = 0; k < n; k++) {
      const t = n > 1 ? k / (n - 1) : 0.5;
      const angle = Math.PI * (1 - t);
      allSeats.push({ x: cx + r * Math.cos(angle), y: cy - r * Math.sin(angle), angle });
    }
  }
  allSeats.sort((a, b) => b.angle - a.angle);
  const seatColors = [];
  for (const p of parties) { for (let k = 0; k < p.seats; k++) seatColors.push(p.color); }
  let svg = `<svg class="parliament-chart" viewBox="0 0 ${width} ${height}" width="100%" preserveAspectRatio="xMidYMax meet">`;
  for (let i = 0; i < allSeats.length; i++) {
    const s = allSeats[i], c = seatColors[i] || '#bbb';
    svg += `<circle cx="${s.x.toFixed(1)}" cy="${s.y.toFixed(1)}" r="${adjRadius.toFixed(1)}" fill="${c}" stroke="rgba(0,0,0,0.15)" stroke-width="0.4"/>`;
  }
  return svg + '</svg>';
}

function renderParliamentChart(parties, total, width = 320, height = 170, opts) {
  if (!total) return '';
  return ((opts && opts.mode) === 'donut')
    ? _parliamentDonut(parties, total, width, height)
    : _parliamentDots(parties, total, width, height);
}
