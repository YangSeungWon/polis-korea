// 거르기(Filter, 동적 질의) — 손잡이를 움직이는 동안 화면이 바로 따라오는가.
//
// 막는 사고:
//   · 조건 밖 칸을 지운다(Overview를 잃는다) / 격자의 표 비례 네모를 테두리로 덮는다.
//   · 모르는 값(무투표)을 조건에 맞거나 안 맞는다고 판정한다.
//   · 지도 방식을 바꾸면 조건이 풀린다. 조건이 URL에 안 남는다 / 링크로 안 돌아온다.
//   · 대선 지도에 '접전' 필터가 붙는다(시군구 승부가 아니다 — 승자독식 틀).
//   · 연표 범위를 좁혔는데 빈 시대 머리가 줄줄이 남는다.
//
// 실행: node tests/ui/test_filter.mjs
import { chromium } from 'playwright';
import { serve } from './server.mjs';

let pass = 0; const fails = [];
const ck = (n, c, d) => {
  if (c) { pass++; console.log(`  ✓ ${n}`); }
  else { fails.push(n); console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`); }
};
const ROOT = new URL('../..', import.meta.url).pathname;
const srv = await serve(ROOT, 8296);
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
const errs = [];
page.on('pageerror', (e) => errs.push(String(e)));
const setRange = (sel, v) => page.$eval(sel, (el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }, v);

// ── 1. archive 지도: 접전 ───────────────────────────────────────────
console.log('\n[archive 지도 필터 — 지선 기초단체장]');
await page.goto(srv.url + '/archive/8th-local-2022/');
await page.waitForSelector('#ar-sgg-result .map-filter', { timeout: 30000 });
const area = '#ar-sgg-result .sgg-map-area';
const before = await page.$$eval(`${area} [data-region]`, (els) => els.length);
const t0 = Date.now();
await setRange('#ar-sgg-result .mf-margin input', 5);
const dt = Date.now() - t0;
await page.waitForTimeout(200);   // 흐림 전환(.1s) 뒤에 잰다
const st = await page.evaluate((area) => {
  const els = [...document.querySelectorAll(`${area} [data-region]`)];
  const hit = els.filter((e) => e.classList.contains('mf-hit'));
  const out = els.filter((e) => e.classList.contains('mf-out'));
  return { n: els.length, hit: hit.length, out: out.length, op: out[0] ? +getComputedStyle(out[0]).opacity : null,
    cnt: document.querySelector('#ar-sgg-result .mf-count').textContent };
}, area);
ck('격차 ≤5%p → 일부만 맞는다', st.hit > 0 && st.out > 0, JSON.stringify(st));
ck('조건 밖 칸을 지우지 않는다(칸 수 그대로)', st.n === before, `${before} → ${st.n}`);
ck('조건 밖은 흐리게', st.op !== null && st.op < 0.5 && st.op > 0, String(st.op));
ck(`즉시 반영 (${dt}ms < 100ms)`, dt < 100);
// 판정이 원자료와 맞는가 — 맞는 칸의 격차는 전부 ≤5, 무투표는 hit이 아니다.
const truth = await page.evaluate(async (area) => {
  const res = await (await fetch('/data/results/8th-local-2022.sigungu.json').catch(() => null))?.json?.().catch(() => null)
    || await (await fetch('/data/results/8th-local-2022.json')).json();
  const races = (res.races || []).filter((r) => r.scope === 'sigungu' && r.sg_typecode === '4');
  const m = new Map();
  for (const r of races) {
    const cs = (r.candidates || []).slice().sort((a, b) => (b.votes || 0) - (a.votes || 0));
    m.set(`${r.sido}|${r.sigungu}`, (r.is_uncontested || cs.length < 2) ? null : cs[0].pct - cs[1].pct);
  }
  const bad = [];
  for (const el of document.querySelectorAll(`${area} [data-region].mf-hit`)) {
    const k = el.dataset.region;
    if (m.has(k) && (m.get(k) == null || m.get(k) > 5.0001)) bad.push(k + ':' + m.get(k));
  }
  const unc = [...m.entries()].filter(([, v]) => v == null).map(([k]) => k);
  const uncHit = unc.filter((k) => document.querySelector(`${area} [data-region="${k}"].mf-hit`));
  return { bad, unc: unc.length, uncHit };
}, area);
ck('맞다고 칠한 칸의 실제 격차가 전부 ≤5%p', truth.bad.length === 0, truth.bad.slice(0, 3).join(' '));
ck(`무투표(${truth.unc}곳)는 접전으로 치지 않는다`, truth.uncHit.length === 0, truth.uncHit.join(' '));
ck('자료 없음·무투표를 따로 센다', truth.unc === 0 || /자료 없음·무투표/.test(st.cnt), st.cnt);

await page.waitForTimeout(400);
ck('조건이 URL에 (?margin=5)', new URL(page.url()).searchParams.get('margin') === '5', page.url());
// 방식을 바꿔도 조건이 남는다
const hitsHex = await page.$$eval(`${area} .mf-hit`, (e) => e.length);
const modeBtn = await page.$('#ar-sgg-result .sgg-mode-toggle [data-enc="격자"]');
ck('격자 방식 버튼이 있다', !!modeBtn);
if (modeBtn) {
  await modeBtn.evaluate((b) => b.click());
  await page.waitForTimeout(800);
  const hitsGrid = await page.evaluate((area) => new Set([...document.querySelectorAll(`${area} .mf-hit`)].map((e) => e.dataset.region)).size, area);
  ck('방식을 바꿔도 조건이 남는다', hitsGrid > 0, `${hitsHex} → ${hitsGrid}`);
}
// 링크로 돌아온다
await page.goto(srv.url + '/archive/8th-local-2022/?margin=5');
await page.waitForSelector('#ar-sgg-result .map-filter', { timeout: 30000 });
await page.waitForTimeout(500);
const rs = await page.evaluate(() => ({
  m: document.querySelector('#ar-sgg-result .mf-margin input').value,
  on: document.querySelector('#ar-sgg-result .sgg-map-area').classList.contains('mf-on'),
}));
ck('링크(?margin=)를 열면 조건이 걸린 채', rs.m === '5' && rs.on, JSON.stringify(rs));
ck('투표율 손잡이는 없다(아래 투표율 지도와 겹친다)', !(await page.$('#ar-sgg-result .map-filter .rf')));
await page.click('#ar-sgg-result .mf-reset');
await page.waitForTimeout(400);
ck('조건 지우기 → 원래대로 + URL에서 빠진다',
  !(await page.$('#ar-sgg-result .sgg-map-area.mf-on')) && !new URL(page.url()).searchParams.get('margin'));

await page.goto(srv.url + '/archive/8th-local-2022/?margin=5&v=sgg-grid');
await page.waitForSelector('#ar-sgg-result .mf-hit', { timeout: 30000 });
const gi = await page.evaluate(() => {
  const h = document.querySelector('#ar-sgg-result .mf-hit');
  const ps = h.querySelectorAll(':scope > polygon');
  return { outline: getComputedStyle(ps[0]).strokeWidth, inner: ps[1] ? getComputedStyle(ps[1]).stroke : 'none' };
});
ck('격자: 칸 외곽에만 테두리, 표 비례 네모는 그대로', parseFloat(gi.outline) >= 1 && gi.inner === 'none', JSON.stringify(gi));

console.log('\n[archive 지도 필터 — 대선에는 없다]');
await page.goto(srv.url + '/archive/21st-pres-2025/?margin=3');
await page.waitForSelector('#ar-sgg-result .sgg-map-area [data-region]', { timeout: 30000 });
await page.waitForTimeout(500);
ck('대선 시군구 지도에 접전 필터가 없다', await page.evaluate(() =>
  !document.querySelector('.map-filter') && !document.querySelector('.mf-on, .mf-out')));

// ── 2. 연표 연도 범위 ─────────────────────────────────────────────────────
console.log('\n[연표]');
await page.goto(srv.url + '/chronology.html');
await page.waitForSelector('#chrono-range .rf-lo', { timeout: 20000 });
await page.waitForSelector('.chr-row');
const all = await page.$$eval('.chr-row:not(.is-hidden)', (e) => e.length);
await setRange('#chrono-range .rf-lo', 1987);
await setRange('#chrono-range .rf-hi', 1997);
const ch = await page.evaluate(() => {
  const vis = [...document.querySelectorAll('.chr-row:not(.is-hidden)')].map((r) => +r.dataset.year);
  const heads = [...document.querySelectorAll('.chr-era:not(.is-hidden), .chr-gov:not(.is-hidden)')].map((h) => h.textContent.slice(0, 12));
  return { vis, heads, cnt: document.getElementById('chrono-count').textContent };
});
ck('1987~1997 밖 행이 숨는다', ch.vis.length > 0 && ch.vis.length < all && ch.vis.every((y) => y >= 1987 && y <= 1997), `${all} → ${ch.vis.length}`);
ck('빈 시대 머리는 남지 않는다', ch.heads.length > 0 && ch.heads.length <= 5, ch.heads.join(' | '));
ck('건수 표시', ch.cnt === `${ch.vis.length}건`, ch.cnt);
await page.click('[data-filter="election"]');
await page.waitForTimeout(400);
const u = new URL(page.url());
ck('종류·범위가 URL에 (?f=&from=&to=)', u.searchParams.get('f') === 'election' && u.searchParams.get('from') === '1987' && u.searchParams.get('to') === '1997', u.search);
await page.goto(srv.url + '/chronology.html?f=election&from=1987&to=1997');
await page.waitForSelector('.chr-row', { state: 'attached', timeout: 20000 });
await page.waitForTimeout(300);
const back = await page.evaluate(() => ({
  types: [...new Set([...document.querySelectorAll('.chr-row:not(.is-hidden)')].map((r) => r.dataset.type))],
  ys: [...document.querySelectorAll('.chr-row:not(.is-hidden)')].map((r) => +r.dataset.year),
  act: document.querySelector('[data-filter].is-active')?.dataset.filter,
}));
ck('링크로 열면 같은 연표', back.act === 'election' && back.types.join() === 'election' && back.ys.every((y) => y >= 1987 && y <= 1997), JSON.stringify(back).slice(0, 120));

// ── 3. 휴대폰 폭 ──────────────────────────────────────────────────────────
console.log('\n[390px]');
await page.setViewportSize({ width: 390, height: 844 });
for (const path of ['/archive/8th-local-2022/', '/chronology.html']) {
  await page.goto(srv.url + path);
  await page.waitForTimeout(2500);
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ck(`가로 스크롤 없음 ${path}`, over <= 1, String(over));
}
ck('페이지 오류 없음', errs.length === 0, errs.slice(0, 3).join(' | '));
await browser.close();
srv.close();
console.log(`\n${pass} 통과 · ${fails.length} 실패`);
process.exit(fails.length ? 1 : 0);
