// 신뢰 상태 렌더러 검증 — docs/trust-states.md의 대표 fixture 8개.
//
// 컴포넌트를 만든 뒤 페이지를 뒤지며 예외를 찾는 대신, 실재하는 상태를 미리 고정해 둔다.
// 2번(잠정+개표율)은 지금 실데이터가 없다(9회 지선은 확정 승격 완료). 그렇다고 테스트를
// 빼면 다음 개표일에 처음 실행되는 코드가 되므로 합성 fixture로 확인한다.
//
// 실행: node tests/test_trust_states.mjs
import fs from 'fs';

const ROOT = new URL('..', import.meta.url).pathname;
globalThis.window = {};
globalThis.document = { getElementById: () => null };
eval(fs.readFileSync(ROOT + 'assets/trust.js', 'utf8'));
const T = window.Trust;

const read = (p) => JSON.parse(fs.readFileSync(ROOT + p, 'utf8'));
let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; console.log(`  ✗ ${name}${detail ? ' — ' + detail : ''}`); }
}

// ── 1. 확정 · NEC OpenAPI (선거 결과) ───────────────────────────────────────
const res = read('data/results/9th-local-2026.json');
const m1 = T.deriveDataset(res._meta);
const h1 = T.renderDataset(m1);
check('1 확정: lifecycle=final', m1.lifecycle === 'final', JSON.stringify(m1));
check('1 확정: 출처 NEC OpenAPI', m1.sourceLabel === 'NEC OpenAPI', m1.sourceLabel);
check('1 확정: 확정본에 개표율 없음', m1.progress === null, m1.progress);
check('1 확정: 렌더 문자열', h1.includes('확정') && h1.includes('NEC OpenAPI'), h1);

// ── 2. 잠정 + 개표율 (합성 — 다음 개표일용 코드 경로) ────────────────────────
const m2 = T.deriveDataset(
  { is_final: false, source: 'nec-live-portal', fetched_at: '2026-06-03T22:40:00+09:00' },
  { countPct: 87.4 });
check('2 잠정: lifecycle=provisional', m2.lifecycle === 'provisional');
check('2 잠정: 개표 87.4%', m2.progress === '개표 87.4%', m2.progress);
check('2 잠정: 출처 NEC 실시간', m2.sourceLabel === 'NEC 실시간', m2.sourceLabel);
check('2 잠정: 갱신 시각 노출', !!m2.publishedAt, m2.publishedAt);
// 확정본에는 개표율을 붙이지 않는다 — 무투표 race의 100뿐이라 없는 정보가 생긴다.
check('2 잠정: 확정이면 개표율 무시',
  T.deriveDataset({ is_final: true, source: 'nec-openapi' }, { countPct: 87.4 }).progress === null);

// ── 3. 일부 집계 중 (tc9 비례 votes_pending) ────────────────────────────────
const pending = res.races.filter((r) => r.sg_typecode === '9'
  && r.scope === 'proportional_sigungu' && r.votes_pending).length;
const m3 = T.deriveDataset(res._meta, { pendingCount: pending });
check('3 일부 집계 중: 실데이터 58곳', pending === 58, String(pending));
check('3 일부 집계 중: 문구', /58곳 일부 집계 중/.test(T.renderDataset(m3)), T.renderDataset(m3));

// ── 4. 무투표 — 신뢰가 아니라 도메인 사실 ───────────────────────────────────
const unc = res.races.filter((r) => r.is_uncontested
  && ['sigungu', 'district'].includes(r.scope)).length;
const f4 = T.domainFact('uncontested');
check('4 무투표: 실데이터 254건', unc === 254, String(unc));
check('4 무투표: 사실 표기 클래스', f4.includes('tr-fact') && f4.includes('무투표'), f4);
check('4 무투표: 신뢰 칩 아님', !f4.includes('tr-chip'), f4);

// ── 5. polis 추정 (공약 분야 realm_auto) ────────────────────────────────────
const pl = read('data/pledges/9th-local-2026.json');
const est = pl.people.reduce((s, p) => s + p.pledges.filter((x) => x.realm_auto && !x.realm).length, 0);
const c5 = T.fieldChip('estimated');
check('5 추정: 실데이터 2,900건 이상', est >= 2900, String(est));
check('5 추정: 값 단위 칩', c5.includes('tr-chip') && c5.includes('polis 추정'), c5);

// ── 6. polis 계산 ───────────────────────────────────────────────────────────
check('6 계산: 칩', T.fieldChip('calculated').includes('polis 계산'));

// ── 7. 출구조사 — 확정/잠정이 나오면 안 된다 ────────────────────────────────
const ex = read('data/exit_polls/9th-local-2026.json');
const m7 = T.deriveDataset(ex._meta, { sourceLabel: ex._meta.sources[0].name });
const h7 = T.renderDataset(m7);
check('7 출구조사: lifecycle 없음', m7.lifecycle === null, String(m7.lifecycle));
check('7 출구조사: 확정/잠정 문구 없음', !/확정|잠정/.test(h7), h7);
check('7 출구조사: 출처+발표시각', h7.includes('공동 출구조사') && h7.includes('발표'), h7);
// is_final을 억지로 넣어도 data_type이 exit_poll이면 무시해야 한다.
const m7b = T.deriveDataset({ ...ex._meta, is_final: true });
check('7 출구조사: is_final 있어도 무시', m7b.lifecycle === null, String(m7b.lifecycle));

// ── 8. 여론조사 / 공약 — 모집단 표시, 확정 없음 ─────────────────────────────
const m8 = T.deriveDataset(pl._meta, { dataType: 'pledges' });
check('8 공약: lifecycle 없음', m8.lifecycle === null, String(m8.lifecycle));
check('8 공약: 모집단 등록 후보 전체', m8.scopeLabel === '등록 후보 전체', m8.scopeLabel);
const agg = read('data/polls/aggregated.json');
check('8 여론조사: NESDC 출처', T.deriveDataset(agg._meta, { dataType: 'polls' }).sourceLabel
  === 'NESDC 등록 조사');

// ── 방어: 내부 식별자가 화면에 새지 않는다 ──────────────────────────────────
check('방어: 알 수 없는 긴 source는 버린다',
  T.deriveDataset({ source: 'some-very-long-internal-pipeline-identifier-v3' }).sourceLabel === null);
check('방어: 빈 meta는 빈 문자열', T.renderDataset(T.deriveDataset({})) === '');

console.log(`\n총 ${pass + fail}건: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
