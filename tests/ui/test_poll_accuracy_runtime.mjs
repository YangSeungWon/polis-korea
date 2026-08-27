// 화면이 말하는 적중률이 **파일과 같은가**.
//
// 여론조사 1위 vs 실제 1위는 빌드가 센다(scripts/build/poll_accuracy.py).
// 페이지는 __INITIAL_STATE__.election.accuracy를 읽기만 한다. 이 검사가 그 계약을
// 고정한다 — 누군가 JS에서 다시 세기 시작하면 여기서 갈라진다.
//
// 막는 사고: 계산이 두 벌이 되는 것. 2026-08-27에 계산을 옮기며 JS 결함 둘이 드러났다.
//   · 대선이 candidates[0]을 pct 정렬 없이 1위로 썼다 — 20대 대선 조사의 49%가
//     후보순≠득표순이라 헤드라인이 7/17이었다(실제 13/17).
//   · 9회 지선이 SIDO_HEX_LAYOUT 17개를 도는데 신설 전남광주가 그 표에 없어
//     통합 1선거가 통째로 빠졌다(13/15 → 14/16).
// 둘 다 **화면에 보이는 숫자가 조용히 틀린** 종류라, 눈으로는 몇 년이 지나도 안 보인다.
//
// 실행: node tests/ui/test_poll_accuracy_runtime.mjs
import { chromium } from 'playwright';
import fs from 'fs';
import { serve } from './server.mjs';

const ROOT = new URL('../..', import.meta.url).pathname;
let pass = 0; const fails = [];
const ck = (n, c, d) => {
  if (c) { pass++; console.log(`  ✓ ${n}`); }
  else { fails.push(n); console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`); }
};

const acc = JSON.parse(fs.readFileSync(`${ROOT}/data/polls/accuracy.json`, 'utf8')).elections;
const OFFICES = {
  local: ['광역단체장', '교육감', '기초단체장'],
  presidential: ['대통령'],
  general_election: ['국회의원'],
};

const srv = await serve(ROOT, 8293);
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1400, height: 1600 } })).newPage();

console.log('[적중률] 화면의 숫자 == data/polls/accuracy.json');
for (const [slug, e] of Object.entries(acc).sort()) {
  await page.goto(`http://localhost:8293/polls/${slug}/`, { waitUntil: 'networkidle', timeout: 40000 });
  await page.waitForTimeout(6000);
  for (const off of OFFICES[e.kind] || []) {
    const o = e.offices[off];
    if (!o) continue;
    let txt;
    if (e.kind === 'local') {
      // 직위 탭을 눌러야 그 직위의 뱃지가 나온다.
      const b = await page.$(`button:has-text("${off}")`);
      if (b) { await b.click(); await page.waitForTimeout(2200); }
      txt = await page.evaluate(() => {
        const h = document.getElementById('result-accuracy');
        return h ? h.innerText : '';
      });
    } else {
      txt = await page.evaluate(() => document.body.innerText);
    }
    const m = /적중\s*(\d+)\s*\/\s*(\d+)/.exec(txt || '');
    const got = m ? `${m[1]}/${m[2]}` : '0/0';
    ck(`${slug} ${off}`, got === `${o.match}/${o.total}`,
      `화면 ${got} ≠ 파일 ${o.match}/${o.total}`);
  }
}

// 계산이 JS로 돌아오지 않았는가 — 소스에서 직접 본다. 숫자가 우연히 같을 수 있어
// 값 비교만으로는 '다시 세기 시작한 것'을 못 잡는다.
const SRC = ['adapter.js', 'result-overlay.js', 'render-hex.js', 'render-pres.js', 'render-gen.js'];
for (const f of SRC) {
  const s = fs.readFileSync(`${ROOT}/assets/polls/${f}`, 'utf8');
  // adapter.js는 읽기 접근자를 갖는 곳이라 예외.
  const counting = /samePartyName\s*\(/.test(s) && f !== 'adapter.js';
  ck(`${f}: 적중을 다시 세지 않는다`, !counting,
    'samePartyName으로 폴↔실제를 비교하고 있다 — 계산은 빌드가 한다');
}

await browser.close();
srv.close();
console.log(`\n총 ${pass + fails.length}건: ${pass} pass, ${fails.length} fail`);
process.exit(fails.length ? 1 : 0);
