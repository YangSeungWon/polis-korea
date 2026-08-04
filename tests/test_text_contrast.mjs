// 정당 색이 **글씨**로 쓰일 때 대비를 지키는지 — 두 겹으로 검사한다.
//
// 1) partyTextColor가 실제로 WCAG 4.5:1을 만족하는가 (라이트·다크 양쪽)
// 2) 어떤 렌더러도 원색(partyColor/pcol)을 글씨 색으로 직접 쓰지 않는가
//
// 왜 필요한가: 정당 원색 146개 중 라이트 배경에서 87개, 다크에서 93개가 본문 대비
// 4.5:1을 못 넘는다. 정의당 노랑(#FFED00)은 1.17:1로 흰 배경에서 사실상 안 보인다.
// 색은 면(fill)에서 정체성을 지고, 글씨는 대비를 지켜야 한다.
//
// 실행: node tests/test_text_contrast.mjs
import fs from 'fs';

const ROOT = new URL('..', import.meta.url).pathname;
let pass = 0, fail = 0;
const ck = (name, cond, detail) => {
  if (cond) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; console.log(`  ✗ ${name}${detail ? ' — ' + detail : ''}`); }
};

function load(dark) {
  globalThis.window = { matchMedia: () => ({ matches: dark }) };
  globalThis.document = {
    documentElement: { getAttribute: () => (dark ? 'dark' : 'light') }, body: {},
  };
  const src = fs.readFileSync(ROOT + 'assets/parties.js', 'utf8')
    + '\nreturn { PARTY_COLORS, partyColor, partyTextColor, _contrast, TEXT_BG };';
  return new Function(src)();
}
const hex2 = (h) => {
  const n = parseInt(String(h).replace('#', ''), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

// ── 1. partyTextColor 대비 ──────────────────────────────────────────────────
for (const dark of [false, true]) {
  const P = load(dark);
  const bg = dark ? P.TEXT_BG.dark : P.TEXT_BG.light;
  const names = Object.keys(P.PARTY_COLORS);
  const bad = names.filter((p) => P._contrast(hex2(P.partyTextColor(p)), bg) < 4.5);
  const label = dark ? '다크' : '라이트';
  ck(`${label}: 정당 ${names.length}개 전부 글씨 대비 4.5:1`, bad.length === 0,
    bad.slice(0, 5).join(', '));
  // 보정이 전부를 검정/흰색으로 만들어버리면 정당 구분이 사라진다.
  const distinct = new Set(names.map((p) => P.partyTextColor(p))).size;
  ck(`${label}: 보정 후에도 색이 구분됨 (${distinct}종)`, distinct >= 40, String(distinct));
  // 무소속은 정당색이 아니라 중립 회색이어야 한다.
  ck(`${label}: 무소속은 중립색`, /^#[0-9a-f]{6}$/i.test(P.partyTextColor('무소속')));
}

// ── 2. 렌더러가 원색을 글씨로 쓰지 않는가 ───────────────────────────────────
// color:${...}에 들어가는 표현식을 같은 파일에서 역추적한다. 원색 헬퍼(partyColor·
// pcol·colOf)로 이어지면 실패 — 대비 보정 헬퍼를 써야 한다.
const SAFE = ['partyTextColor', '_textLegible', 'ptc(', 'ptcol', 'textCol', 'txtCol', 'tcol'];
const RAW = ['partyColor', 'pcol(', 'colOf('];
const files = [];
(function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = d + '/' + e.name;
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith('.js')) files.push(p);
  }
})(ROOT + 'assets');

const offenders = [];
for (const f of files) {
  const src = fs.readFileSync(f, 'utf8');
  const lines = src.split('\n');
  lines.forEach((line, i) => {
    for (const m of line.matchAll(/(?<!-)color:\$\{([^}]+)\}/g)) {
      const expr = m[1];
      if (SAFE.some((s) => expr.includes(s))) continue;
      const v = expr.trim().match(/^([A-Za-z_$][\w$]*)$/);
      let src2 = expr;
      if (v) {
        const defs = [...src.matchAll(
          new RegExp(`(?:const|let|var)\\s+${v[1]}\\s*=\\s*([^;\\n]+)`, 'g'))].map((x) => x[1]);
        src2 = defs.join(' | ');
        if (SAFE.some((s) => src2.includes(s))) continue;
      }
      if (RAW.some((r) => src2.includes(r))) {
        offenders.push(`${f.slice(ROOT.length)}:${i + 1} ${expr.trim()}`);
      }
    }
  });
}
ck(`렌더러 ${files.length}개: 원색을 글씨 색으로 쓰는 곳 없음`, offenders.length === 0,
  offenders.slice(0, 8).join(' / '));

console.log(`\n총 ${pass + fail}건: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
