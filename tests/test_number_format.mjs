// 숫자 표기 문법 — 값 / 무투표 / 자료 없음이 서로 다르게 보이는가.
//
// 흩어진 렌더러가 각자 `(pct || 0).toFixed(1)`을 쓰고 있었다. null이 0.0%가 되면
// '아무도 안 찍었다'는 없는 사실이 만들어진다. 실측:
//   · 1위 후보 득표율이 없는 race 2,668건 → 화면에 0.0%
//   · 무투표 race의 후보 239행(pct=0 저장) → 화면에 0.00%
// 잠재 결함이 아니라 매일 나가던 오표기였다.
//
// 표기는 fmtPct 한곳에 모은다. 문법이 흩어지면 페이지마다 같은 뜻이 다르게 보인다.
//
// 실행: node tests/test_number_format.mjs
import fs from 'fs';

const ROOT = new URL('..', import.meta.url).pathname;
let pass = 0, fail = 0;
const ck = (n, c, d) => { if (c) { pass++; console.log(`  ✓ ${n}`); } else { fail++; console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`); } };

globalThis.window = { matchMedia: () => ({ matches: false }) };
globalThis.document = { documentElement: { getAttribute: () => 'light' }, body: {} };
const { fmtPct, pctValue } = new Function(
  fs.readFileSync(ROOT + 'assets/parties.js', 'utf8') + '\nreturn { fmtPct, pctValue };')();

// ── 세 상태가 구분된다 ──────────────────────────────────────────────────────
ck('값은 값으로', fmtPct(49.37) === '49.4%', fmtPct(49.37));
ck('자릿수 지정', fmtPct(49.37, { digits: 2 }) === '49.37%', fmtPct(49.37, { digits: 2 }));
ck('null은 0%가 아니라 —', fmtPct(null) === '—', fmtPct(null));
ck('undefined도 —', fmtPct(undefined) === '—', fmtPct(undefined));
ck('NaN도 —', fmtPct(NaN) === '—', fmtPct(NaN));
ck('무투표는 사실로', fmtPct(0, { uncontested: true }) === '무투표', fmtPct(0, { uncontested: true }));
ck('무투표 긴 표기', fmtPct(0, { uncontested: true, longFact: true }) === '무투표 당선');
ck('세 상태가 서로 다르다',
  new Set([fmtPct(0), fmtPct(null), fmtPct(0, { uncontested: true })]).size === 3,
  [fmtPct(0), fmtPct(null), fmtPct(0, { uncontested: true })].join(' / '));
ck('진짜 0%는 0.0%로 (결손과 구분)', fmtPct(0) === '0.0%', fmtPct(0));

// 표기와 계산은 분리 — 막대 폭은 0이어도 되지만 글씨는 0%면 안 된다.
ck('pctValue는 계산용이라 0으로 떨어진다', pctValue(null) === 0 && pctValue(12.3) === 12.3);

// ── 렌더러가 옛 패턴으로 돌아가지 않는다 ────────────────────────────────────
const files = [];
(function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = d + '/' + e.name;
    if (e.isDirectory()) walk(p); else if (e.name.endsWith('.js')) files.push(p);
  }
})(ROOT + 'assets');

const offenders = [];
for (const f of files) {
  fs.readFileSync(f, 'utf8').split('\n').forEach((line, i) => {
    const s = line.trim();
    if (s.startsWith('//') || s.startsWith('*')) return;
    for (const m of line.matchAll(/\(\s*[\w.]*\.pct \|\| 0\s*\)\.toFixed/g)) {
      // style= 안이면 계산값(막대 폭) — 거긴 0이 맞다.
      const st = line.lastIndexOf('style="', m.index);
      if (st !== -1 && line.indexOf('"', st + 7) > m.index) continue;
      offenders.push(`${f.slice(ROOT.length)}:${i + 1}`);
    }
  });
}
ck(`글씨로 나가는 (pct || 0) 없음 (${files.length}개 파일)`, !offenders.length,
  offenders.slice(0, 6).join(' '));

// fmtPct가 단위를 붙이므로 뒤에 %가 또 오면 '—%'가 된다.
const dup = [];
for (const f of files) {
  const t = fs.readFileSync(f, 'utf8');
  if (/\$\{fmtPct\([^{}]*\{[^{}]*\}\)\}\s*(%|<span class="u(nit)?">%)/.test(t)) dup.push(f.slice(ROOT.length));
}
ck('fmtPct 뒤에 % 중복 없음', !dup.length, dup.join(' '));

// ── 결손을 무투표로 주장하지 않는다 ─────────────────────────────────────────
const hist = fs.readFileSync(ROOT + 'assets/history/main.js', 'utf8');
ck('득표율 결손을 "무투표"로 쓰지 않는다',
  !/c\.pct != null \? c\.pct\.toFixed\(1\) \+ '%' : '무투표'/.test(hist));

console.log(`\n총 ${pass + fail}건: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
