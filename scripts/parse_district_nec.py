"""NEC data.nec.go.kr 통합 xlsx → 지역구별 결과.

xlsx (sheet '지역구'):
  row 0: 컬럼 헤더 ['시도', '선거구', '읍면동', '투표구', '선거인수', '투표수',
                  '후보자별 득표수', NaN, NaN, ..., '계', '무효투표수', '기권수']
  지역구 블록:
    row a: 시도, 선거구 + 후보 슬롯에 정당명
    row a+1: 시도, 선거구 + 후보 슬롯에 후보자 이름
    row a+2: 시도, 선거구, '합계', ... 합계 행
    row a+3+: 거소·선상·관외사전·읍면동 등 세부

지역구별 합계 (row a+2) 행에서 votes 추출.

사용:
  .venv/bin/python scripts/parse_district_nec.py 19
  .venv/bin/python scripts/parse_district_nec.py 21
  .venv/bin/python scripts/parse_district_nec.py --all
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data/raw/nec_district"
OUT_DIR = ROOT / "data/results"
GEO_DIR = ROOT / "data/geo"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _geo import SIDO_NAME_CANONICAL  # noqa: E402

# data.nec.go.kr attachFileId mapping
ATTACH = {19: 9, 20: 7, 21: 1, 22: 8}
DATE = {19: '2012-04-11', 20: '2016-04-13', 21: '2020-04-15', 22: '2024-04-10'}

NON_CANDIDATE = {'선거인수', '투표수', '무효투표수', '무효 투표수', '기권수', '기권자수', '계', '합계'}


def download_nec(n: int) -> Path:
    out = RAW_DIR / f"n{n}_district_nec.xlsx"
    if out.exists() and out.stat().st_size > 100000:
        return out
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(accept_downloads=True)
        page.goto('http://data.nec.go.kr/open-data/file.do?dataId=9', wait_until='networkidle')
        page.wait_for_timeout(2000)
        with page.expect_download() as dl_info:
            page.evaluate(f'document.querySelector("a[href*=\\"attachFileId={ATTACH[n]}\\"]").click()')
        dl = dl_info.value
        dl.save_as(str(out))
        browser.close()
    return out


def _to_int(v) -> int:
    if pd.isna(v) or v is None: return 0
    try:
        return int(str(v).replace(',', '').strip())
    except (ValueError, TypeError):
        return 0


def parse_district_xlsx(path: Path):
    df = pd.read_excel(path, sheet_name='지역구', header=None)
    n_cols = df.shape[1]
    head = df.iloc[0].tolist()
    # col 위치
    sido_col = head.index('시도') if '시도' in head else 0
    sgg_col = head.index('선거구') if '선거구' in head else 1
    emd_col = head.index('읍면동') if '읍면동' in head else 2
    electors_col = head.index('선거인수') if '선거인수' in head else 4
    voted_col = head.index('투표수') if '투표수' in head else 5
    cand_col_start = head.index('후보자별 득표수') if '후보자별 득표수' in head else 6
    # cand end
    cand_col_end = n_cols
    for i in range(cand_col_start, n_cols):
        h = head[i]
        if isinstance(h, str) and h.strip() in {'계', '무효투표수', '기권수', '권역'}:
            cand_col_end = i; break

    districts = defaultdict(lambda: {
        'sido': '', 'name': '',
        'electors': 0, 'voted': 0, 'invalid': 0,
        'candidates': defaultdict(int),
    })
    current_sido = None
    current_sgg = None
    parties = [None] * (cand_col_end - cand_col_start)
    names = [None] * (cand_col_end - cand_col_start)
    state = 'init'  # init → parties → names → totals

    for idx in range(1, df.shape[0]):
        row = df.iloc[idx]
        sido = row.iloc[sido_col] if sido_col < n_cols else None
        sgg = row.iloc[sgg_col] if sgg_col < n_cols else None
        emd = row.iloc[emd_col] if emd_col < n_cols else None

        sido_str = str(sido).strip() if not pd.isna(sido) else ''
        sgg_str = str(sgg).strip() if not pd.isna(sgg) else ''
        emd_str = str(emd).strip() if not pd.isna(emd) else ''

        if not sido_str or not sgg_str:
            continue

        # 시도명 정규화 (옛 '강원도' → '강원특별자치도' 등)
        sido_str = SIDO_NAME_CANONICAL.get(sido_str, sido_str)

        # 새 (시도, 선거구) 블록 시작 — 정당 행
        if (sido_str, sgg_str) != (current_sido, current_sgg) and not emd_str:
            current_sido = sido_str
            current_sgg = sgg_str
            # 이 행이 정당 행
            for i, c in enumerate(range(cand_col_start, cand_col_end)):
                val = row.iloc[c] if c < n_cols else None
                if pd.isna(val):
                    parties[i] = None
                else:
                    s = str(val).strip().replace('_x000D_', '').replace('\n', '')
                    parties[i] = s if s and s not in NON_CANDIDATE else None
            state = 'expecting_names'
            continue

        # 정당 행 다음 — 후보 이름 행
        if state == 'expecting_names' and not emd_str:
            for i, c in enumerate(range(cand_col_start, cand_col_end)):
                val = row.iloc[c] if c < n_cols else None
                if pd.isna(val):
                    names[i] = None
                else:
                    s = str(val).strip().replace('_x000D_', '').replace('\n', '')
                    names[i] = s if s and s not in NON_CANDIDATE else None
            state = 'totals'
            continue

        # 합계 행
        if emd_str == '합계':
            key = (current_sido, current_sgg)
            r = districts[key]
            r['sido'] = current_sido; r['name'] = current_sgg
            r['electors'] = _to_int(row.iloc[electors_col])
            r['voted'] = _to_int(row.iloc[voted_col])
            for i, c in enumerate(range(cand_col_start, cand_col_end)):
                party = parties[i]; name = names[i]
                if not party or not name: continue
                v = _to_int(row.iloc[c]) if c < n_cols else 0
                if v:
                    r['candidates'][(party, name)] += v
            # 합계 처리 후엔 detail rows 처리 안 함
            state = 'after_total'
            continue

        # 그 외 행 (거소·선상·관외사전·읍면동 등) — 이미 합계로 처리

    return districts


def cands_with_pct(cdict):
    total = sum(cdict.values())
    out = []
    for (party, name), votes in sorted(cdict.items(), key=lambda x: -x[1]):
        pct = (votes / total * 100) if total else 0
        out.append({'name': name, 'party': party, 'votes': votes, 'pct': round(pct, 2)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('n', type=int, nargs='?')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()
    targets = list(ATTACH.keys()) if args.all else [args.n]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GEO_DIR.mkdir(parents=True, exist_ok=True)

    for n in targets:
        if n is None: continue
        print(f'== {n}대 ==', file=sys.stderr)
        path = download_nec(n)
        print(f'  src: {path.name} ({path.stat().st_size:,} bytes)', file=sys.stderr)
        districts = parse_district_xlsx(path)
        print(f'  지역구 {len(districts)}', file=sys.stderr)

        out_list = []
        centroid_meta = []
        for (sido, name), r in sorted(districts.items()):
            cands = cands_with_pct(r['candidates'])
            winner = cands[0] if cands else None
            turnout = (r['voted'] / r['electors'] * 100) if r['electors'] else 0
            out_list.append({
                'sido': sido, 'name': name,
                'winner': winner['name'] if winner else None,
                'winner_party': winner['party'] if winner else None,
                'electors': r['electors'], 'voted': r['voted'],
                'invalid': r['invalid'],
                'turnout': round(turnout, 2),
                'candidates': cands,
            })
            centroid_meta.append({'sido': sido, 'name': name})

        # 기존 비례 JSON 머지 (없으면 새로 생성)
        out_path = OUT_DIR / f"national_assembly_{n}.json"
        if out_path.exists():
            existing = json.loads(out_path.read_text(encoding='utf-8'))
        else:
            existing = {
                '_meta': {'type': 'national_assembly', 'n': n,
                          'date': DATE[n], 'label': f'{n}대 국회의원선거'},
                'national': None, 'sigungu': [],
            }
        existing['district'] = out_list
        existing['_meta']['has_district'] = True
        out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  → {out_path.name} (district {len(out_list)})', file=sys.stderr)

        centroid_path = GEO_DIR / f'district_{n}_centroid.json'
        centroid_path.write_text(json.dumps(centroid_meta, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  → {centroid_path.name}', file=sys.stderr)

    # manifest 재생성
    import re as _re
    manifest = {'presidential': [], 'national_assembly': [], 'local': []}
    for f in OUT_DIR.glob('*_*.json'):
        m = _re.match(r'(presidential|national_assembly|local)_(\d+)\.json', f.name)
        if m: manifest[m.group(1)].append(int(m.group(2)))
    for k in manifest: manifest[k] = sorted(set(manifest[k]))
    (OUT_DIR / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
