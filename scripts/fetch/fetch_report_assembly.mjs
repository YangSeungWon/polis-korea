// NEC info.nec.go.kr 역대 당선인명부(report.xhtml) → 옛 총선 지역구 당선인 수집.
// LOD(data.nec SPARQL)가 14대~만 후보를 노출하는 반면, 이 엔드포인트는 제헌(1948)~ 보유.
// 13대(1988) 등 LOD에 없는 회차의 지역구 당선인(선거구별 1명)을 회수.
//
// 메커니즘:
//  - showDocument.xhtml?...secondMenuId=EPEI01(당선인명부) 로 세션·폼 로드.
//  - 폼 select는 커스텀 위젯이 native select를 가려 selectOption 실패 → JS value+change로 cascade 구동.
//  - report.xhtml POST(statementId=EPEI01_#1, electionType=2(국회의원), electionName=YYYYMMDD,
//    electionCode=2(지역구), cityCode=시도) → HTML 표(9컬럼: 선거구·정당·성명(한자)·…·득표(율)).
//  - 시도 cityCode: 서울11 부산26 대구27 인천28 광주29 경기41 강원42 충북43 충남44 전북45 전남46 경북47 경남48 제주49.
//  - 전국구(비례)는 이 메뉴에 별도 electionCode 없음 → 회차별 공식값을 build 단계에서 주입.
//
// 당선인명부 = 당선자만(낙선·전체 득표율 없음) → 의석·승자지도 O, scatter X.
//
// 사용: node scripts/fetch/fetch_report_assembly.mjs <electionName=YYYYMMDD> > data/raw/lod/report_<id>.json
//   예: node scripts/fetch/fetch_report_assembly.mjs 19880426 > data/raw/lod/report_13th.json
import { chromium } from 'playwright';

const electionName = process.argv[2];
if (!electionName) { console.error('usage: node fetch_report_assembly.mjs <YYYYMMDD>'); process.exit(1); }

const SIDO = { 11: '서울특별시', 26: '부산광역시', 27: '대구광역시', 28: '인천광역시', 29: '광주광역시',
  41: '경기도', 42: '강원특별자치도', 43: '충청북도', 44: '충청남도', 45: '전북특별자치도',
  46: '전라남도', 47: '경상북도', 48: '경상남도', 49: '제주특별자치도' };

const b = await chromium.launch();
const pg = await b.newPage();
await pg.goto('https://info.nec.go.kr/main/showDocument.xhtml?electionId=0000000000&topMenuId=EP&secondMenuId=EPEI01',
  { waitUntil: 'networkidle', timeout: 45000 });
await pg.waitForTimeout(800);

const all = [];
for (const cc of Object.keys(SIDO)) {
  const rows = await pg.evaluate(async ({ cc, electionName }) => {
    const body = new URLSearchParams({
      electionId: '0000000000', requestURI: '/electioninfo/0000000000/ep/epei01.jsp',
      topMenuId: 'EP', secondMenuId: 'EPEI01', menuId: 'EPEI01', statementId: 'EPEI01_#1',
      oldElectionType: '0', electionType: '2', electionName, electionCode: '2',
      cityCode: cc, proportionalRepresentationCode: '-1', townCode: '-1', x: '50', y: '15',
    }).toString();
    const r = await fetch('/electioninfo/electionInfo_report.xhtml',
      { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body });
    const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
    const trs = [...(doc.querySelector('#table01,.table01,table')?.querySelectorAll('tbody tr') || [])];
    return trs.map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent.replace(/\s+/g, ' ').trim()))
      .filter((r) => r.length >= 9);
  }, { cc, electionName });
  for (const r of rows) {
    const vc = r[8] || '';
    all.push({
      sido: SIDO[cc], sgg: r[0], party: r[1], name: (r[2] || '').replace(/\(.*\)/, '').trim(),
      votes: parseInt((vc.split('(')[0] || '').replace(/[^0-9]/g, '')) || 0,
      pct: parseFloat(vc.match(/\(([\d.]+)/)?.[1] || '') || null,
    });
  }
  await pg.waitForTimeout(250);
}
await b.close();
process.stdout.write(JSON.stringify(all));
console.error(`수집 ${all.length}명`);
