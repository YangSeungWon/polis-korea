"""지선 xlsx 파서 — 광역단체장·기초단체장·교육감 추출.

지선 결과 xlsx 구조:
  sheet 8개 (시도지사, 구시군의장, 시도의원, 구시군의원, 광역비례, 기초비례, 교육감, 교육의원)
  각 sheet:
    row 0: 컬럼 헤더 ('선거구명'/'시도명', '구시군명', '읍면동명', '구분', '선거인수', '투표수', '후보자별 득표수', ...)
    row 1: 후보 번호 ('후보1','후보2',...) 또는 정당 번호
    row 2+: 데이터. 시도 블록 시작 행은 후보자 이름(정당\n이름), 그 다음 행부터 시군구별 데이터.

데이터 행 종류 (col '구분' or col '읍면동명' 기준):
  - '합계'    → 시군구 합계 (시군구 단위 사용)
  - '거소투표'/'관외사전투표'/'국외부재자' → 특수 투표 (개별 시군구로 별도 집계 안 함)
  - 읍면동명 + 소계/관내사전투표/선거일투표 → 더 세분화
"""
from __future__ import annotations
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd


def parse_candidate_cell(val) -> tuple[str, str] | None:
    """'정당\n이름' (7회는 '정당_x000D_\n이름') → (party, name). 빈 셀·숫자만·구분자만 → None."""
    if pd.isna(val) or val is None:
        return None
    s = str(val).replace('_x000D_', '').strip()
    if not s or s == '\n':
        return None
    # 숫자만 (시도 합계 등 데이터 행이 잘못 들어왔을 때 거부)
    if re.fullmatch(r'[\d,.\s]+', s):
        return None
    parts = s.split('\n')
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    if len(parts) == 1:
        # 정당 미표기 — 무소속 가정
        return '무소속', parts[0].strip()
    # 3개 이상 = 정당명에 줄바꿈 (드물) — 마지막을 이름으로
    return '\n'.join(parts[:-1]).strip(), parts[-1].strip()


def _to_int(v) -> int:
    if pd.isna(v) or v is None:
        return 0
    try:
        return int(str(v).replace(',', '').strip())
    except (ValueError, TypeError):
        return 0


def _find_col(headers, *names):
    """헤더 행에서 가장 먼저 일치하는 컬럼 인덱스. names = 후보 이름 리스트."""
    for n in names:
        for i, h in enumerate(headers):
            if h is None or (isinstance(h, float) and pd.isna(h)):
                continue
            if str(h).strip() == n:
                return i
    return -1


def parse_election_sheet(xlsx_path: Path, sheet_name: str, **_):
    """한 sheet에서 시군구별 결과 추출. 컬럼 위치는 헤더 행에서 자동 detect.

    return:
      sigungu_data: {(sido, sgg): {'electors','voted','candidates': {(party,name): votes}, 'sido','name'}}
    """
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None)
    sigungu_data = defaultdict(lambda: {
        'sido': '', 'name': '',
        'electors': 0, 'voted': 0,
        'candidates': defaultdict(int),
    })

    n_cols = df.shape[1]
    head = df.iloc[0].tolist()

    # 컬럼 자동 감지 (회차마다 컬럼명 다름)
    # 시도지사: 5~6회 '시도', 7회 '시도명', 8회 '선거구명'(데이터는 시도)
    # 구시군의장: 5~6회 '시도'+'선거구', 7회 '시도명'(과 별개로 col에 '시도'도 있음), 8회 '시도명'+'선거구(구시군)'
    sido_col = _find_col(head, '시도명', '시도', '선거구명')
    sgg_col  = _find_col(head, '구시군명', '구시군')
    emd_col  = _find_col(head, '읍면동명', '법정읍면동명', '읍면동')
    gubun_col = _find_col(head, '구분')
    electors_col = _find_col(head, '선거인수')
    voted_col = _find_col(head, '투표수')
    cand_col_start = _find_col(head, '후보자별 득표수', '정당별 득표수')

    try:
        gye_idx = head.index('계')
    except ValueError:
        gye_idx = n_cols - 3
    cand_col_end = gye_idx

    if min(sido_col, sgg_col, emd_col, electors_col, voted_col, cand_col_start) < 0:
        print(f'  {sheet_name}: 컬럼 detect 실패 (sido={sido_col} sgg={sgg_col} emd={emd_col} '
              f'el={electors_col} vt={voted_col} cs={cand_col_start})', file=sys.stderr)
        return sigungu_data

    SIGUNGU_TOTAL = {'합계', '계'}
    META_VALS = {'선거인수', '투표수', '투표인수', '무효투표수', '무효 투표수',
                 '기권수', '기권자수', '합계', '계', '후보1', '후보2', '후보3',
                 '후보4', '후보5', '후보6', '후보7', '후보8', '후보9', '후보10'}
    current_candidates: list[tuple[str, str] | None] = []
    for idx, row in df.iterrows():
        # header row만 skip. 7회는 row 1이 후보 행. 5·6·8회는 row 1이 '후보N' slot
        # 메타라 META_VALS detection이 skip 처리.
        if idx < 1:
            continue
        col_sido = row.iloc[sido_col]
        col_sgg = row.iloc[sgg_col]
        col_emd = row.iloc[emd_col]

        # 후보 이름 행 detection (회차마다 sheet 구조 달라 robust하게):
        #  - cand_col_start 셀에 '\n' or '_x000D_' (정당\n이름 형식) → 무조건 후보 행
        #  - 또는 emd 비어있고 cand 셀이 의미있는 문자열 (메타값/숫자 아님)
        first_cand_val = row.iloc[cand_col_start] if cand_col_start < n_cols else None
        if not pd.isna(first_cand_val):
            s = str(first_cand_val).replace('_x000D_', '').strip()
            # 숫자만 (시도 합계 데이터)는 후보 행 아님
            is_numeric = bool(re.fullmatch(r'[\d,.\s]+', s)) if s else False
            is_cand_row = False
            if '\n' in s:
                is_cand_row = True
            elif pd.isna(col_emd) and s and s not in META_VALS and not is_numeric:
                is_cand_row = True
            if is_cand_row:
                new_cands = []
                for c in range(cand_col_start, cand_col_end):
                    new_cands.append(parse_candidate_cell(row.iloc[c]))
                current_candidates = new_cands
                continue

        # 시군구 합계 행: emd 컬럼에 '합계'(5/6/8회) 또는 '계'(7회)
        if not pd.isna(col_emd) and str(col_emd).strip() in SIGUNGU_TOTAL:
            col_sido = row.iloc[sido_col]
            sido = str(col_sido).strip() if not pd.isna(col_sido) else ''
            sgg  = str(col_sgg).strip() if not pd.isna(col_sgg) else ''
            if not sido or not sgg:
                continue
            # 7회 시도 단위 합계 (col 2 = '합계')는 시군구 단위 데이터 아님 → emd_col이 sido_col보다 오른쪽인 경우만 시군구 단위
            # 7회 시도 합계 행: col 2 = '합계'. 시도 단위라 sgg 비어있을 텐데, col 3 (구시군) nan이라 위에서 continue됨.
            electors = _to_int(row.iloc[electors_col])
            voted = _to_int(row.iloc[voted_col])
            # 합리적 데이터인지 확인 (선거인수 > 0)
            if electors <= 0:
                continue
            key = (sido, sgg)
            r = sigungu_data[key]
            r['sido'] = sido; r['name'] = sgg
            r['electors'] = electors; r['voted'] = voted
            for i, cand in enumerate(current_candidates):
                if not cand: continue
                col_idx = cand_col_start + i
                if col_idx >= cand_col_end: break
                v = _to_int(row.iloc[col_idx])
                if v:
                    r['candidates'][cand] += v

    return sigungu_data


# office → sheet 이름 (지선 회차마다 약간 다를 수 있음)
SHEET_MAP = {
    '광역단체장': '시·도지사',
    '기초단체장': '구·시·군의장',
    '교육감':     '교육감',
}


def parse_all(xlsx_path: Path) -> dict:
    """3가지 직(광역·기초·교육감) 파싱."""
    out = {}
    for office, sheet in SHEET_MAP.items():
        try:
            data = parse_election_sheet(xlsx_path, sheet)
            out[office] = data
            print(f'  {office}: {len(data)} 시군구', file=sys.stderr)
        except Exception as e:
            print(f'  {office} parse 실패: {e}', file=sys.stderr)
            out[office] = {}
    return out


ELECTION_META = {
    5: {"date": "2010-06-02", "label": "5회 전국동시지방선거"},
    6: {"date": "2014-06-04", "label": "6회 전국동시지방선거"},
    7: {"date": "2018-06-13", "label": "7회 전국동시지방선거"},
    8: {"date": "2022-06-01", "label": "8회 전국동시지방선거"},
}


def to_office_payload(office_data: dict) -> dict:
    """parse 결과 dict → JSON friendly (sigungu list + national 합산)."""
    sigungu_list = []
    nat_cands = defaultdict(int)
    nat_electors = 0
    nat_voted = 0
    for (sido, sgg), d in office_data.items():
        cands = []
        total_votes = sum(d['candidates'].values())
        for (party, name), votes in sorted(d['candidates'].items(), key=lambda x: -x[1]):
            cands.append({
                "name": name,
                "party": party,
                "votes": int(votes),
                "pct": round(votes / total_votes * 100, 2) if total_votes else 0.0,
            })
            nat_cands[(party, name)] += int(votes)
        sigungu_list.append({
            "sido": sido,
            "name": sgg,
            "electors": int(d['electors']),
            "voted": int(d['voted']),
            "turnout": round(d['voted'] / d['electors'] * 100, 2) if d['electors'] else 0.0,
            "candidates": cands,
        })
        nat_electors += int(d['electors'])
        nat_voted += int(d['voted'])

    nat_total = sum(nat_cands.values())
    nat_candidates = []
    for (party, name), votes in sorted(nat_cands.items(), key=lambda x: -x[1]):
        nat_candidates.append({
            "name": name,
            "party": party,
            "votes": int(votes),
            "pct": round(votes / nat_total * 100, 2) if nat_total else 0.0,
        })
    return {
        "national": {
            "electors": nat_electors,
            "voted": nat_voted,
            "turnout": round(nat_voted / nat_electors * 100, 2) if nat_electors else 0.0,
            "candidates": nat_candidates,
        },
        "sigungu": sigungu_list,
    }


def main():
    import json
    ROOT = Path(__file__).resolve().parents[2]
    out_dir = ROOT / 'data/results'
    for n in [5, 6, 7, 8]:
        src = ROOT / f'data/raw/results_csv/local_{n}.csv'
        if not src.exists():
            print(f'skip {n}: {src} 없음', file=sys.stderr)
            continue
        print(f'\n=== local_{n} ===', file=sys.stderr)
        try:
            parsed = parse_all(src)
        except Exception as e:
            print(f'  parse_all 실패: {e}', file=sys.stderr)
            continue
        meta = ELECTION_META[n]
        payload = {
            "_meta": {
                "type": "local",
                "n": n,
                "date": meta["date"],
                "label": meta["label"],
                "source": "info.nec.go.kr 선거통계시스템",
            },
            "offices": {office: to_office_payload(data) for office, data in parsed.items() if data},
        }
        out_path = out_dir / f'local_{n}.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        n_offices = len(payload['offices'])
        n_sigungu = sum(len(v['sigungu']) for v in payload['offices'].values())
        print(f'  → {out_path.relative_to(ROOT)} ({n_offices} offices, {n_sigungu} sigungu records)', file=sys.stderr)


if __name__ == '__main__':
    main()
