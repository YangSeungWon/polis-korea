// 의회 반 도넛(채운 호) 차트 — history.html 우측 detail + index status overview + 아카이브 총선 hero 공용.
// parties: [{party, seats, color}] 의석 desc 정렬, total: 총 의석.
//   정당별 의석 비례만큼 반원 환형(annulus)을 각도로 분할해 통으로 칠한다(점 대신 — 작은 썸네일서 빈공간↓).
//   정확한 의석수는 범례가 표기. 호버 title에 정당·의석.

// 환형 섹터 폴리곤 — 각도 aL→aR(라디안, aL>aR) 사이를 바깥/안쪽 반지름으로 샘플링(arc-flag 회피).
function _annulusSector(cx, cy, rIn, rOut, aL, aR) {
  const steps = Math.max(2, Math.round((aL - aR) / 0.08));
  const pts = [];
  for (let i = 0; i <= steps; i++) { const a = aL + (aR - aL) * i / steps; pts.push([cx + rOut * Math.cos(a), cy - rOut * Math.sin(a)]); }
  for (let i = steps; i >= 0; i--) { const a = aL + (aR - aL) * i / steps; pts.push([cx + rIn * Math.cos(a), cy - rIn * Math.sin(a)]); }
  return 'M' + pts.map((p) => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' L') + 'Z';
}

function renderParliamentChart(parties, total, width = 320, height = 170) {
  if (!total) return '';
  const cx = width / 2;
  const cy = height - 14;
  const rOuter = Math.min(width / 2 - 8, height - 18);
  const rInner = rOuter * 0.42;   // 도넛 구멍 — 작게(빈공간 최소) 두되 반원 의회 느낌 유지
  let svg = `<svg class="parliament-chart" viewBox="0 0 ${width} ${height}" width="100%" preserveAspectRatio="xMidYMax meet">`;
  let acc = 0;
  for (const p of parties) {
    if (!p.seats) continue;
    const t0 = acc / total;
    const t1 = (acc + p.seats) / total;
    acc += p.seats;
    // 의석이 왼쪽(각 π)부터 누적 — 점 버전과 동일 배치.
    const aL = Math.PI * (1 - t0);
    const aR = Math.PI * (1 - t1);
    svg += `<path d="${_annulusSector(cx, cy, rInner, rOuter, aL, aR)}" fill="${p.color || '#bbb'}" stroke="var(--bg, #fff)" stroke-width="1" stroke-linejoin="round"><title>${p.party || ''} ${p.seats}석</title></path>`;
  }
  svg += '</svg>';
  return svg;
}
