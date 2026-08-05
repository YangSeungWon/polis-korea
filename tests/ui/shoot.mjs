// 대표 화면 스크린샷 — 사람이 보는 용도. 통과/실패는 test_ui_invariants가 낸다.
//
// 4,900개를 다 찍을 필요는 없다. 서로 다른 실패 양식을 가진 화면(pages.mjs)만
// desktop light / desktop dark / mobile 세 벌로 고정해 계속 같은 걸 본다.
//
// 실행: node tests/ui/shoot.mjs [--out=디렉터리] [--only=archive-pres]
import { chromium } from 'playwright';
import fs from 'fs';
import { serve } from './server.mjs';
import { PAGES, VIEWPORTS } from './pages.mjs';

const ROOT = new URL('../..', import.meta.url).pathname;
const arg = (k, d) => (process.argv.find((a) => a.startsWith(`--${k}=`)) || `=${d}`).split('=').slice(1).join('=');
const OUT = arg('out', '/tmp/polis-ui');
const only = arg('only', '');

const SHOTS = [
  { id: 'desktop-light', vp: VIEWPORTS[0], scheme: 'light' },
  { id: 'desktop-dark', vp: VIEWPORTS[0], scheme: 'dark' },
  { id: 'mobile-light', vp: VIEWPORTS[2], scheme: 'light' },
];

fs.mkdirSync(OUT, { recursive: true });
const srv = await serve(ROOT, 8300);
const browser = await chromium.launch();
let n = 0;

for (const spec of PAGES.filter((p) => !only || p.id === only)) {
  for (const shot of SHOTS) {
    const ctx = await browser.newContext({
      viewport: { width: shot.vp.width, height: shot.vp.height },
      colorScheme: shot.scheme, deviceScaleFactor: 1,
    });
    const page = await ctx.newPage();
    await page.goto(srv.url + spec.url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForFunction(() => {
      const m = document.querySelector('main') || document.body;
      return [...document.querySelectorAll('svg')].some((s) => s.querySelectorAll('path,polygon,circle,rect,g').length > 5)
        || (m.innerText || '').trim().length > 300;
    }, null, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(700);
    const f = `${OUT}/${spec.id}__${shot.id}.png`;
    await page.screenshot({ path: f, fullPage: true });
    console.log(`  ${f}`);
    n++;
    await ctx.close();
  }
}
await browser.close();
await srv.close();
console.log(`\n${n}장 · ${OUT}`);
