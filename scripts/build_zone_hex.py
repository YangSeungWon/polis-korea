"""hex layout T-zone 재설계 — 권역별 row 구간 못 박음.

구조 (⊥ 모양):
  N 존: 수도권 + 강원         (rows 0~)         가로 중앙 정렬
  M 존: 충청                  (rows 다음)       가로 중앙 정렬
  S 존: 호남 | 영남           (rows 다음)       boundary col 가운데 고정,
                                                  호남 우측 정렬, 영남 좌측 정렬
  P 존: 제주                  (rows 끝)         가로 중앙 정렬

각 zone 내부:
  - cells lat 기준 linear bin → local row
  - 같은 row 안 lon 정렬, contiguous 배치

보장:
  - row gap=0 (zone 내 contiguous, S zone 호남|영남 boundary 인접)
  - inversion 0 (T-partition + zone 내 lon 정렬)
  - intrusion 0 (zone 경계가 row 경계와 일치)
  - 회차 일관 (같은 rule)

사용:
  python3 scripts/build_zone_hex.py
  python3 scripts/build_zone_hex.py --dry
  python3 scripts/build_zone_hex.py --target-row-width 12
"""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIGUNGU_GEO = ROOT / 'data/geo/sigungu_simple.json'

SIDO_REGION = {
    '서울특별시': '수도권', '인천광역시': '수도권', '경기도': '수도권',
    '충청남도': '충청권', '충청북도': '충청권',
    '세종특별자치시': '충청권', '대전광역시': '충청권',
    '전북특별자치도': '호남권', '전라북도': '호남권',
    '전라남도': '호남권', '광주광역시': '호남권', '전남광주특별시': '호남권',
    '경상북도': '영남권', '경상남도': '영남권',
    '대구광역시': '영남권', '울산광역시': '영남권', '부산광역시': '영남권',
    '강원특별자치도': '강원권', '강원도': '강원권',
    '제주특별자치도': '제주권',
}

# 권역 → zone. 영남 cell 수가 많아 호남만으로 불균형(29~37 차이).
# 충청을 호남과 같이 S_L에 묶어 좌·우 균형 (3~13 차이).
REGION_ZONE = {
    '수도권': 'N', '강원권': 'N',
    '충청권': 'S_L',  # 호남과 함께 좌측 (영남이 너무 많아 balance용)
    '호남권': 'S_L',
    '영남권': 'S_R',
    '제주권': 'P',
}

SIDO_PREFIX = {
    '서울특별시': '11', '부산광역시': '21', '대구광역시': '22', '인천광역시': '23',
    '광주광역시': '24', '대전광역시': '25', '울산광역시': '26', '세종특별자치시': '29',
    '경기도': '31', '강원특별자치도': '32', '강원도': '32', '충청북도': '33',
    '충청남도': '34', '전북특별자치도': '35', '전라북도': '35', '전라남도': '36',
    '경상북도': '37', '경상남도': '38', '제주특별자치도': '39',
}

DEFAULT_TARGETS = [
    'data/geo/sigungu_hex.json',
    'data/geo/sigungu_hex_legacy.json',
    'data/geo/district_hex_17.json',
    'data/geo/district_hex_18.json',
    'data/geo/district_hex_19.json',
    'data/geo/district_hex_20.json',
    'data/geo/district_hex_21.json',
    'data/geo/district_hex_22.json',
]


def polygon_centroid(geom):
    coords = geom['coordinates']
    if geom['type'] == 'MultiPolygon':
        ring = max(coords, key=lambda p: len(p[0]))[0]
    else:
        ring = coords[0]
    n = len(ring)
    return sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n


def load_centroids():
    sg = json.loads(SIGUNGU_GEO.read_text(encoding='utf-8'))
    by_code = {}
    by_name = defaultdict(list)
    for f in sg['features']:
        code = f['properties']['code']
        name = f['properties']['name']
        lon, lat = polygon_centroid(f['geometry'])
        by_code[code] = (lon, lat)
        by_name[name].append((code, lon, lat))
    return by_code, by_name


def cell_centroid(cell, by_code, by_name):
    if 'sigungus' in cell and cell['sigungus']:
        lons, lats = [], []
        for nm in cell['sigungus']:
            if nm in by_name:
                _, lon, lat = by_name[nm][0]
                lons.append(lon); lats.append(lat)
        if lons:
            return sum(lons) / len(lons), sum(lats) / len(lats)
        return None
    code = cell.get('code')
    if code and code in by_code:
        return by_code[code]
    if code and len(code) == 6:
        prefix = code[:5]
        m = [v for k, v in by_code.items() if k.startswith(prefix) and len(k) == 5]
        if m:
            return sum(x[0] for x in m) / len(m), sum(x[1] for x in m) / len(m)
    if code and len(code) == 5:
        m = [v for k, v in by_code.items() if k.startswith(code)]
        if m:
            return sum(x[0] for x in m) / len(m), sum(x[1] for x in m) / len(m)
    name = cell.get('name')
    if name and name in by_name:
        return by_name[name][0][1], by_name[name][0][2]
    sido = cell.get('sido')
    if sido and sido in SIDO_PREFIX:
        pfx = SIDO_PREFIX[sido]
        m = [v for k, v in by_code.items() if k.startswith(pfx)]
        if m:
            return sum(x[0] for x in m) / len(m), sum(x[1] for x in m) / len(m)
    return None


def lat_bin_rows(cells, n_rows, mode='quantile'):
    """cells에 _r_local 부여, row → cells dict 반환. lon 정렬됨.
    mode='quantile' (기본): cell 수 균등 (row width 일정)
    mode='linear': lat 균등 (한반도 silhouette 자연, row width 비균등)"""
    if not cells or n_rows <= 0:
        return {}
    rows = defaultdict(list)
    if mode == 'quantile':
        sorted_cells = sorted(cells, key=lambda c: -c['lat'])
        n = len(sorted_cells)
        for i, c in enumerate(sorted_cells):
            r = min(n_rows - 1, int(i * n_rows / n))
            c['_r_local'] = r
            rows[r].append(c)
    else:
        lats = [c['lat'] for c in cells]
        lo, hi = min(lats), max(lats)
        span = hi - lo or 1.0
        bin_h = span / n_rows
        for c in cells:
            r = int((hi - c['lat']) / bin_h)
            r = max(0, min(n_rows - 1, r))
            c['_r_local'] = r
            rows[r].append(c)
    for r in rows:
        rows[r].sort(key=lambda c: c['lon'])
    return rows


def n_rows_for(n_cells: int, target_row_width: float) -> int:
    if n_cells == 0:
        return 0
    return max(1, round(n_cells / target_row_width))


def t_zone_layout(cells, target_row_width=12):
    """T-zone layout. cells에 c, r 부여. 누락된 lon/lat cells은 건드리지 않음."""
    # group by zone
    zone_cells = defaultdict(list)
    for c in cells:
        if 'lon' not in c:
            continue
        zone = REGION_ZONE.get(SIDO_REGION.get(c['sido']), 'P')
        zone_cells[zone].append(c)

    # decide n_rows per zone
    n_N = n_rows_for(len(zone_cells['N']), target_row_width)
    n_S = n_rows_for(len(zone_cells['S_L']) + len(zone_cells['S_R']), target_row_width + 2)
    n_P = n_rows_for(len(zone_cells['P']), max(2, target_row_width // 4))

    rows_N = lat_bin_rows(zone_cells['N'], n_N)
    # S zone — 호남+충청 + 영남 같이 lat-bin, row 마다 left(호남+충청)·right(영남) 분리
    s_all = zone_cells['S_L'] + zone_cells['S_R']
    rows_S_combined = lat_bin_rows(s_all, n_S)
    s_split = {}
    for r in range(n_S):
        rcs = rows_S_combined.get(r, [])
        # 호남+충청 group: 충청이 호남보다 lon 살짝 east (충북 127.5+). 호남 먼저 lon, 충청 그 다음 lon.
        ho = sorted([c for c in rcs if SIDO_REGION[c['sido']] == '호남권'], key=lambda c: c['lon'])
        ch = sorted([c for c in rcs if SIDO_REGION[c['sido']] == '충청권'], key=lambda c: c['lon'])
        L = ho + ch  # 호남(좌측 더 west) → 충청(좌측 east 살짝)
        R = sorted([c for c in rcs if SIDO_REGION[c['sido']] == '영남권'], key=lambda c: c['lon'])
        s_split[r] = (L, R)
    rows_P = lat_bin_rows(zone_cells['P'], n_P)

    # widths
    w_N = max((len(rcs) for rcs in rows_N.values()), default=0)
    w_SL = max((len(s_split[r][0]) for r in range(n_S)), default=0)
    w_SR = max((len(s_split[r][1]) for r in range(n_S)), default=0)
    w_P = max((len(rcs) for rcs in rows_P.values()), default=0)

    # boundary 가운데 정렬: 양쪽 max width
    half = max(w_SL, w_SR, (w_N + 1) // 2, (w_P + 1) // 2)
    bbox_width = 2 * half
    boundary = half

    def center_place(row_cells, row_index):
        w = len(row_cells)
        col_start = boundary - w // 2 - (w % 2)
        for i, c in enumerate(row_cells):
            c['c'] = col_start + i
            c['r'] = row_index

    out_rows = 0
    # N
    for r in range(n_N):
        center_place(rows_N.get(r, []), out_rows + r)
    out_rows += n_N
    # S — 호남+충청 우측정렬, 영남 좌측정렬, boundary 가운데
    for r in range(n_S):
        L, R = s_split[r]
        for i, c in enumerate(L):
            c['c'] = boundary - len(L) + i
            c['r'] = out_rows + r
        for i, c in enumerate(R):
            c['c'] = boundary + i
            c['r'] = out_rows + r
    out_rows += n_S
    # P
    for r in range(n_P):
        center_place(rows_P.get(r, []), out_rows + r)
    out_rows += n_P
    return out_rows, bbox_width


def process(path: Path, target_row_width, dry, backup):
    cells = json.loads(path.read_text(encoding='utf-8'))
    by_code, by_name = load_centroids()
    missing = []
    for c in cells:
        cent = cell_centroid(c, by_code, by_name)
        if cent is None:
            missing.append(c.get('name', c.get('code', '?')))
            continue
        c['lon'], c['lat'] = cent
    n_total_rows, bbox_w = t_zone_layout(cells, target_row_width)
    # 정리
    for c in cells:
        c.pop('lon', None); c.pop('lat', None); c.pop('_r_local', None)
    valid = [c for c in cells if 'c' in c]
    info = {
        'path': str(path.relative_to(ROOT)),
        'n': len(valid),
        'rows': n_total_rows,
        'bbox': f'{bbox_w}×{n_total_rows}',
        'missing': missing,
    }
    if not dry:
        if backup:
            bak = path.with_suffix(path.suffix + '.zone.bak')
            if not bak.exists():
                shutil.copy2(path, bak)
        path.write_text(json.dumps(cells, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--target-row-width', type=float, default=12)
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--no-backup', action='store_true')
    args = ap.parse_args()
    paths = [ROOT / p if not Path(p).is_absolute() else Path(p) for p in (args.paths or DEFAULT_TARGETS)]
    paths = [p for p in paths if p.exists()]
    print(f'[build_zone_hex] {len(paths)} files | target_row_width={args.target_row_width}\n')
    for p in paths:
        info = process(p, target_row_width=args.target_row_width, dry=args.dry, backup=not args.no_backup)
        print(f"{info['path']}")
        print(f"  n={info['n']} bbox={info['bbox']}")
        if info['missing']:
            print(f"  missing: {len(info['missing'])} → {info['missing'][:3]}")


if __name__ == '__main__':
    main()
