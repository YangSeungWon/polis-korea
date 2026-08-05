// 실제 navigation 무결성 — 정적 href 감사와 **별개의 검사**다.
//
// 정적 링크 108,439개가 0 broken이었는데 /history/local/9/는 404였다.
// lens-switcher가 런타임에 조립하는 URL이라 파일을 훑어서는 안 보인다.
// 지선은 /history/local/{n}/ 자체가 없고 직위 세그먼트까지 있어야 한다.
//
// 그래서 세 층을 본다:
//   1. 렌더된 링크    — JS가 만든 href 포함
//   2. 토글 후 링크   — 상호작용으로 바뀐 상태
//   3. pushState 경로 — 링크가 아니라 주소창. href 감사로는 절대 안 보인다
//
// 실행: node tests/ui/test_routes.mjs
import { chromium } from 'playwright';
import fs from 'fs';
import { serve } from './server.mjs';

const ROOT = new URL('../..', import.meta.url).pathname;
let pass = 0; const fails = [];
const ck = (n, c, d) => {
  if (c) { pass++; console.log(`  ✓ ${n}`); }
  else { fails.push(n); console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`); }
};

const srv = await serve(ROOT, 8290);
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage();

const seen = new Map();          // path → status (같은 경로는 한 번만)
async function alive(path) {
  if (seen.has(path)) return seen.get(path);
  const r = await page.request.get(srv.url + path, { failOnStatusCode: false });
  seen.set(path, r.status());
  return r.status();
}
async function deadLinks() {
  const hrefs = await page.evaluate(() =>
    [...document.querySelectorAll('a[href^="/"]')]
      .map((a) => a.getAttribute('href').split('#')[0].split('?')[0]));
  const out = [];
  for (const h of new Set(hrefs)) {
    if (!h || h === '/') continue;
    if (await alive(h) >= 400) out.push(h);
  }
  return out;
}

// ── 1. archive 전 회차의 렌즈 링크 ──────────────────────────────────────────
console.log('\n[렌즈] archive → polls·history 전환 링크');
const archives = fs.readdirSync(ROOT + 'archive')
  .filter((d) => fs.existsSync(`${ROOT}archive/${d}/index.html`));
const lensDead = [];
for (const d of archives) {
  await page.goto(`${srv.url}/archive/${d}/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(450);
  const hrefs = await page.evaluate(() =>
    [...document.querySelectorAll('.lens-chip[href]')].map((a) => a.getAttribute('href')));
  for (const h of new Set(hrefs)) {
    if (await alive(h) >= 400) lensDead.push(`${d}: ${h}`);
  }
}
ck(`archive ${archives.length}개의 렌즈 링크가 전부 살아 있음`,
  !lensDead.length, lensDead.slice(0, 4).join(' · '));

// ── 2. 탐색 화면 — 초기 + 토글 후 ───────────────────────────────────────────
console.log('\n[탐색] 초기 상태와 토글 후');
for (const u of ['/history.html', '/polls.html', '/elections.html', '/parties.html',
                 '/tracker.html', '/chronology.html', '/byelection.html', '/region/']) {
  await page.goto(srv.url + u, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  const d1 = await deadLinks();
  const btns = await page.$$('.seg-btn, [data-view], [data-sgmode]');
  for (const el of btns.slice(0, 6)) {
    try { await el.click({ timeout: 1200 }); await page.waitForTimeout(350); } catch { /* 가려짐 */ }
  }
  await page.waitForTimeout(500);
  const d2 = await deadLinks();
  ck(`${u} 링크 살아 있음 (초기·토글 후)`, !d1.length && !d2.length,
    [...new Set([...d1, ...d2])].slice(0, 3).join(' · '));
}

// ── 3. pushState 경로 — 주소창은 링크가 아니다 ──────────────────────────────
console.log('\n[주소창] 회차를 바꾸면 URL이 갈린다');
await page.goto(srv.url + '/history.html', { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
const pushDead = []; let n_push = 0;
for (const t of (await page.$$('.seg-btn')).slice(0, 3)) {
  try { await t.click({ timeout: 1500 }); await page.waitForTimeout(600); } catch { continue; }
  for (const r of (await page.$$('[data-n], .seg-rounds .seg-btn')).slice(-4)) {
    try { await r.click({ timeout: 1200 }); await page.waitForTimeout(500); } catch { continue; }
    const path = new URL(page.url()).pathname;
    if (path === '/history.html') continue;
    n_push++;
    if (await alive(path) >= 400) pushDead.push(path);
  }
}
ck(`회차 전환 ${n_push}회의 주소가 전부 실재`, !pushDead.length,
  [...new Set(pushDead)].slice(0, 3).join(' · '));

// ── 4. 대표 경로 fixture — 회귀 방지 ────────────────────────────────────────
console.log('\n[fixture] 대표 route');
for (const path of ['/history/local/9/governor/', '/history/local/8/governor/',
                    '/history/presidential/21/', '/history/national-assembly/22/',
                    '/archive/9th-local-2026/', '/polls/9th-local-2026/', '/region/']) {
  ck(path, await alive(path) < 400, String(seen.get(path)));
}
// 지선에 직위 없는 경로는 **원래 없다** — 있다고 착각해 만들면 다시 404가 난다
ck('/history/local/9/ 는 설계상 없다 (직위 세그먼트 필수)', await alive('/history/local/9/') >= 400,
  String(seen.get('/history/local/9/')));

await browser.close();
await srv.close();
console.log(`\n총 ${pass + fails.length}건: ${pass} pass, ${fails.length} fail`);
process.exit(fails.length ? 1 : 0);
