// 격차 명도 키(mountGapLegend) — 붙는지, 두 번 그려도 하나인지.
//
// 이 뷰들은 사용자가 토글을 누를 때마다 다시 그린다. 범례가 append만 하면 클릭할
// 때마다 한 줄씩 쌓인다 — 화면을 못 보는 상태에서 가장 나기 쉬운 사고라 여기서 잡는다.
//
// 브라우저가 없으므로 필요한 DOM만 흉내낸다(jsdom 미설치). 검증 대상은 삽입 위치와
// 멱등성이지 렌더링이 아니다.
//
// 실행: node tests/test_viz_legend.mjs
import fs from 'fs';

const ROOT = new URL('..', import.meta.url).pathname;
let pass = 0, fail = 0;
const ck = (n, c, d) => { if (c) { pass++; console.log(`  ✓ ${n}`); } else { fail++; console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`); } };

// ── 최소 DOM ────────────────────────────────────────────────────────────────
class El {
  constructor(tag) { this.tag = tag; this.children = []; this.parentNode = null; this._cls = ''; this.innerHTML = ''; }
  get className() { return this._cls; }
  set className(v) { this._cls = v; }
  get nextSibling() {
    if (!this.parentNode) return null;
    const i = this.parentNode.children.indexOf(this);
    return this.parentNode.children[i + 1] || null;
  }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  remove() {
    if (!this.parentNode) return;
    const i = this.parentNode.children.indexOf(this);
    if (i >= 0) this.parentNode.children.splice(i, 1);
    this.parentNode = null;
  }
  insertBefore(c, ref) {
    c.parentNode = this;
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i < 0) this.children.push(c); else this.children.splice(i, 0, c);
    return c;
  }
  // mountGapLegend가 쓰는 건 ':scope > .클래스' 하나뿐이다.
  querySelector(sel) {
    const m = sel.match(/^:scope > \.([\w-]+)$/);
    if (!m) return null;
    return this.children.find((c) => c._cls.split(/\s+/).includes(m[1])) || null;
  }
}

globalThis.window = { matchMedia: () => ({ matches: false }) };
globalThis.document = {
  documentElement: { getAttribute: () => 'light' },
  body: {},
  createElement: (t) => new El(t),
};
const src = fs.readFileSync(ROOT + 'assets/parties.js', 'utf8')
  + '\nreturn { mountGapLegend, removeGapLegend, gapOpacity, GAP_LEGEND_STOPS };';
const { mountGapLegend, removeGapLegend, gapOpacity, GAP_LEGEND_STOPS } = new Function(src)();

// ── 검사 ────────────────────────────────────────────────────────────────────
const parent = new El('div');
const svg = parent.appendChild(new El('svg'));
const after = parent.appendChild(new El('p'));   // 뒤에 다른 형제가 있어도 자리 지키는지

const leg = mountGapLegend(svg);
ck('범례가 만들어진다', !!leg);
ck('host 바로 다음에 들어간다', parent.children[1] === leg,
  parent.children.map((c) => c.tag + '.' + c._cls).join(','));
ck('뒤 형제는 밀려날 뿐 사라지지 않는다', parent.children.includes(after));

const before = parent.children.length;
mountGapLegend(svg);
mountGapLegend(svg);
ck('세 번 그려도 범례는 하나', parent.children.length === before,
  `${before} → ${parent.children.length}`);

ck('명도 단계가 gapOpacity와 일치',
  GAP_LEGEND_STOPS.every((g) => leg.innerHTML.includes(`opacity:${gapOpacity(g).toFixed(2)}`)),
  leg.innerHTML.slice(0, 120));
ck('박빙→압도 방향이 옅음→진함', gapOpacity(0) < gapOpacity(20),
  `${gapOpacity(0)} < ${gapOpacity(20)}`);
ck('기본 설명이 붙는다', /1·2위 격차/.test(leg.innerHTML));

const leg2 = mountGapLegend(svg, { note: '크기 = 투표수 · 색 진하기 = 1·2위 격차' });
ck('note를 덮어쓸 수 있다', /크기 = 투표수/.test(leg2.innerHTML));
ck('note를 바꿔도 여전히 하나', parent.children.length === before);

ck('부모 없는 host는 조용히 무시', mountGapLegend(new El('svg')) === null);
ck('host 없으면 조용히 무시', mountGapLegend(null) === null);

// ── 걷어내기 — 지도가 사라지는 경로에서 키만 남으면 안 된다 ──────────────────
// 실제 사고 경로: 데이터 0건이면 svg.innerHTML=''로 지도만 비우는데, 범례는 svg의
// **형제**라 그대로 남는다. 설명할 대상 없는 키가 화면에 떠 있게 된다.
removeGapLegend(svg);
ck('걷어내면 사라진다', !parent.children.some((c) => c._cls === 'vz-gap-legend'),
  parent.children.map((c) => c.tag + '.' + c._cls).join(','));
ck('걷어내도 지도·형제는 남는다',
  parent.children.includes(svg) && parent.children.includes(after));
removeGapLegend(svg);
ck('두 번 걷어내도 안전', true);
ck('없는 host 걷어내기 안전', (removeGapLegend(null), removeGapLegend(new El('svg')), true));
// 걷어낸 뒤 다시 그릴 수 있어야 한다(모드 왕복).
const again = mountGapLegend(svg);
ck('걷어낸 뒤 다시 붙는다', !!again && parent.children[1] === again);
ck('왕복해도 하나뿐',
  parent.children.filter((c) => c._cls === 'vz-gap-legend').length === 1);

console.log(`\n총 ${pass + fail}건: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
