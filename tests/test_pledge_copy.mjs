// 공약 분야 분포 카피 — 분모를 사용자가 오해하지 않는 형태인지.
//
// 사고 형태: '공약 10건 · 미분류 1건 제외'라고 쓰면 사용자는 10건을 분모로 잡고
// '왜 2건이 22.2%지?' 하게 된다. 실제 분모는 9건이다. 사용자가 알고 싶은 건
// 처리 로직(제외했다)이 아니라 차트 합계가 왜 9인가다.
//
// 문구는 자꾸 파이프라인 용어로 돌아가므로(원본이 비어 있어·자동 추정한 값) 고정한다.
//
// 실행: node tests/test_pledge_copy.mjs
import fs from 'fs';

const ROOT = new URL('..', import.meta.url).pathname;
const RAW = fs.readFileSync(ROOT + 'assets/archive/render-pledge-realms.js', 'utf8');
// 주석에는 '왜 이렇게 안 쓰는지'를 적어 두므로 금지어가 그대로 등장한다.
// 검사 대상은 화면에 나가는 코드다 — 주석을 걷고 본다.
const SRC = RAW.split('\n').map((l) => l.replace(/^\s*\/\/.*$/, '')).join('\n');
const SUMMARY = JSON.parse(fs.readFileSync(ROOT + 'data/pledges/realm-summary.json', 'utf8'));
let pass = 0, fail = 0;
const ck = (n, c, d) => { if (c) { pass++; console.log(`  ✓ ${n}`); } else { fail++; console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`); } };

// ── 1. 데이터 불변식: 차트 합계 = 공약 − 미분류 ─────────────────────────────
const bad = [];
for (const [eid, d] of Object.entries(SUMMARY)) {
  const total = (d.realms || []).reduce((s, r) => s + r.n, 0);
  if (total !== (d.n_pledges || 0) - (d.n_unclassified || 0)) bad.push(eid);
}
ck(`차트 합계 = 공약 − 미분류 (${Object.keys(SUMMARY).length}회차)`, !bad.length, bad.slice(0, 3).join(','));

// ── 2. 분모를 밝힌다 ────────────────────────────────────────────────────────
ck('미분류가 있으면 "N건 중 M건 분류"로 분모를 밝힌다', /건 중 .*건 분류/.test(SRC));
ck('"제외"로 처리 로직을 설명하지 않는다', !/건 제외/.test(SRC), '제외 문구 잔존');
ck('분류된 건수를 강조(<b>)', /<b>\$\{num\(total\)\}건 분류<\/b>/.test(SRC));

// ── 3. 출처·가공 문구는 신뢰 칩에 맡기고 반복하지 않는다 ────────────────────
ck('신뢰 칩(fieldChip)을 쓴다', /fieldChip\('autoClassified'\)/.test(SRC));
ck('칩이 없어도 문장은 성립한다(폴백)', /\? window\.Trust\.fieldChip[\s\S]{0,40}: ''/.test(SRC));
ck('파이프라인 말투가 없다 ("원본이 비어 있어")', !/원본이 비어 있어/.test(SRC));
ck('"추정" 반복이 없다', (SRC.match(/추정/g) || []).length === 0, String((SRC.match(/추정/g) || []).length));
ck('오분류 가능성은 한 번 밝힌다', (SRC.match(/오분류/g) || []).length === 1);
ck('대표 분야 1개 기준을 밝힌다', /대표 분야 1개/.test(SRC));

// ── 4. 모집단을 밝힌다 — 당선인만인지 등록 후보 전체인지에 따라 분포가 달라진다 ──
ck('모집단(당선인/등록 후보)을 note에 쓴다', /roster_scope === 'all_candidates'/.test(SRC));

// ── 5. archive 그룹 제목 ────────────────────────────────────────────────────
const pages = fs.readdirSync(ROOT + 'archive').filter((d) => fs.existsSync(`${ROOT}archive/${d}/index.html`));
const withPledge = pages.filter((d) => fs.readFileSync(`${ROOT}archive/${d}/index.html`, 'utf8')
  .includes('ar-pledge-realm-section'));
const stale = withPledge.filter((d) => fs.readFileSync(`${ROOT}archive/${d}/index.html`, 'utf8')
  .includes('무엇을 약속했나'));
ck(`공약 그룹이 있는 회차 ${withPledge.length}개에 옛 제목 없음`, !stale.length, stale.slice(0, 3).join(','));

console.log(`\n총 ${pass + fail}건: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
