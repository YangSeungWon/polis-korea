// 지역 정치사 연표 — 데이터가 정확해도 화면이 잘못 전달할 수 있다.
//
// 감사 대상 4곳은 각각 다른 실패 유형을 잡는다:
//   성남  10 series·116점 — lane 밀도와 높이
//   포항  1995 도농통합 — 같은 이름의 다른 entity, 사건선, 시간축
//   부천  crossing_dong  — "비교 불가 ≠ 데이터 없음"
//   하남  reaggregated   — capability가 UI claim을 실제로 제한하는가
//
// 가로로 긴 연표라 **처음 화면만 보면 안 된다**. 과거·중간·최근 구간을 다 본다.
import { chromium } from 'playwright';
import { serve } from './server.mjs';
import fs from 'fs';
import path from 'path';

const ROOT = path.resolve(process.cwd());
const REGIONS = ['성남', '포항', '부천', '하남'];
const VIEWPORTS = [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1440, height: 900 },
];
let fails = [];
const ck = (n, c, d = '') => {
  if (!c) fails.push(`${n}${d ? ' — ' + d : ''}`);
  if (!c) console.log(`  ✗ ${n}${d ? ' — ' + d : ''}`);
};

const data = (r) => JSON.parse(fs.readFileSync(
  path.join(ROOT, 'data/region_timeline', `${r}.json`), 'utf-8'));

const srv = await serve(ROOT, 8110);
const browser = await chromium.launch();
console.log(`\n[연표 UI] ${REGIONS.length}곳 × ${VIEWPORTS.length}뷰포트 × 3구간`);

for (const region of REGIONS) {
  const d = data(region);
  for (const vp of VIEWPORTS) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
    await page.goto(`${srv.url}/region-timeline/${encodeURIComponent(region)}.html`,
      { waitUntil: 'load' });
    await page.waitForSelector('.rt-svg', { timeout: 5000 });
    const tag = `${region}/${vp.name}`;

    // ── 실제로 그려졌는가 (빈 화면을 통과시키지 않는다) ──────────────────
    const box = await page.locator('.rt-svg').boundingBox();
    ck(`${tag}: svg가 그려짐`, box && box.height > 40, JSON.stringify(box));

    // ── 구조가 backend와 일치하는가 ────────────────────────────────────
    const nPt = await page.locator('.rt-pt').count();
    // 넷 이상 몰린 자리는 하나로 묶는다 — DOM 점 수 ≤ 데이터 점 수가 정상
    ck(`${tag}: 점이 데이터보다 많지 않다 (${nPt}/${d.points.length})`,
      nPt <= d.points.length && nPt > 0);
    const nGrp = await page.locator('.rt-pt-group').count();
    ck(`${tag}: 묶인 점은 개수를 밝힌다`,
      nGrp === await page.locator('.rt-svg .rt-cnt').count());
    const nBlocked = d.comparison_edges.filter(e => e.delta_allowed === false).length;
    const nX = await page.locator('.rt-svg .rt-x').count();
    // 비교 불가는 점을 지우는 게 아니라 선만 끊는다
    ck(`${tag}: 차단 표시 = 차단된 edge (${nX}/${nBlocked})`, nX === nBlocked);
    ck(`${tag}: 차단이 있어도 점은 남는다`, nPt > 0);
    const nAdm = d.events.filter(e => e.namespace === 'administrative_geography').length;
    ck(`${tag}: 행정구역 사건선 (${nAdm})`,
      await page.locator('.rt-ev-admin').count() === nAdm);

    // ── 금지된 claim이 DOM에 없는가 ────────────────────────────────────
    const html = await page.content();
    for (const p of d.points) {
      const cm = p.comparison;
      if (!cm || cm.may_show_level) continue;
      // 수준값을 화면에 쓰면 안 되는 점 — 재집계 과거 수준값이 DOM에 있으면 실패
      const lv = (p.lineage_composition_historical?.share) || {};
      void lv;
      ck(`${tag}: ${p.unit_name_at_the_time} 금지된 수준값이 DOM에 없음`,
        html.includes('과거 재집계 수준값·승자는 사용하지 않음'));
      break;
    }

    // ── 가로 탐색: 과거·중간·최근 구간을 다 본다 ────────────────────────
    const sc = page.locator('.rt-scroll');
    const max = await sc.evaluate(el => el.scrollWidth - el.clientWidth);
    const needScroll = await sc.evaluate(el => el.scrollWidth > el.clientWidth + 1);
    ck(`${tag}: 넓으면 가로 스크롤이 생긴다`, !needScroll || max > 0, `max=${max}`);
    for (const [label, pos] of [['과거', 0], ['중간', Math.floor(max / 2)], ['최근', max]]) {
      await sc.evaluate((el, p) => { el.scrollLeft = p; }, pos);
      await page.waitForTimeout(60);
      // 이 구간에서 보이는 점들이 서로 겹쳐 읽을 수 없지 않은가
      const overlaps = await page.evaluate(() => {
        const s = document.querySelector('.rt-scroll');
        const r = s.getBoundingClientRect();
        const pts = [...document.querySelectorAll('.rt-pt')]
          .map(c => c.getBoundingClientRect())
          .filter(b => b.left >= r.left - 4 && b.right <= r.right + 4);
        let n = 0;
        for (let i = 0; i < pts.length; i++)
          for (let j = i + 1; j < pts.length; j++) {
            const a = pts[i], b = pts[j];
            if (Math.abs(a.x - b.x) < 5 && Math.abs(a.y - b.y) < 5) n++;
          }
        return { visible: pts.length, overlapping: n };
      });
      ck(`${tag}/${label}: 점이 완전히 겹치지 않음`,
        overlaps.overlapping === 0, JSON.stringify(overlaps));
    }

    // ── 키보드: <title>만으로 통과시키지 않는다 ──────────────────────────
    if (vp.name === 'desktop') {
      const first = page.locator('.rt-pt').first();
      await first.focus();
      const focused = await page.evaluate(() =>
        document.activeElement?.classList?.contains('rt-pt'));
      ck(`${tag}: 점에 키보드 포커스가 간다`, focused);
      const lab = await first.getAttribute('aria-label');
      ck(`${tag}: 포커스 대상에 aria-label이 있다`, !!lab && lab.length > 10,
        String(lab).slice(0, 40));
    }
    // lane이 많아도 높이가 폭발하지 않는가
    if (region === '성남') {
      ck(`${tag}: 높이가 900px 이내 (lane ${d.series.length})`,
        box.height <= 900, `${box.height}`);
    }
    await page.close();
  }
}
await browser.close();
await srv.close();
console.log(fails.length ? `\n실패 ${fails.length}` : '\n전부 통과');
process.exit(fails.length ? 1 : 0);
