// 화면 상태 ↔ URL — 공유 링크가 같은 화면을 열고, 뒤로가기가 이전 회차로 돌아가는가.
//
// 막는 사고:
//   · 링크를 복사해 보냈는데 받은 사람은 기본 화면을 본다(상태가 URL에 없다).
//   · 토글 한 번마다 뒤로가기 항목이 쌓여 페이지를 못 떠난다(push 남발).
//   · 유형을 바꾸면 setType→setRound가 항목 둘을 만든다(기록을 안 모은다).
//   · 뒤로가기로 회차는 돌아오는데 방식·선택은 안 돌아온다(복원이 일부만).
//
// 규칙(assets/view-state.js): 경로(회차·유형·직위)가 바뀔 때만 push, 나머지는 replace.
//
// 실행: node tests/ui/test_url_state.mjs   (선행: npm run build:map)
import { chromium } from 'playwright';
import { serve } from './server.mjs';

const ROOT = new URL('../..', import.meta.url).pathname;
let pass = 0; const fails = [];
const ck = (n, c, d) => {
  if (c) { pass++; console.log(`  ✓ ${n}`); }
  else { fails.push(n); console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`); }
};

const srv = await serve(ROOT, 8291);
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', (e) => errs.push(String(e)));

const q = () => page.evaluate(() => Object.fromEntries(new URLSearchParams(location.search)));
const path = () => page.evaluate(() => decodeURIComponent(location.pathname));
const histLen = () => page.evaluate(() => history.length);
const settle = () => page.waitForTimeout(400);
const activeEnc = (sel) => page.$eval(`${sel} [data-enc].is-active`, (b) => b.dataset.enc).catch(() => null);

// ── history 탐색기 ───────────────────────────────────────────────
console.log('history 탐색기');
await page.goto(srv.url + '/history/presidential/21/?view=dorling&sel=' + encodeURIComponent('서울특별시'));
await page.waitForSelector('#enc-seg [data-enc].is-active');
await settle();
ck('?view=dorling → 원형 모드로 열린다', (await activeEnc('#enc-seg')) === 'dorling', await activeEnc('#enc-seg'));
const pane = await page.$eval('#detail-pane', (e) => e.textContent);
ck('?sel=서울특별시 → 상세 패널이 서울', /서울/.test(pane));
ck('복원이 URL을 지우지 않는다', (await q()).view === 'dorling' && (await q()).sel === '서울특별시', JSON.stringify(await q()));

await page.goto(srv.url + '/history/presidential/21/');
await page.waitForSelector('#enc-seg [data-enc].is-active');
await settle();
const L0 = await histLen();
ck('기본 화면은 쿼리 없음', Object.keys(await q()).length === 0, JSON.stringify(await q()));
await page.click('#enc-seg [data-enc="dorling"]');
await settle();
ck('방식 전환 → ?view=dorling', (await q()).view === 'dorling', JSON.stringify(await q()));
ck('방식 전환은 뒤로가기 항목을 안 만든다', (await histLen()) === L0, `${L0}→${await histLen()}`);
await page.click('#enc-seg [data-enc="격자"]');
await settle();
ck('기본 방식으로 돌아오면 ?view 사라짐', !('view' in (await q())), JSON.stringify(await q()));

await page.selectOption('#round-select', JSON.stringify([20, null]));
await settle();
ck('회차 변경 → 경로 /history/presidential/20/', (await path()) === '/history/presidential/20/', await path());
ck('회차 변경은 뒤로가기 항목 하나', (await histLen()) === L0 + 1, `${L0}→${await histLen()}`);
await page.click('#enc-seg [data-enc="dorling"]');
await settle();
await page.goBack();
await settle();
ck('뒤로가기 → 21대 경로', (await path()) === '/history/presidential/21/', await path());
ck('뒤로가기 → 회차 선택도 21대', (await page.$eval('#round-select', (s) => s.value)) === JSON.stringify([21, null]));
await page.goForward();
await settle();
ck('앞으로 → 20대 + 원형까지 복원', (await path()) === '/history/presidential/20/' && (await activeEnc('#enc-seg')) === 'dorling',
  `${await path()} ${await activeEnc('#enc-seg')}`);

await page.goto(srv.url + '/history/presidential/21/');
await page.waitForSelector('[data-type]');
await settle();
const L1 = await histLen();
await page.click('[data-type="national_assembly"]');
await settle();
ck('유형 변경 → 총선 경로', /^\/history\/national-assembly\/\d+\/$/.test(await path()), await path());
ck('유형 변경(setType→setRound)도 뒤로가기 항목 하나', (await histLen()) === L1 + 1, `${L1}→${await histLen()}`);

await page.goto(srv.url + '/history/presidential/21/?sizing=dorling');
await page.waitForSelector('#enc-seg [data-enc].is-active');
await settle();
ck('옛 링크 ?sizing=dorling 호환 → 원형, ?view로 정규화', (await activeEnc('#enc-seg')) === 'dorling' && (await q()).view === 'dorling' && !('sizing' in (await q())),
  JSON.stringify(await q()));

// 줌: 실제 셀의 지역 키(시도|시군구)를 하나 집어 ?z=로 열어 본다.
await page.goto(srv.url + '/history/presidential/21/?view=hex');
await page.waitForSelector('#enc-seg [data-enc].is-active');
await settle();
const region = await page.evaluate(() => {
  for (const id of ['hex2', 'hex']) {
    const s = document.getElementById(id);
    if (s && !s.hasAttribute('hidden') && s._focusCells && s._focusCells.length) {
      return (s._focusCells.find((c) => /^서울/.test(c.region)) || s._focusCells[0]).region;
    }
  }
  return null;
});
await page.goto(srv.url + '/history/presidential/21/?view=hex&z=' + encodeURIComponent(region + '~3'));
await page.waitForSelector('#enc-seg [data-enc].is-active');
await page.waitForTimeout(1200);
const z = await page.evaluate(() => (window.HistoryFocus && HistoryFocus.capture()) || null);
ck(`?z=${region}~3 → 그 지역으로 3배 확대된 채 열린다`, !!(z && Math.abs(z.scale - 3) < 0.2 && z.region === region), JSON.stringify(z));

await page.goto(srv.url + '/history/presidential/21/?view=hex');
await page.waitForSelector('#enc-seg [data-enc].is-active');
await settle();
await page.$eval('.viz svg:not([hidden])', (e) => e.scrollIntoView({ block: 'center' }));
await page.waitForTimeout(200);
const box = await page.$eval('.viz svg:not([hidden])', (e) => { const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
await page.mouse.move(box.x, box.y);
await page.keyboard.down('Control');   // 데스크톱은 Ctrl+휠만 줌(일반 휠=페이지 스크롤)
for (let i = 0; i < 4; i++) { await page.mouse.wheel(0, -300); await page.waitForTimeout(60); }
await page.keyboard.up('Control');
await page.waitForTimeout(800);
ck('Ctrl+휠로 확대 → ?z= 기록', /~\d/.test((await q()).z || ''), JSON.stringify(await q()));

// ── archive ─────────────────────────────────────────────────────
console.log('archive');
await page.goto(srv.url + '/archive/21st-pres-2025/?v=sgg-dorling');
await page.waitForSelector('[data-map-host="sgg"][data-mode]');
await settle();
const sggMode = () => page.$eval('[data-map-host="sgg"]', (e) => e.dataset.mode);
ck('?v=sgg-dorling → 시군구 지도가 원형으로 열린다', (await sggMode()) === 'dorling', await sggMode());
const L2 = await histLen();
const tog = '.sgg-mode-toggle';
await page.click(`${tog} [data-enc="격자"]`);
await settle();
ck('토글 → ?v=sgg-grid', (await page.evaluate(() => new URLSearchParams(location.search).getAll('v'))).includes('sgg-grid'));
await page.click(`${tog} [data-enc="단색"]`);
await settle();
ck('기본 모드 → ?v 에서 sgg 빠짐', !(await page.evaluate(() => new URLSearchParams(location.search).getAll('v'))).some((k) => k.startsWith('sgg-')));
ck('archive 토글은 뒤로가기 항목을 안 만든다', (await histLen()) === L2, `${L2}→${await histLen()}`);

const sidoHost = await page.$('[data-map-host="sido"]');
if (sidoHost) {
  const modes = await page.$$eval('[data-map-host="sido"] .ar-sido-view', (els) => els.map((e) => e.dataset.view));
  const alt = modes.find((m) => m === 'turnout') || modes[1];
  if (alt) {
    await page.goto(srv.url + `/archive/21st-pres-2025/?v=sido-${alt === 'turnout' ? 'turnout' : alt}`);
    await page.waitForSelector('[data-map-host="sido"]');
    await settle();
    const m = await page.$eval('[data-map-host="sido"]', (e) => e.dataset.mode);
    const visible = await page.$eval('[data-map-host="sido"] .ar-sido-view:not([hidden])', (e) => e.dataset.view);
    ck(`?v=sido-${alt} → 시도 지도 모드·보이는 뷰 일치`, m === alt && visible === alt, `${m}/${visible}`);
  }
}

console.log('archive 당선자 필터');
await page.goto(srv.url + '/archive/9th-local-2026/?wsido=' + encodeURIComponent('부산광역시') + '&wlv=' + encodeURIComponent('광역의원'));
await page.waitForSelector('#ar-winners-sido', { timeout: 15000 }).catch(() => null);
if (await page.$('#ar-winners-sido')) {
  await settle();
  ck('?wsido= → 시도 필터 복원', (await page.$eval('#ar-winners-sido', (s) => s.value)) === '부산광역시');
  ck('?wlv= → 직급 필터 복원', (await page.$eval('#ar-winners-level', (s) => s.value)) === '광역의원');
  await page.selectOption('#ar-winners-level', '');
  await settle();
  ck('필터 해제 → ?wlv 사라짐', !('wlv' in (await q())), JSON.stringify(await q()));
} else {
  ck('9회 지선 당선자 표가 있다', false, '#ar-winners-sido 없음');
}

ck('페이지 오류 없음', errs.length === 0, errs.slice(0, 3).join(' | '));

await browser.close();
srv.close();
console.log(`\n${pass} 통과 · ${fails.length} 실패`);
process.exit(fails.length ? 1 : 0);
