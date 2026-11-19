// 지역 허브 — 지도에서 고르고 이름으로 찾는다.
//
// 막는 사고:
//   · 지도 칸이 없는 페이지로 보낸다(이름 모양으로 slug를 지었다).
//   · 지도 칸이 정당색을 띤다(이 페이지는 어느 선거의 결과가 아니다).
//   · 목록을 접으면서 링크가 HTML에서 사라진다(크롤러·비JS가 지역 페이지에 못 닿는다).
//   · 검색이 지도에 안 걸린다 / 검색해도 접힌 목록이 안 열린다.
//
// 실행: node tests/ui/test_region_hub.mjs
import { chromium } from 'playwright';
import fs from 'fs';
import { serve } from './server.mjs';

let pass = 0; const fails = [];
const ck = (n, c, d) => { if (c) { pass++; console.log(`  ✓ ${n}`); } else { fails.push(n); console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`); } };
const ROOT = new URL('../..', import.meta.url).pathname;

// JS 없이도 — HTML에 전 지역 링크가 있다
const html = fs.readFileSync(ROOT + 'region/index.html', 'utf8');
const pages = fs.readdirSync(ROOT + 'region').filter((d) => fs.existsSync(`${ROOT}region/${d}/index.html`));
const linked = new Set([...html.matchAll(/href="\/region\/([^"]+?)\/"/g)].map((m) => decodeURIComponent(m[1])));
const missing = pages.filter((p) => !linked.has(p));
ck(`HTML만으로 지역 페이지 전부에 링크 (${pages.length})`, missing.length === 0, missing.slice(0, 3).join(' '));

const srv = await serve(ROOT, 8300);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
const errs = [];
page.on('pageerror', (e) => errs.push(String(e)));
await page.goto(srv.url + '/region/');
await page.waitForSelector('#rg-map.is-ready', { timeout: 20000 }).catch(() => null);
const m = await page.evaluate(() => {
  const as = [...document.querySelectorAll('#rg-map a')];
  return {
    n: as.length,
    hrefs: as.map((a) => a.getAttribute('href')),
    fills: [...new Set([...document.querySelectorAll('#rg-map .hex-cell')].map((p) => getComputedStyle(p).fill))],
    open: document.getElementById('rg-list').open,
  };
});
ck(`지도 칸이 링크다 (${m.n})`, m.n >= 225, String(m.n));
const bad = m.hrefs.filter((h) => !fs.existsSync(ROOT + decodeURIComponent(h).replace(/^\//, '') + 'index.html'));
ck('지도 링크는 전부 실재 페이지', bad.length === 0, bad.slice(0, 3).join(' '));
ck('칸은 정당색이 아니다(한 가지 중립색)', m.fills.length === 1, m.fills.join(' '));
ck('목록은 처음엔 접혀 있다', m.open === false);
const href0 = m.hrefs.find((h) => decodeURIComponent(h).includes('김천시'));
await page.click(`#rg-map a[href="${href0}"]`, { force: true });
await page.waitForLoadState();
ck('칸을 누르면 그 지역 페이지', decodeURIComponent(new URL(page.url()).pathname) === '/region/경상북도-김천시/', page.url());

await page.goto(srv.url + '/region/?q=' + encodeURIComponent('분당'));
await page.waitForSelector('#rg-map.is-ready', { timeout: 20000 }).catch(() => null);
const s = await page.evaluate(() => ({
  open: document.getElementById('rg-list').open,
  vis: [...document.querySelectorAll('.rg-item:not([hidden])')].map((a) => a.textContent),
  dim: document.getElementById('rg-map').classList.contains('is-searching'),
}));
ck('검색하면 목록이 열리고 맞는 이름만(일반구도 잡힌다)', s.open && s.vis.length >= 1 && s.vis.every((t) => t.includes('분당')), s.vis.join(' '));
ck('검색하면 지도는 흐려서 맞춘다(지우지 않는다)', s.dim);
await page.goto(srv.url + '/region/?q=' + encodeURIComponent('성남'));
await page.waitForSelector('#rg-map.is-ready', { timeout: 20000 }).catch(() => null);
const hits = await page.$$eval('#rg-map .is-hit', (e) => e.length);
ck('“성남” → 지도에서 성남 칸이 밝다', hits >= 1, String(hits));

await page.setViewportSize({ width: 390, height: 844 });
await page.goto(srv.url + '/region/');
await page.waitForTimeout(1200);
ck('390px 가로 스크롤 없음', (await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 1);
ck('페이지 오류 없음', errs.length === 0, errs.slice(0, 2).join(' | '));
await browser.close(); srv.close();
console.log(`\n${pass} 통과 · ${fails.length} 실패`);
process.exit(fails.length ? 1 : 0);
