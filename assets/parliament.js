// 의회 반 도넛 점 차트 — history.html 우측 detail + index status overview 공용.
// parties: [{party, seats, color}] 의석 desc 정렬, total: 총 의석.

function renderParliamentChart(parties, total, width = 320, height = 170) {
  if (!total) return '';
  const cx = width / 2;
  const cy = height - 14;
  const rings = total > 280 ? 7 : total > 180 ? 6 : total > 100 ? 5 : 4;
  const rOuter = Math.min(width / 2 - 8, height - 18);
  const rInner = rOuter * (0.40 + 0.04 * (rings - 4));
  const dr = (rOuter - rInner) / Math.max(1, rings - 1);
  const ringR = Array.from({ length: rings }, (_, i) => rInner + i * dr);
  const seatRadius = dr * 0.46;
  const spacing = 1.15;
  const ringCap = ringR.map(r => Math.floor((Math.PI * r) / (2 * seatRadius * spacing)));
  let cap = ringCap.reduce((a, b) => a + b, 0);
  let adjRadius = seatRadius;
  while (cap < total && adjRadius > 0.5) {
    adjRadius *= 0.97;
    cap = ringR.map(r => Math.floor((Math.PI * r) / (2 * adjRadius * spacing))).reduce((a, b) => a + b, 0);
  }
  const finalCap = ringR.map(r => Math.floor((Math.PI * r) / (2 * adjRadius * spacing)));
  const weight = ringR.map(r => Math.PI * r);
  const totalW = weight.reduce((a, b) => a + b, 0);
  let ringSeats = weight.map(w => Math.floor(total * w / totalW));
  let diff = total - ringSeats.reduce((a, b) => a + b, 0);
  for (let i = rings - 1; diff > 0 && i >= 0; i--) {
    const room = finalCap[i] - ringSeats[i];
    const add = Math.min(diff, room);
    ringSeats[i] += add; diff -= add;
  }
  const allSeats = [];
  for (let i = 0; i < rings; i++) {
    const r = ringR[i];
    const n = ringSeats[i];
    if (!n) continue;
    for (let k = 0; k < n; k++) {
      const t = n > 1 ? k / (n - 1) : 0.5;
      const angle = Math.PI * (1 - t);
      allSeats.push({ x: cx + r * Math.cos(angle), y: cy - r * Math.sin(angle), angle });
    }
  }
  allSeats.sort((a, b) => b.angle - a.angle);
  const seatColors = [];
  for (const p of parties) {
    for (let k = 0; k < p.seats; k++) seatColors.push(p.color);
  }
  let svg = `<svg class="parliament-chart" viewBox="0 0 ${width} ${height}" width="100%" preserveAspectRatio="xMidYMax meet">`;
  for (let i = 0; i < allSeats.length; i++) {
    const s = allSeats[i];
    const c = seatColors[i] || '#bbb';
    svg += `<circle cx="${s.x.toFixed(1)}" cy="${s.y.toFixed(1)}" r="${adjRadius.toFixed(1)}" fill="${c}" stroke="rgba(0,0,0,0.15)" stroke-width="0.4"/>`;
  }
  svg += '</svg>';
  return svg;
}
