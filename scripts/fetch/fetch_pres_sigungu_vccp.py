"""대선 시군구별 개표(전체 후보) — info.nec.go.kr VCCP09 개표현황.

LOD는 대선을 전국 합계만 보유. 선거통계시스템 VCCP09는 시군구별 후보 득표를 주지만,
보고서가 **세션 바인딩 statementId**(예: 13대=VCCP09_#90)와 세션 쿠키로만 응답한다.
→ 브라우저에서 해당 대선 개표현황을 한 번 연 뒤, 그 report 요청의 쿠키와 statementId를
   넘기면 14개 시도 전부 자동 수집한다. (electionType=1, electionCode=1, electionName=YYYYMMDD)

시군구명 정규화: '중구(서울)'·'동구(광주)' → 괄호 제거, '성동구갑/을' 개표구 → 갑/을 합산.
'합계'/'소계'·정적 1960 간선표는 (선거인수·투표수 정수 검사로) 자동 제외.

사용:
  NEC_COOKIE='_fwb=...; WMONID=...; JSESSIONID=...' \
    python3 scripts/fetch/fetch_pres_sigungu_vccp.py --name 19871216 --stmt VCCP09_#90 [--out data/results/13th-pres-1987.json]
출력: --out 파일의 race에 scope='sigungu' tc='1' race들 병합(nation·sido 유지). --out 없으면 stdout.
"""
from __future__ import annotations
import argparse, gzip, json, os, re, sys, time, urllib.parse, urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIDO = {11: '서울특별시', 26: '부산광역시', 27: '대구광역시', 28: '인천광역시', 29: '광주광역시',
        41: '경기도', 42: '강원특별자치도', 43: '충청북도', 44: '충청남도', 45: '전북특별자치도',
        46: '전라남도', 47: '경상북도', 48: '경상남도', 49: '제주특별자치도'}
ENDPOINT = 'https://info.nec.go.kr/electioninfo/electionInfo_report.xhtml'


def fetch(cc, name, stmt, cookie):
    data = urllib.parse.urlencode({
        'electionId': '0000000000', 'requestURI': '/electioninfo/0000000000/vc/vccp09.jsp',
        'topMenuId': 'VC', 'secondMenuId': 'VCCP09', 'menuId': 'VCCP09', 'statementId': stmt,
        'oldElectionType': '0', 'electionType': '1', 'electionName': name, 'electionCode': '1',
        'cityCode': str(cc), 'townCode': '-1', 'sggCityCode': '-1', 'x': '41', 'y': '19'}).encode()
    req = urllib.request.Request(ENDPOINT, data=data, headers={
        'Cookie': cookie, 'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': ENDPOINT, 'User-Agent': 'Mozilla/5.0'})
    raw = urllib.request.urlopen(req, timeout=30).read()
    try:
        return gzip.decompress(raw).decode('utf-8', 'replace')
    except Exception:
        return raw.decode('utf-8', 'replace')


def _cells(tr):
    return [re.sub(r'<[^>]+>', '', c).replace('&nbsp;', ' ').strip()
            for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)]


def _norm(nm):
    nm = re.sub(r'\(.*?\)', '', nm).strip()        # (서울)/(광주) 제거
    return re.sub(r'[갑을병정무]$', '', nm).strip()  # 개표구 갑/을 합산


def parse(h, sido):
    seg = re.sub(r'<[^>]+>', ' ', h[h.find('후보자별 득표율'):])
    seg = re.sub(r'\s+', ' ', seg)
    seg = seg[:seg.find(' 계 ')].replace('후보자별 득표율 (%)', '')
    toks = seg.split()
    cands = [{'party': toks[i], 'name': toks[i + 1]} for i in range(0, len(toks) - 1, 2)]
    K = len(cands)
    isint = lambda s: bool(re.fullmatch(r'[\d,]+', s or ''))
    agg = defaultdict(lambda: {'el': 0, 'vo': 0, 'v': [0] * K, 'valid': 0, 'inv': 0})
    for r in [_cells(tr) for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', h, re.S)]:
        if len(r) < 3 + K + 2 or r[0] in ('합계', '소계', ''):
            continue
        if not (isint(r[1]) and isint(r[2])):       # 1960 정적표·헤더 제외
            continue
        try:
            el, vo = int(r[1].replace(',', '')), int(r[2].replace(',', ''))
            votes = [int(r[3 + j].replace(',', '')) for j in range(K)]
            valid, inv = int(r[3 + K].replace(',', '')), int(r[4 + K].replace(',', ''))
        except ValueError:
            continue
        a = agg[_norm(r[0])]
        a['el'] += el; a['vo'] += vo; a['valid'] += valid; a['inv'] += inv
        for j in range(K):
            a['v'][j] += votes[j]
    races = []
    for nm, a in agg.items():
        cl = [{'name': cands[j]['name'], 'party': cands[j]['party'], 'votes': a['v'][j],
               'pct': round(a['v'][j] / a['valid'] * 100, 2) if a['valid'] else 0} for j in range(K)]
        cl.sort(key=lambda c: -c['votes'])
        for rk, c in enumerate(cl):
            c['rank'] = rk + 1
        races.append({'sg_typecode': '1', 'scope': 'sigungu', 'sido': sido, 'sigungu': nm,
                      'electors': a['el'], 'voters': a['vo'], 'valid_votes': a['valid'],
                      'invalid_votes': a['inv'], 'candidates': cl})
    return races


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True, help='electionName YYYYMMDD (예 19871216)')
    ap.add_argument('--stmt', required=True, help='statementId (브라우저 요청서 복사, 예 VCCP09_#90)')
    ap.add_argument('--out', help='병합할 {n}th-pres-{year}.json (없으면 stdout)')
    a = ap.parse_args()
    cookie = os.environ.get('NEC_COOKIE')
    if not cookie:
        sys.exit('NEC_COOKIE 환경변수 필요 (브라우저 report 요청의 Cookie 헤더)')
    allraces = []
    for cc, sido in SIDO.items():
        races = parse(fetch(cc, a.name, a.stmt, cookie), sido)
        allraces += races
        print(f'{sido}: {len(races)} 시군구', file=sys.stderr)
        time.sleep(0.3)
    print(f'총 {len(allraces)} 시군구', file=sys.stderr)
    if a.out:
        p = ROOT / a.out
        d = json.loads(p.read_text(encoding='utf-8'))
        d['races'] = [r for r in d['races'] if r.get('scope') != 'sigungu'] + allraces
        d.setdefault('_meta', {})['_sigungu_source'] = f'info.nec.go.kr VCCP09 ({a.stmt})'
        p.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        print(f'병합 → {a.out}', file=sys.stderr)
    else:
        print(json.dumps(allraces, ensure_ascii=False))


if __name__ == '__main__':
    main()
