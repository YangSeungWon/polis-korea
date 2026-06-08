// NEC 개표현황(VCCP09) → 옛 직선 대선(2·3·5·6·7대) 시도별 후보 득표.
// statementId 동적이라 폼 조작+#searchBtn 클릭+화면 스크랩. 회차마다 새 브라우저(누적 reload 크래시 회피),
// 시도별 재시도+기존 파일 병합(간헐 실패 대응). 후보 헤더 '정당+성명' / '합계' 행=시도 총계.
// 사용: node scripts/fetch/fetch_pres_old.mjs  → data/raw/lod/pres_{n}_{date}.json
import { chromium } from 'playwright';
import { writeFileSync, readFileSync, existsSync } from 'fs';
const R = '/home/whysw/Documents/vote-via-data';
const SIDO = { 11:'서울특별시',26:'부산광역시',27:'대구광역시',28:'인천광역시',29:'광주광역시',41:'경기도',42:'강원특별자치도',43:'충청북도',44:'충청남도',45:'전북특별자치도',46:'전라남도',47:'경상북도',48:'경상남도',49:'제주특별자치도' };
const PRES = { 2:'19520805', 3:'19560515', 5:'19631015', 6:'19670503', 7:'19710427' };
const URL = 'https://info.nec.go.kr/main/showDocument.xhtml?electionId=0000000000&topMenuId=VC&secondMenuId=VCCP09';
for (const [n, en] of Object.entries(PRES)) {
  const path = `${R}/data/raw/lod/pres_${n}_${en}.json`;
  const out = existsSync(path) ? JSON.parse(readFileSync(path)) : {};
  const b = await chromium.launch({ args: ['--disable-dev-shm-usage', '--no-sandbox'] });
  const pg = await b.newPage();
  const setv = (nm, v) => pg.evaluate(({ nm, v }) => { const s = document.querySelector(`[name=${nm}],#${nm}`); if (s) { s.value = v; s.dispatchEvent(new Event('change', { bubbles: true })); } }, { nm, v });
  const ready = (nm, v) => pg.evaluate(({ nm, v }) => { const s = document.querySelector(`[name=${nm}],#${nm}`); return s && [...s.options].some(o => o.value === v); }, { nm, v });
  const waitOpt = async (nm, v) => { const t = Date.now(); while (Date.now() - t < 6000) { if (await ready(nm, v)) return true; await pg.waitForTimeout(250); } return false; };
  async function one(cc) {
    await pg.goto(URL, { waitUntil: 'domcontentloaded', timeout: 40000 }); await pg.waitForTimeout(700);
    await setv('electionType', '1'); await pg.waitForTimeout(400); if (!await waitOpt('electionName', en)) return null;
    await setv('electionName', en); await pg.waitForTimeout(400); if (!await waitOpt('electionCode', '1')) return null;
    await setv('electionCode', '1'); await pg.waitForTimeout(400); if (!await waitOpt('cityCode', cc)) return null;
    await setv('cityCode', cc); await pg.waitForTimeout(400);
    await pg.click('#searchBtn', { timeout: 6000 }); await pg.waitForTimeout(1300);
    return await pg.evaluate(() => { const t = document.querySelector('#table01,.table01,table'); if (!t) return null; const ths = [...t.querySelectorAll('thead th')].map(x => x.textContent.replace(/\s+/g, '').trim()); const rows = [...t.querySelectorAll('tbody tr')]; const sum = rows.find(tr => /^합계$/.test(tr.querySelector('td')?.textContent?.trim() || '')) || rows[0]; const tds = [...sum.querySelectorAll('td')].map(x => x.textContent.trim()); return ths.some(x => /득표율/.test(x)) ? { ths, tds } : null; });
  }
  for (const cc of Object.keys(SIDO)) {
    if (out[SIDO[cc]]?.ths) continue;
    for (let t = 0; t < 3; t++) { try { const d = await one(cc); if (d) { out[SIDO[cc]] = d; break; } } catch (e) {} await pg.waitForTimeout(300); }
  }
  writeFileSync(path, JSON.stringify(out));
  console.error(`${n}대: ${Object.values(out).filter(v => v?.ths).length} 시도`);
  await b.close();
}
