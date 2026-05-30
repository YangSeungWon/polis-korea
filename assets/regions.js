// 5권역 색 시스템 — korea-via-data와 동기.
// 17개 시도를 5권역으로 묶고, 위계(t1/t2/t3) 밝기 offset + 동일 권역+tier 안 hue shift 적용.
// 출처: korea-via-data/assets/explore.js (2026-05-22 복사)

const SIDO_COLORS = {
  '서울특별시':'#c8553d','부산광역시':'#5a6e9c','대구광역시':'#b85c38','인천광역시':'#2e7d6f',
  '광주광역시':'#6d4c7d','대전광역시':'#8a5a8a','울산광역시':'#d4651f','세종특별자치시':'#8c6a3e',
  '경기도':'#2e5e7e','강원특별자치도':'#4a7c59','강원도':'#4a7c59','충청북도':'#c97064','충청남도':'#b07e3d',
  '전북특별자치도':'#7b8c3f','전라북도':'#7b8c3f','전라남도':'#5d8a6e',
  '경상북도':'#a3623f','경상남도':'#677eaa','제주특별자치도':'#2e8a78',
  '전남광주특별시':'#5d8a6e',  // 2026 지선 통합 (전남 톤 — 청록)
};

const REGION_OF = {
  '서울특별시':'수도권','인천광역시':'수도권','경기도':'수도권',
  '대전광역시':'충청권','세종특별자치시':'충청권','충청북도':'충청권','충청남도':'충청권',
  '광주광역시':'호남권','전북특별자치도':'호남권','전라북도':'호남권','전라남도':'호남권',
  '전남광주특별시':'호남권',  // 2026 통합
  '부산광역시':'영남권','대구광역시':'영남권','울산광역시':'영남권','경상북도':'영남권','경상남도':'영남권',
  '강원특별자치도':'강원·제주','강원도':'강원·제주','제주특별자치도':'강원·제주',
};

const REGION_COLORS = {
  '수도권':'#c8553d',     // 주홍
  '충청권':'#b07e3d',     // 황토
  '호남권':'#2e7d6f',     // 청록
  '영남권':'#5a6e9c',     // 청람
  '강원·제주':'#6d4c7d',  // 자
};

const REGION_ORDER = ['수도권','충청권','호남권','영남권','강원·제주'];

const SIDO_TIER = {
  '서울특별시':'t1',
  '부산광역시':'t2','대구광역시':'t2','인천광역시':'t2','광주광역시':'t2',
  '대전광역시':'t2','울산광역시':'t2','세종특별자치시':'t2',
  '경기도':'t3','강원특별자치도':'t3','강원도':'t3','충청북도':'t3','충청남도':'t3',
  '전북특별자치도':'t3','전라북도':'t3','전라남도':'t3',
  '경상북도':'t3','경상남도':'t3','제주특별자치도':'t3',
  '전남광주특별시':'t1',  // 2026 통합 — 특별시급
};

const TIER_LABEL = { 't1':'특별시', 't2':'광역시·세종', 't3':'도' };
const TIER_OFFSET = { 't1': -0.38, 't2': 0, 't3': 0.36 };

function adjustColor(hex, pct) {
  const r = parseInt(hex.slice(1,3),16),
        g = parseInt(hex.slice(3,5),16),
        b = parseInt(hex.slice(5,7),16);
  const adj = c => pct>=0 ? Math.round(c + (255-c)*pct) : Math.round(c*(1+pct));
  const toHex = c => c.toString(16).padStart(2,'0');
  return '#' + toHex(adj(r)) + toHex(adj(g)) + toHex(adj(b));
}

const SIDO_HUE_SHIFT = (function() {
  const groups = {};
  for (const s of Object.keys(REGION_OF)) {
    const key = REGION_OF[s] + '|' + (SIDO_TIER[s]||'t3');
    if (!groups[key]) groups[key] = [];
    groups[key].push(s);
  }
  const out = {};
  for (const arr of Object.values(groups)) {
    arr.sort((a,b)=>a.localeCompare(b,'ko'));
    if (arr.length === 1) { out[arr[0]] = 0; continue; }
    arr.forEach((s,i) => {
      const t = i / (arr.length-1);
      out[s] = (t - 0.5) * 36;
    });
  }
  return out;
})();

function hexToHsl(hex) {
  const r = parseInt(hex.slice(1,3),16)/255;
  const g = parseInt(hex.slice(3,5),16)/255;
  const b = parseInt(hex.slice(5,7),16)/255;
  const max = Math.max(r,g,b), min = Math.min(r,g,b);
  const l = (max+min)/2;
  let h, s;
  if (max===min) { h=0; s=0; }
  else {
    const d = max-min;
    s = l>0.5 ? d/(2-max-min) : d/(max+min);
    if (max===r) h = ((g-b)/d + (g<b?6:0));
    else if (max===g) h = (b-r)/d + 2;
    else h = (r-g)/d + 4;
    h *= 60;
  }
  return [h, s*100, l*100];
}

function hslToHex(h, s, l) {
  s/=100; l/=100;
  const k = n => (n + h/30) % 12;
  const a = s * Math.min(l, 1-l);
  const f = n => l - a * Math.max(-1, Math.min(k(n)-3, Math.min(9-k(n), 1)));
  const toHex = c => Math.round(c*255).toString(16).padStart(2,'0');
  return '#' + toHex(f(0)) + toHex(f(8)) + toHex(f(4));
}

function getSidoColor(sido) {
  const base = REGION_COLORS[REGION_OF[sido]] || '#888';
  const tierShifted = adjustColor(base, TIER_OFFSET[SIDO_TIER[sido]] ?? 0);
  const hueShift = SIDO_HUE_SHIFT[sido] || 0;
  if (hueShift === 0) return tierShifted;
  const [h, s, l] = hexToHsl(tierShifted);
  return hslToHex((h + hueShift + 360) % 360, s, l);
}
