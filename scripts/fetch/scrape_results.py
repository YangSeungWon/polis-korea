"""data.go.kr 공공데이터포털에서 선거 개표결과 CSV 다운로드 → 시군구 집계 → JSON.

CSV 스키마 (선관위 표준):
  시도명, 구시군명, 읍면동명, 투표구명, 후보자, 득표수
  - 읍면동명="거소·선상투표"·"관외사전투표"·"재외투표" 등은 특수 행
  - 후보자="선거인수"·"투표수"·"무효투표수"·"기권수"는 행정값
  - 후보자="<정당명> <후보자명>"은 후보 득표

회차별 atchFileId는 META 테이블에 매핑.

사용:
  .venv/bin/python scripts/fetch/scrape_results.py --type presidential --n 21
  .venv/bin/python scripts/fetch/scrape_results.py --all
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "results_csv"
OUT_DIR = ROOT / "data" / "results"

DOWNLOAD_URL = "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={atch}&fileDetailSn=1&insertDataPrcus=N"

# 회차별 atchFileId — data.go.kr 공공데이터포털에서 추출.
# (type, n) → atchFileId
# data.go.kr 검색 키워드: "제N대 대통령선거 개표결과" / "제N회 전국동시지방선거 개표결과"
META = {
    ('presidential', 16): {
        'atch': 'FILE_000000003170796',
        'date': '2002-12-19', 'label': '16대 대통령선거',
    },
    ('presidential', 17): {
        'atch': 'FILE_000000003170804',
        'date': '2007-12-19', 'label': '17대 대통령선거',
    },
    ('presidential', 21): {
        'atch': 'FILE_000000003525373',
        'date': '2025-06-03', 'label': '21대 대통령선거',
    },
    ('national_assembly', 22): {
        # 비례대표 정당투표 (시군구 단위)
        'atch': 'FILE_000000003182982',
        'date': '2024-04-10', 'label': '22대 국회의원선거 (비례대표)',
        'schema': 'party',
    },
    ('national_assembly', 22, 'district'): {
        # 지역구 선거구별 (선거구 단위 — 별도 hex 필요)
        'atch': 'FILE_000000003172714',
        'date': '2024-04-10', 'label': '22대 국회의원선거 (지역구)',
        'schema': 'district',
    },
    ('local', 5): {
        'atch': 'FILE_000000003189760',
        'date': '2010-06-02', 'label': '5회 전국동시지방선거',
        'schema': 'local',
    },
    ('local', 6): {
        'atch': 'FILE_000000003157447',
        'date': '2014-06-04', 'label': '6회 전국동시지방선거',
        'schema': 'local',
    },
    ('local', 7): {
        'atch': 'FILE_000000003531137',
        'date': '2018-06-13', 'label': '7회 전국동시지방선거',
        'schema': 'local',
    },
    ('local', 8): {
        'atch': 'FILE_000000003157459',
        'date': '2022-06-01', 'label': '8회 전국동시지방선거',
        'schema': 'local',
    },
}

UA = "Mozilla/5.0 (vote-via-data scraper; +https://polis.ysw.kr)"


def download_csv(type_: str, n: int) -> Path:
    meta = META.get((type_, n))
    if not meta or not meta.get('atch'):
        raise SystemExit(f"atchFileId 미등록: ({type_}, {n}). META 테이블에 추가 필요.")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{type_}_{n}.csv"
    if out.exists() and out.stat().st_size > 1000:
        print(f'  cached: {out.name}', file=sys.stderr)
        return out
    url = DOWNLOAD_URL.format(atch=meta['atch'])
    print(f'  downloading {url}', file=sys.stderr)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        out.write_bytes(resp.read())
    print(f'  saved {out.name} ({out.stat().st_size:,} bytes)', file=sys.stderr)
    return out


NON_CANDIDATE = {
    '선거인수', '투표수', '무효투표수', '무효 투표수', '기권수', '기권자수',
    '계', '합계', '재투표수',
}

# 시도명 정규화 — 옛 이름·약어 → 현행 (hex 기준)
SIDO_ALIAS = {
    # 옛 이름
    '강원도': '강원특별자치도',
    '전라북도': '전북특별자치도',
    # 약어 (옛 CSV)
    '서울': '서울특별시', '부산': '부산광역시', '대구': '대구광역시',
    '인천': '인천광역시', '광주': '광주광역시', '대전': '대전광역시',
    '울산': '울산광역시', '세종': '세종특별자치시',
    '경기': '경기도', '강원': '강원특별자치도',
    '충북': '충청북도', '충남': '충청남도',
    '전북': '전북특별자치도', '전남': '전라남도',
    '경북': '경상북도', '경남': '경상남도', '제주': '제주특별자치도',
}

# CSV의 시군구명 → hex(sigungu_hex.json) 시군구명 정규화.
# - 통합·분할 시군구 (부천 3구 → 부천시 통합 hex)
# - 행정구역 개편 후 옛 이름과 동기화 (마산·진해·창원 → 창원시)
# - 선거구 분할 ("화성시갑" → 화성시)
# 키는 (시도, 옛이름), 값은 현재 hex 시군구명 (또는 옮길 시도까지 바뀌면 (새시도, 새이름) tuple)
SIGUNGU_ALIAS: dict = {
    # 통합 세종시
    ('세종특별자치시', '세종특별자치시'): '세종시',
    # 부천 3구 → 부천시
    ('경기도', '부천시소사구'): '부천시',
    ('경기도', '부천시오정구'): '부천시',
    ('경기도', '부천시원미구'): '부천시',
    # 선거구 분할
    ('경기도', '화성시갑'): '화성시',
    ('경기도', '화성시을'): '화성시',
    ('경기도', '화성시병'): '화성시',
    # 인천 미추홀구 (2018 개명) - 결과 csv가 신구 어느 쪽이든 hex(남구)로
    ('인천광역시', '미추홀구'): '남구',
    # 2010 통합 창원시 — 옛 마산·진해·창원 → 통합 창원시의 해당 구
    ('경상남도', '마산시'):   '창원시마산합포구',
    ('경상남도', '진해시'):   '창원시진해구',
    ('경상남도', '창원시'):   '창원시의창구',
    # 2008 천안 분리: 옛 통합 천안시 → 동남구 (서북구는 broadcast 별도 처리)
    ('충청남도', '천안시'):   '천안시동남구',
    # 청주시 (옛 통합) → 상당구. 통합 청주시 + 청원군은 broadcast로 4구 다 채우는 게 정확하지만 일단 single mapping
    ('충청북도', '청주시'):   '청주시상당구',
    # 2012 연기군 → 세종시 (시도가 바뀌므로 시도까지 변경)
    ('충청남도', '연기군'): ('세종특별자치시', '세종시'),
    # 2014 청원군 → 청주시 흡수 — hex엔 청주시 4개 구. 통째로 청원/주변 흡수했으니 청원군→청주시청원구
    ('충청북도', '청원군'): '청주시청원구',
    # 2012 당진군 → 당진시
    ('충청남도', '당진군'): '당진시',
    # 2023 군위군 → 대구 편입
    ('경상북도', '군위군'): ('대구광역시', '군위군'),
    # 2013 여주군 → 여주시
    ('경기도', '여주군'): '여주시',
    # 2003 고양 일산구 → 일산동·서구 (single mapping)
    ('경기도', '고양시일산구'): '고양시일산동구',
    # 2003 양주군 → 양주시
    ('경기도', '양주군'): '양주시',
    # 2003 포천군 → 포천시
    ('경기도', '포천군'): '포천시',
    # 옛 용인시 (분구 전) → 처인구 (중심)
    ('경기도', '용인시'): '용인시처인구',
    # 2006 제주: 4개 행정시(제주시·서귀포시·북제주군·남제주군) → 2개 (제주시·서귀포시)
    ('제주특별자치도', '북제주군'): '제주시',
    ('제주특별자치도', '남제주군'): '서귀포시',
}


def parse_candidate(s: str) -> tuple[str, str] | None:
    """후보자 컬럼에서 (정당, 이름) 추출.
    "더불어민주당 이재명" → ('더불어민주당', '이재명')
    "무소속 송진호" → ('무소속', '송진호')
    헤더값(선거인수·투표수·무효 투표수·기권자수 등)은 None.
    """
    s = s.strip()
    if not s or s in NON_CANDIDATE:
        return None
    # 정당명에 공백 가능 ("새로운 미래"). 끝 2~4글자가 후보명, 그 앞이 정당명.
    m = re.match(r'^(.+?)\s+([가-힣]{2,4})$', s)
    if m:
        party, name = m.group(1).strip(), m.group(2).strip()
        # "무효 투표수" 같은 행 한 번 더 거름
        if name in NON_CANDIDATE or party in NON_CANDIDATE:
            return None
        return party, name
    return ('무소속', s)


def detect_encoding(path: Path) -> str:
    with path.open('rb') as f:
        b = f.read(4096)
    if b.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'
    try:
        b.decode('cp949')
        return 'cp949'
    except UnicodeDecodeError:
        return 'utf-8'


def aggregate_sigungu(csv_path: Path):
    """CSV → 시군구 단위 집계 결과 dict."""
    import csv
    sigungu_rows = defaultdict(lambda: {
        'sido': '', 'name': '',
        'electors': 0,
        'voted': 0,
        'invalid': 0,
        'candidates': defaultdict(int),
    })
    national = {
        'electors': 0, 'voted': 0, 'invalid': 0,
        'candidates': defaultdict(int),
    }
    enc = detect_encoding(csv_path)
    with csv_path.open('r', encoding=enc) as f:
        rd = csv.DictReader(f)
        # 컬럼명이 회차마다 달라 — '후보자' (대선) / '정당' (비례총선) / '선거구명' (지역구총선)
        # 단위 컬럼도 '구시군명' / '선거구명'
        fields = rd.fieldnames or []
        cand_col = '후보자' if '후보자' in fields else ('정당' if '정당' in fields else '후보자')
        unit_col = '구시군명' if '구시군명' in fields else ('선거구명' if '선거구명' in fields else '구시군명')
        is_party_only = (cand_col == '정당')
        for row in rd:
            sido = (row.get('시도명') or '').strip()
            sgg  = (row.get(unit_col) or '').strip()
            emd  = (row.get('읍면동명') or row.get('법정읍면동명') or '').strip()
            cand = (row.get(cand_col) or '').strip()
            try:
                vote = int((row.get('득표수') or '0').replace(',', ''))
            except ValueError:
                vote = 0
            if not sido or not sgg:
                continue
            # "합계"행은 시군구 자체 합산 — 중복이라 스킵 (읍면동별 합산이 진실)
            if emd == '합계':
                continue
            # 시도 alias (강원도·강원 → 강원특별자치도 등)
            sido = SIDO_ALIAS.get(sido, sido)
            # 시군구명 정규화: "고성군(강원)" → "고성군" 같은 disambiguation 제거
            sgg = re.sub(r'\([^)]*\)$', '', sgg).strip()
            # 시군구 alias — 시도까지 바뀌는 경우 tuple, 아니면 str
            alias = SIGUNGU_ALIAS.get((sido, sgg))
            if isinstance(alias, tuple):
                sido, sgg = alias
            elif isinstance(alias, str):
                sgg = alias
            key = (sido, sgg)
            r = sigungu_rows[key]
            r['sido'] = sido; r['name'] = sgg
            if cand == '선거인수':
                r['electors'] += vote
                national['electors'] += vote
            elif cand == '투표수':
                r['voted'] += vote
                national['voted'] += vote
            elif cand in ('무효 투표수', '무효투표수'):
                r['invalid'] += vote
                national['invalid'] += vote
            elif cand in NON_CANDIDATE:
                continue
            else:
                if is_party_only:
                    # 비례대표 — 후보자 컬럼이 정당명만
                    if cand in NON_CANDIDATE: continue
                    pc = (cand, '비례')
                else:
                    pc = parse_candidate(cand)
                if not pc: continue
                r['candidates'][pc] += vote
                national['candidates'][pc] += vote
    return sigungu_rows, national


def cands_with_pct(cdict, total_valid):
    out = []
    for (party, name), votes in sorted(cdict.items(), key=lambda x: -x[1]):
        pct = (votes / total_valid * 100) if total_valid else 0
        out.append({'name': name, 'party': party, 'votes': votes, 'pct': round(pct, 2)})
    return out


def sigungu_dict_to_list(sg_rows: dict) -> list:
    out = []
    for (sido, name), r in sorted(sg_rows.items()):
        # 시도·시군구 alias 한 번 더 (xlsx parser가 통과시킨 경우 대비)
        sido2 = SIDO_ALIAS.get(sido, sido)
        sgg2 = re.sub(r'\([^)]*\)$', '', name).strip()
        alias = SIGUNGU_ALIAS.get((sido2, sgg2))
        if isinstance(alias, tuple):
            sido2, sgg2 = alias
        elif isinstance(alias, str):
            sgg2 = alias
        valid = sum(r['candidates'].values())
        turnout = (r['voted'] / r['electors'] * 100) if r['electors'] else 0
        out.append({
            'sido': sido2, 'name': sgg2,
            'electors': r['electors'], 'voted': r['voted'],
            'invalid': r.get('invalid', 0),
            'turnout': round(turnout, 2),
            'candidates': cands_with_pct(r['candidates'], valid),
        })
    return out


def build_result_csv(type_: str, n: int):
    """대선·총선 등 단일 CSV 회차 처리."""
    meta = META[(type_, n)]
    csv_path = download_csv(type_, n)
    sg_rows, nat = aggregate_sigungu(csv_path)

    nat_valid = sum(nat['candidates'].values())
    nat_turnout = (nat['voted'] / nat['electors'] * 100) if nat['electors'] else 0
    national_out = {
        'electors': nat['electors'],
        'voted': nat['voted'],
        'invalid': nat['invalid'],
        'turnout': round(nat_turnout, 2),
        'candidates': cands_with_pct(nat['candidates'], nat_valid),
    }

    return {
        '_meta': {
            'type': type_, 'n': n,
            'date': meta['date'], 'label': meta['label'],
            'source': 'data.go.kr (중앙선거관리위원회 개표결과)',
            'source_atch': meta['atch'],
        },
        'national': national_out,
        'sigungu': sigungu_dict_to_list(sg_rows),
    }


def build_result_local(n: int):
    """지선 xlsx 처리 — 광역단체장·기초단체장·교육감 3종."""
    from parse_local_xlsx import parse_all
    meta = META[('local', n)]
    xlsx_path = download_csv('local', n)
    offices = parse_all(xlsx_path)

    offices_out = {}
    for office, sg_rows in offices.items():
        if not sg_rows:
            continue
        # 합산 후보 (전국 단위) — 시도지사·교육감은 시도별 다른 선거이라 national 합산 의미 모호하지만
        # 광역단체장 1위 등 표시 위해 합산
        national_cands = defaultdict(int)
        nat_electors = 0; nat_voted = 0
        for (sido, name), r in sg_rows.items():
            nat_electors += r['electors']
            nat_voted += r['voted']
            for cand, v in r['candidates'].items():
                national_cands[cand] += v
        nat_valid = sum(national_cands.values())
        offices_out[office] = {
            'national': {
                'electors': nat_electors, 'voted': nat_voted,
                'turnout': round(nat_voted / nat_electors * 100, 2) if nat_electors else 0,
                'candidates': cands_with_pct(national_cands, nat_valid),
            },
            'sigungu': sigungu_dict_to_list(sg_rows),
        }

    return {
        '_meta': {
            'type': 'local', 'n': n,
            'date': meta['date'], 'label': meta['label'],
            'source': 'data.go.kr (중앙선거관리위원회 개표결과)',
            'source_atch': meta['atch'],
        },
        'offices': offices_out,
    }


def build_result(type_: str, n: int):
    if type_ == 'local':
        return build_result_local(n)
    return build_result_csv(type_, n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--type', choices=['presidential', 'national_assembly', 'local'])
    ap.add_argument('--n', type=int)
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    targets = []
    if args.all:
        targets = [k for k, v in META.items() if v.get('atch')]
    elif args.type and args.n:
        targets = [(args.type, args.n)]
    else:
        ap.error('--all or (--type --n) required')

    for type_, n in targets:
        print(f'== {type_} {n} ==', file=sys.stderr)
        result = build_result(type_, n)
        out_path = OUT_DIR / f"{type_}_{n}.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        if 'sigungu' in result:
            n_sg = len(result['sigungu'])
            print(f'  → {out_path.relative_to(ROOT)} ({n_sg} 시군구)', file=sys.stderr)
        elif 'offices' in result:
            counts = {k: len(v.get('sigungu', [])) for k, v in result['offices'].items()}
            print(f'  → {out_path.relative_to(ROOT)} (offices: {counts})', file=sys.stderr)

    # 매니페스트 생성/업데이트 — 데이터 있는 회차 목록
    manifest = {'presidential': [], 'national_assembly': [], 'local': []}
    for f in OUT_DIR.glob('*_*.json'):
        m = re.match(r'(presidential|national_assembly|local)_(\d+)\.json', f.name)
        if m:
            manifest[m.group(1)].append(int(m.group(2)))
    for k in manifest:
        manifest[k].sort()
    (OUT_DIR / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'manifest: {manifest}', file=sys.stderr)


if __name__ == '__main__':
    main()
