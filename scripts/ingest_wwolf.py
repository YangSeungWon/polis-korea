"""WWolf/korea-election TSV → data/results/*.json 변환.

WWolf 데이터: https://github.com/WWolf/korea-election/tree/master/dataset
- 2004·2006·2008: long format (시군구 단위, 정당 컬럼)
- 2012·2016 비례: wide format (시군구·읍면동 × 정당 컬럼)
- 2012·2017 대선: wide format (후보 이름 컬럼)
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "wwolf"
OUT = ROOT / "data" / "results"
BASE = "https://raw.githubusercontent.com/WWolf/korea-election/master/dataset/"

# scrape_results.py 의 alias 재사용
sys.path.insert(0, str(Path(__file__).parent))
from scrape_results import SIDO_ALIAS, SIGUNGU_ALIAS  # noqa

# 18대 대선 후보 → 정당
CAND_PARTY_18P = {
    '박근혜': '새누리당',
    '문재인': '민주통합당',
    '박종선': '무소속',
    '김소연': '무소속',
    '강지원': '무소속',
    '김순자': '무소속',
}

# WWolf 회차 메타
TARGETS = {
    ('national_assembly', 17, 'prop'): {
        'file': '2004-prop-sgg.tsv', 'format': 'long',
        'date': '2004-04-15', 'label': '17대 국회의원선거 (비례대표)',
    },
    # 4회 지선 (2006) 광역 비례는 WWolf에 있지만 광역단체장과 다른 직위.
    # offices schema와 호환 안 되므로 비활성. NEC 별도 광역단체장 데이터 필요.
    # ('local', 4, 'prop'): {
    #     'file': '2006-prop-sgg.tsv', 'format': 'long',
    #     'date': '2006-05-31', 'label': '4회 전국동시지방선거 (광역 비례)',
    # },
    ('national_assembly', 18, 'prop'): {
        'file': '2008-prop-sgg.tsv', 'format': 'long',
        'date': '2008-04-09', 'label': '18대 국회의원선거 (비례대표)',
    },
    ('national_assembly', 19, 'prop'): {
        'file': '2012general_prop_full.tsv', 'format': 'wide_party',
        'date': '2012-04-11', 'label': '19대 국회의원선거 (비례대표)',
    },
    ('presidential', 18): {
        'file': '2012presidential_full.tsv', 'format': 'wide_cand',
        'cand_party': CAND_PARTY_18P,
        'date': '2012-12-19', 'label': '18대 대통령선거',
    },
    ('national_assembly', 20, 'prop'): {
        'file': '2016general_prop_emd.tsv', 'format': 'wide_party',
        'date': '2016-04-13', 'label': '20대 국회의원선거 (비례대표)',
    },
    # 20대 대선 (2022)은 vuski 데이터셋에서 별도 처리 (build_one에서 분기)
    ('presidential', 20): {
        'file': None, 'format': 'vuski_20p',
        'date': '2022-03-09', 'label': '20대 대통령선거',
    },
    ('presidential', 19): {
        'file': '2017presidential_sgg.tsv', 'format': 'wide_party',
        # 19대 대선 wide는 정당 컬럼명. 후보명은 PARTY_CAND_19P로 후처리.
        'date': '2017-05-09', 'label': '19대 대통령선거',
        'party_cand': {
            '더불어민주당': '문재인',
            '자유한국당': '홍준표',
            '국민의당': '안철수',
            '바른정당': '유승민',
            '정의당': '심상정',
            '새누리당': '조원진',
            '경제애국당': '오영국',
            '국민대통합당': '장성민',
            '늘푸른한국당': '이재오',
            '민중연합당': '김선동',
            '한국국민당': '이경희',
            '혹익당': '윤홍식',
            '무소속': '김민찬',
        },
    },
}


def download(fname: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / fname
    if out.exists() and out.stat().st_size > 5000:
        return out
    url = BASE + fname
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    print(f'  fetching {url}', file=sys.stderr)
    with urllib.request.urlopen(req, timeout=60) as r:
        out.write_bytes(r.read())
    return out


def normalize_region(sido: str, sgg: str) -> tuple[str, str]:
    sido = SIDO_ALIAS.get(sido, sido)
    sgg = re.sub(r'\([^)]*\)$', '', sgg).strip()
    alias = SIGUNGU_ALIAS.get((sido, sgg))
    if isinstance(alias, tuple):
        return alias
    if isinstance(alias, str):
        return (sido, alias)
    return (sido, sgg)


def parse_long(path: Path):
    """long format (시군구·정당 행). 컬럼: 광역, 광역코드, 시군구, 선거인수, 투표수, 유효투표수, 무효투표수, 기권수, 정당, 득표수"""
    sigungu_data = defaultdict(lambda: {
        'sido': '', 'name': '', 'electors': 0, 'voted': 0, 'invalid': 0,
        'candidates': defaultdict(int),
    })
    with path.open('r', encoding='utf-8') as f:
        header = f.readline().strip().split('\t')
        idx = {h: i for i, h in enumerate(header)}
        for line in f:
            cols = line.rstrip('\n').split('\t')
            if len(cols) < len(header): continue
            sido = cols[idx['광역']].strip()
            sgg = cols[idx['시군구']].strip()
            sido, sgg = normalize_region(sido, sgg)
            party = cols[idx['정당']].strip()
            def num(k):
                try: return int(cols[idx[k]].replace(',',''))
                except: return 0
            r = sigungu_data[(sido, sgg)]
            r['sido'] = sido; r['name'] = sgg
            r['electors'] = num('선거인수')
            r['voted'] = num('투표수')
            r['invalid'] = num('무효투표수')
            r['candidates'][(party, '비례')] += num('득표수')
    return sigungu_data


def parse_wide(path: Path, cand_party: dict | None = None):
    """wide format. 컬럼: 광역, 시군구, 읍면동(or 투표소), [선거인수, 투표수, ...], 후보/정당N...

    파일에 시군구 합계 행 ('합계'/'계')이 있으면 그것만 사용,
    없으면 (예: 2016 emd-only) 모든 읍면동 row를 시군구별 합산.
    """
    with path.open('r', encoding='utf-8') as f:
        header = f.readline().rstrip('\n').split('\t')
    idx = {h.strip(): i for i, h in enumerate(header)}
    sido_col = idx.get('광역', 0)
    sgg_col = idx.get('시군구', 1)
    emd_col = idx.get('읍면동') if '읍면동' in idx else (idx.get('투표소') if '투표소' in idx else None)
    vote_col = idx.get('투표소') if '투표소' in idx else None

    # 메타 컬럼들 (이외는 후보/정당 컬럼으로 간주)
    META_COLS = {
        '광역', '광역코드', '시군구', '시군구코드', '읍면동', '투표소', '구분',
        '선거인수', '투표수', '투표인수', '기권수', '무효표', '무효투표수',
        '유효투표수', '계', '권역', '비고',
    }
    cand_cols = []
    cand_names = []
    for i, h in enumerate(header):
        h_clean = h.strip()
        if h_clean and h_clean not in META_COLS:
            cand_cols.append(i)
            cand_names.append(h_clean)

    # 1차 패스: '합계'/'계' 시군구 합계 행이 있는지 검사
    sigungu_total_markers = {'합계', '계'}
    has_sigungu_total = False
    with path.open('r', encoding='utf-8') as f:
        f.readline()
        for line in f:
            cols = line.rstrip('\n').split('\t')
            if emd_col is not None and emd_col < len(cols):
                emd = cols[emd_col].strip()
                if emd in sigungu_total_markers:
                    has_sigungu_total = True
                    break

    sigungu_data = defaultdict(lambda: {
        'sido': '', 'name': '', 'electors': 0, 'voted': 0, 'invalid': 0,
        'candidates': defaultdict(int),
    })

    def num_from_cols(cols, key):
        if key not in idx or idx[key] >= len(cols): return 0
        v = cols[idx[key]].strip()
        if not v: return 0
        try: return int(v.replace(',',''))
        except: return 0

    with path.open('r', encoding='utf-8') as f:
        f.readline()
        for line in f:
            cols = line.rstrip('\n').split('\t')
            if len(cols) < len(header) - 5: continue
            sido = cols[sido_col].strip() if sido_col < len(cols) else ''
            sgg = cols[sgg_col].strip() if sgg_col < len(cols) else ''
            if not sido or not sgg: continue
            emd = cols[emd_col].strip() if emd_col is not None and emd_col < len(cols) else ''
            if has_sigungu_total:
                # 합계/계 행만 사용
                if emd not in sigungu_total_markers: continue
            else:
                # 모든 읍면동 합산 — 단 '합계'/'계' 행이 (혹시) 있으면 스킵 (중복 방지)
                if emd in sigungu_total_markers: continue
            sido, sgg = normalize_region(sido, sgg)
            r = sigungu_data[(sido, sgg)]
            r['sido'] = sido; r['name'] = sgg
            r['electors'] += num_from_cols(cols, '선거인수') or num_from_cols(cols, '투표인수') if not has_sigungu_total else (num_from_cols(cols, '선거인수') or num_from_cols(cols, '투표인수'))
            r['voted'] += num_from_cols(cols, '투표수') or num_from_cols(cols, '투표인수') if not has_sigungu_total else (num_from_cols(cols, '투표수') or num_from_cols(cols, '투표인수'))
            r['invalid'] += num_from_cols(cols, '무효투표수') or num_from_cols(cols, '무효표') if not has_sigungu_total else (num_from_cols(cols, '무효투표수') or num_from_cols(cols, '무효표'))
            for i, c in enumerate(cand_cols):
                if c >= len(cols): break
                v = cols[c].strip()
                if not v: continue
                try: vv = int(v.replace(',',''))
                except: continue
                if vv == 0: continue
                cname = cand_names[i]
                if cand_party:
                    party = cand_party.get(cname, '무소속')
                    r['candidates'][(party, cname)] += vv
                else:
                    r['candidates'][(cname, '비례')] += vv
            # 합계 행을 사용 시 += 대신 = 가 자연인데 위는 +=. 합계가 단 하나라 OK.
    return sigungu_data


def cands_with_pct(cdict):
    total = sum(cdict.values())
    out = []
    for (party, name), votes in sorted(cdict.items(), key=lambda x: -x[1]):
        pct = (votes / total * 100) if total else 0
        out.append({'name': name, 'party': party, 'votes': votes, 'pct': round(pct, 2)})
    return out


def sigungu_to_list(sg_data):
    out = []
    for (sido, name), r in sorted(sg_data.items()):
        valid = sum(r['candidates'].values())
        turnout = (r['voted'] / r['electors'] * 100) if r['electors'] else 0
        out.append({
            'sido': sido, 'name': name,
            'electors': r['electors'], 'voted': r['voted'],
            'invalid': r['invalid'],
            'turnout': round(turnout, 2),
            'candidates': cands_with_pct(r['candidates']),
        })
    return out


def aggregate_national(sg_data):
    nat = {'electors': 0, 'voted': 0, 'invalid': 0, 'cands': defaultdict(int)}
    for r in sg_data.values():
        nat['electors'] += r['electors']
        nat['voted'] += r['voted']
        nat['invalid'] += r['invalid']
        for c, v in r['candidates'].items():
            nat['cands'][c] += v
    return {
        'electors': nat['electors'], 'voted': nat['voted'], 'invalid': nat['invalid'],
        'turnout': round(nat['voted']/nat['electors']*100, 2) if nat['electors'] else 0,
        'candidates': cands_with_pct(nat['cands']),
    }


def parse_vuski_20p() -> dict:
    """vuski/presidentialElection2022 data.csv → 시군구 단위 집계."""
    import pandas as pd
    url = 'https://raw.githubusercontent.com/vuski/presidentialElection2022SouthKoreaEmdmap/master/data.csv'
    cache = RAW / 'vuski_20p.csv'
    if not cache.exists() or cache.stat().st_size < 100000:
        RAW.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        cache.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    df = pd.read_csv(cache)
    df['sgg_cd'] = df['code'].astype(str).str[:5]
    # hex code → (sido, name) 매핑
    hex_data = json.loads((ROOT / 'data/geo/sigungu_hex.json').read_text(encoding='utf-8'))
    code_to_region = {h['code']: (h['sido'], h['name']) for h in hex_data}
    sigungu_data = defaultdict(lambda: {
        'sido': '', 'name': '', 'electors': 0, 'voted': 0, 'invalid': 0,
        'candidates': defaultdict(int),
    })
    grouped = df.groupby('sgg_cd').agg({
        'p22lee': 'sum', 'p22yoon': 'sum', 'p22sim': 'sum',
        'p22etc': 'sum', 'p22valid': 'sum',
    })
    for sgg_cd, row in grouped.iterrows():
        region = code_to_region.get(sgg_cd)
        if not region: continue
        sido, name = region
        r = sigungu_data[(sido, name)]
        r['sido'] = sido; r['name'] = name
        # 투표수 ≈ 유효투표수 + 무효표. vuski에 무효표 없으니 voted = valid.
        r['voted'] = int(row['p22valid'])
        r['candidates'][('더불어민주당', '이재명')] += int(row['p22lee'])
        r['candidates'][('국민의힘',   '윤석열')] += int(row['p22yoon'])
        r['candidates'][('정의당',     '심상정')] += int(row['p22sim'])
        if int(row['p22etc']) > 0:
            r['candidates'][('기타',     '기타')] += int(row['p22etc'])
    return sigungu_data


def build_one(key, meta):
    fmt = meta['format']
    if fmt == 'vuski_20p':
        sg = parse_vuski_20p()
        type_ = key[0]; n = key[1]
        out = {
            '_meta': {
                'type': type_, 'n': n,
                'date': meta['date'], 'label': meta['label'],
                'source': 'github.com/vuski/presidentialElection2022SouthKoreaEmdmap',
                'note': '읍면동 단위 합산 — 거소·관외사전·재외투표 미포함',
            },
            'national': aggregate_national(sg),
            'sigungu': sigungu_to_list(sg),
        }
        out_path = OUT / f"{type_}_{n}.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  → {out_path.name} ({len(out["sigungu"])} 시군구, {len(out["national"]["candidates"])} 후보)', file=sys.stderr)
        return

    path = download(meta['file'])
    if fmt == 'long':
        sg = parse_long(path)
    elif fmt == 'wide_party':
        sg = parse_wide(path, cand_party=None)
        # 대선의 경우 정당→후보명 매핑 후처리 (key의 name '비례' 교체)
        party_cand = meta.get('party_cand')
        if party_cand:
            for r in sg.values():
                new = defaultdict(int)
                for (party, name), v in r['candidates'].items():
                    new_name = party_cand.get(party, name)
                    new[(party, new_name)] += v
                r['candidates'] = new
    elif fmt == 'wide_cand':
        sg = parse_wide(path, cand_party=meta.get('cand_party', {}))
    else:
        raise SystemExit(f'unknown format: {fmt}')

    type_ = key[0]; n = key[1]
    out = {
        '_meta': {
            'type': type_, 'n': n,
            'date': meta['date'], 'label': meta['label'],
            'source': 'github.com/WWolf/korea-election',
        },
        'national': aggregate_national(sg),
        'sigungu': sigungu_to_list(sg),
    }
    out_path = OUT / f"{type_}_{n}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'  → {out_path.name} ({len(out["sigungu"])} 시군구, {len(out["national"]["candidates"])} 정당)', file=sys.stderr)


def update_manifest():
    import re as _re
    manifest = {'presidential': [], 'national_assembly': [], 'local': []}
    for f in OUT.glob('*_*.json'):
        m = _re.match(r'(presidential|national_assembly|local)_(\d+)\.json', f.name)
        if m:
            manifest[m.group(1)].append(int(m.group(2)))
    for k in manifest:
        manifest[k] = sorted(set(manifest[k]))
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'manifest: {manifest}', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', help='e.g., presidential_18 or national_assembly_19')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()

    targets = []
    if args.all:
        targets = list(TARGETS.items())
    elif args.key:
        for k, m in TARGETS.items():
            kstr = f'{k[0]}_{k[1]}'
            if kstr == args.key:
                targets = [(k, m)]
                break

    OUT.mkdir(parents=True, exist_ok=True)
    for k, m in targets:
        print(f'== {k} ==', file=sys.stderr)
        try:
            build_one(k, m)
        except Exception as e:
            print(f'  ERROR: {e}', file=sys.stderr)
    update_manifest()


if __name__ == '__main__':
    main()
