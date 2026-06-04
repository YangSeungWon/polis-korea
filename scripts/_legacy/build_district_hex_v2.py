"""총선 N대 지역구 hex layout 빌더 — 시군구 hex 기반 simple version.

대선 hex (시군구)가 이미 polished이라 그 layout 위에 지역구를 자연스럽게 매핑.

알고리즘 (manual cells / anchor BFS 없음):
1. 시군구 hex layout 로드 (250 cells, 시도별 분류)
2. 각 지역구 → 관할 시군구 추출 (parse_district_name)
3. 시도별로:
   a. sigungu_hex의 그 시도 cells가 base
   b. 시도 districts 수 D, sigungu cells 수 S 비교
   c. D > S면 시도 cells outer로 BFS 확장 (round-robin)
   d. D < S면 일부 sigungu cells discard (외곽부터)
4. 시도별 Hungarian assign — districts × cells, cost = 지역구 centroid - cell pixel 거리

사용:
  .venv/bin/python scripts/_legacy/build_district_hex_v2.py        # 22대 (기본)
  .venv/bin/python scripts/_legacy/build_district_hex_v2.py 20

출력: data/geo/district_hex_N.json (기존과 동일 schema)
"""
from __future__ import annotations
import argparse
import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[2]
SIGUNGU_HEX = ROOT / "data/geo/sigungu_hex.json"
SIGUNGU_GEO = ROOT / "data/geo/sigungu_simple.json"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _geo import sigungu_to_sido
from _hex import offset_neighbors, offset_to_pixel, polygon_centroid  # noqa: F401
# 지역구명 파싱 등 district 전용 헬퍼는 v1 build에서 import
from build_district_hex_22 import (
    PARENT_TO_CHILDREN, SGG_ALIAS, SIDO_AS_SGG,
    parse_district_name,
)


# 가로 납작 우선 시도들 — discard·expand 모두 가로 우선.
SIDO_PREFER_HORIZONTAL = {'전북특별자치도', '광주광역시', '전라남도'}
# 세로 우선 — 가로 expand 안 함. (서울은 r_min 제약으로 충분, 비우면 북쪽 spike 사라짐)
SIDO_PREFER_VERTICAL = set()
# 시도 expand 시 cell 위치 제한 — 경기 wrap 영역 침범 방지
# 서울: 48석이 doubling되며 북쪽(r<-1)으로 굴뚝처럼 솟던 것 차단. r_min=-1로 컴팩트하게.
# 경기 r_max=12: 충남(r6~9) 아래로 평택/안성/용인이 내려가지 않게.
SIDO_MAX_RANGE = {
    '서울특별시': {'c_min': 2, 'c_max': 9, 'r_min': -1},
    '경기도': {'r_max': 12},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('n', nargs='?', type=int, default=22)
    args = ap.parse_args()
    n = args.n
    DISTRICT_META = ROOT / f"data/geo/district_{n}_centroid.json"
    OUT = ROOT / f"data/geo/district_hex_{n}.json"

    # === 데이터 로드 ===
    hex_data = json.loads(SIGUNGU_HEX.read_text(encoding='utf-8'))
    geo = json.loads(SIGUNGU_GEO.read_text(encoding='utf-8'))

    sgg_centroid_geo = {}
    for feat in geo['features']:
        code = feat['properties']['code']
        sido = sigungu_to_sido(code)
        name = feat['properties']['name']
        if sido and name:
            sgg_centroid_geo[(sido, name)] = polygon_centroid(feat['geometry'])

    sgg_hex_pos = {}
    sgg_by_sido = defaultdict(set)
    for h in hex_data:
        sgg_hex_pos[(h['sido'], h['name'])] = (h['c'], h['r'])
        sgg_by_sido[h['sido']].add(h['name'])
    for (sido, old_name), new_name in SGG_ALIAS.items():
        sgg_by_sido[sido].add(old_name)

    districts = json.loads(DISTRICT_META.read_text(encoding='utf-8'))

    # === 지역구 정보 (centroid, sigungu 관할) ===
    district_info = []
    for d in districts:
        sido, name = d['sido'], d['name']
        sgg_list = parse_district_name(sido, name, sgg_by_sido)
        if not sgg_list:
            print(f'  X 시군구 매칭 실패: {sido} {name}', file=sys.stderr)
            continue
        lons, lats = [], []
        hex_xs, hex_ys = [], []
        for sgg in sgg_list:
            ctr = sgg_centroid_geo.get((sido, sgg))
            if ctr is None:
                for (s2, n2), c2 in sgg_centroid_geo.items():
                    if n2 == sgg:
                        ctr = c2; break
            if ctr:
                lons.append(ctr[0]); lats.append(ctr[1])
            hex_pos = sgg_hex_pos.get((sido, sgg))
            if hex_pos is None:
                for (s2, n2), p in sgg_hex_pos.items():
                    if n2 == sgg:
                        hex_pos = p; break
            if hex_pos:
                hx, hy = offset_to_pixel(*hex_pos)
                hex_xs.append(hx); hex_ys.append(hy)
        if not lons:
            print(f'  X centroid 없음: {sido} {name}', file=sys.stderr)
            continue
        district_info.append({
            'sido': sido,
            'name': name,
            'lon': sum(lons) / len(lons),
            'lat': sum(lats) / len(lats),
            'hex_x': sum(hex_xs) / len(hex_xs) if hex_xs else 0,
            'hex_y': sum(hex_ys) / len(hex_ys) if hex_ys else 0,
            'sigungus': sgg_list,
        })

    print(f'유효 지역구: {len(district_info)} / {len(districts)}', file=sys.stderr)

    # === 시도별 cells 준비 ===
    sido_districts = defaultdict(list)
    for d in district_info:
        sido_districts[d['sido']].append(d)

    # 시도 → sigungu_hex 의 그 시도 cells
    sido_sgg_cells = defaultdict(set)
    for h in hex_data:
        sido_sgg_cells[h['sido']].add((h['c'], h['r']))

    # 시도별 target cell 수 = 지역구 수
    sido_target = {s: len(sido_districts[s]) for s in sido_districts}

    # 신 sigungu_hex가 잘 배치되어 manual shift/override 거의 불필요.
    # 세종: 21·22대 갑/을 2 districts ↔ sigungu_hex 1 cell. (7,6) 추가 reserve.
    SIDO_CELLS_OVERRIDE = {
        '세종특별자치시': [(8, 7), (7, 6)],
    }
    for sido, cells_list in SIDO_CELLS_OVERRIDE.items():
        if sido not in sido_target: continue
        n = sido_target[sido]
        new_cells = set(cells_list[:max(n, 1)])
        sido_sgg_cells[sido] = new_cells
        # 다른 시도가 점유한 cells 양보
        for other in list(sido_sgg_cells):
            if other == sido: continue
            sido_sgg_cells[other] -= new_cells

    # 모든 sigungu cells을 occupied로 표시
    occupied = {}  # (c, r) → sido
    for s, cells in sido_sgg_cells.items():
        for c in cells:
            occupied[c] = s

    # 시도별 최종 cluster cells
    sido_cells = {s: set(sido_sgg_cells[s]) for s in sido_sgg_cells}

    # === Phase 1: discard 먼저 (D < S 시도 → 외곽 cells을 빈자리로) ===
    for s, cells in sido_cells.items():
        target = sido_target.get(s, 0)
        if len(cells) <= target:
            continue
        cx = sum(c[0] for c in cells) / len(cells)
        cy = sum(c[1] for c in cells) / len(cells)
        cx_px, cy_px = offset_to_pixel(cx, cy)
        prefer_horiz = s in SIDO_PREFER_HORIZONTAL
        while len(cells) > target:
            cluster_set = cells
            boundary = [c for c in cells if any(nb not in cluster_set for nb in offset_neighbors(*c))]
            if prefer_horiz:
                # r-extreme (가장 위·아래) row의 cells 무조건 우선 → 세로 좁아짐
                cell_rs = [c[1] for c in cells]
                r_min, r_max = min(cell_rs), max(cell_rs)
                candidates = sorted(boundary, key=lambda p: (
                    0 if (p[1] == r_min or p[1] == r_max) else 1,
                    -abs(offset_to_pixel(*p)[1] - cy_px),
                    -abs(offset_to_pixel(*p)[0] - cx_px),
                ))
            else:
                candidates = sorted(boundary,
                                    key=lambda p: -math.hypot(
                                        offset_to_pixel(*p)[0] - cx_px,
                                        offset_to_pixel(*p)[1] - cy_px,
                                    ))
            removed = False
            for c in candidates:
                new_cells = cells - {c}
                if not new_cells:
                    continue
                start = next(iter(new_cells))
                visited = {start}; q = deque([start])
                while q:
                    cur = q.popleft()
                    for nb in offset_neighbors(*cur):
                        if nb in new_cells and nb not in visited:
                            visited.add(nb); q.append(nb)
                if len(visited) == len(new_cells):
                    cells.discard(c)
                    if c in occupied:
                        del occupied[c]
                    removed = True
                    break
            if not removed and candidates:
                c = candidates[0]
                cells.discard(c)
                if c in occupied: del occupied[c]
            elif not removed:
                break

    # === Phase 2: expand (D > S 시도 → 인접 빈자리 + 한반도 외부 + swap) ===
    def needs_expand():
        return [s for s in sido_target if len(sido_cells.get(s, set())) < sido_target[s]]

    for iteration in range(2000):
        if not needs_expand(): break
        progressed = False
        order = sorted(needs_expand(),
                       key=lambda s: sido_target[s] - len(sido_cells[s]), reverse=True)
        for s in order:
            if len(sido_cells[s]) >= sido_target[s]: continue
            cells = sido_cells[s]
            cx = sum(c[0] for c in cells) / len(cells)
            cy = sum(c[1] for c in cells) / len(cells)
            cx_px, cy_px = offset_to_pixel(cx, cy)
            # cluster aspect — wide가 tall의 절반보다 작을 때만 가로 expand 우선
            cell_cs = [c[0] for c in cells]; cell_rs = [c[1] for c in cells]
            wide = max(cell_cs) - min(cell_cs) + 1
            tall = (max(cell_rs) - min(cell_rs) + 1) * (math.sqrt(3) / 2)
            if s in SIDO_PREFER_VERTICAL:
                prefer_horiz = False
            elif s in SIDO_PREFER_HORIZONTAL:
                prefer_horiz = True
            else:
                prefer_horiz = wide < tall * 0.7
            # 인접 빈 cells 우선
            cand_empty = set()
            for c in cells:
                for nb in offset_neighbors(*c):
                    if nb not in occupied:
                        cand_empty.add(nb)
            # SIDO_MAX_RANGE 적용 — 시도 cells 위치 제한
            rng = SIDO_MAX_RANGE.get(s)
            if rng:
                cand_empty = {nb for nb in cand_empty
                              if rng.get('c_min', -999) <= nb[0] <= rng.get('c_max', 999)
                              and rng.get('r_min', -999) <= nb[1] <= rng.get('r_max', 999)}
            if cand_empty:
                def expand_key(p):
                    px, py = offset_to_pixel(*p)
                    n_occ = sum(1 for nb in offset_neighbors(*p) if nb in occupied)
                    # 1) indentation 우선
                    # 2) cluster aspect — 짧은 축으로 expand 우선
                    # 3) centroid 가까이
                    if prefer_horiz:
                        axis_bias = abs(py - cy_px)  # 가로면 dy 작을수록 좋음
                    else:
                        axis_bias = abs(px - cx_px)
                    return (-n_occ, axis_bias, math.hypot(px - cx_px, py - cy_px))
                best = min(cand_empty, key=expand_key)
                cells.add(best)
                occupied[best] = s
                progressed = True
                continue
            # 빈자리 없음 — 다른 시도 외곽 cells 중 그 시도의 잉여(or 가장 멀고 boundary)인 cell swap
            # 단 다른 시도의 connectivity 유지
            cand_other = []
            for c in cells:
                for nb in offset_neighbors(*c):
                    if nb in occupied and occupied[nb] != s:
                        cand_other.append(nb)
            for nb in sorted(set(cand_other), key=lambda p: math.hypot(
                offset_to_pixel(*p)[0] - cx_px,
                offset_to_pixel(*p)[1] - cy_px,
            )):
                owner = occupied[nb]
                owner_cells = sido_cells[owner]
                # connectivity 유지 + owner cells > target 이면 안전
                if len(owner_cells) <= sido_target.get(owner, 0): continue
                new_owner = owner_cells - {nb}
                if not new_owner: continue
                start = next(iter(new_owner))
                visited = {start}; q = deque([start])
                while q:
                    cur = q.popleft()
                    for nb2 in offset_neighbors(*cur):
                        if nb2 in new_owner and nb2 not in visited:
                            visited.add(nb2); q.append(nb2)
                if len(visited) != len(new_owner): continue
                # swap
                owner_cells.discard(nb)
                cells.add(nb)
                occupied[nb] = s
                progressed = True
                break
            if progressed: continue
        if not progressed: break

    # === Phase 3: 미달 시도에 빈자리 우선, 없으면 swap (chain 허용).
    for iteration in range(300):
        if not needs_expand(): break
        progressed = False
        for s in list(needs_expand()):
            cells = sido_cells[s]
            if len(cells) >= sido_target[s]: continue
            cx = sum(c[0] for c in cells) / len(cells)
            cy = sum(c[1] for c in cells) / len(cells)
            cx_px, cy_px = offset_to_pixel(cx, cy)
            # 1) 인접 빈자리 우선
            cand_empty = set()
            for c in cells:
                for nb in offset_neighbors(*c):
                    if nb not in occupied:
                        cand_empty.add(nb)
            # SIDO_MAX_RANGE 적용
            rng = SIDO_MAX_RANGE.get(s)
            if rng:
                cand_empty = {nb for nb in cand_empty
                              if rng.get('c_min', -999) <= nb[0] <= rng.get('c_max', 999)
                              and rng.get('r_min', -999) <= nb[1] <= rng.get('r_max', 999)}
            if cand_empty:
                # nbrs(occupied) 많은 indentation 먼저 → 한반도 boundary 매끄럽게.
                best = min(cand_empty, key=lambda p: (
                    -sum(1 for nb in offset_neighbors(*p) if nb in occupied),
                    math.hypot(offset_to_pixel(*p)[0] - cx_px,
                               offset_to_pixel(*p)[1] - cy_px),
                ))
                cells.add(best)
                occupied[best] = s
                progressed = True
                continue
            # 2) 빈자리 없음 → swap
            cand_other = set()
            for c in cells:
                for nb in offset_neighbors(*c):
                    if nb in occupied and occupied[nb] != s:
                        cand_other.add(nb)
            for nb in sorted(cand_other, key=lambda p: (
                -(len(sido_cells[occupied[p]]) - sido_target.get(occupied[p], 0)),
                math.hypot(offset_to_pixel(*p)[0] - cx_px,
                           offset_to_pixel(*p)[1] - cy_px),
            )):
                owner = occupied[nb]
                owner_cells = sido_cells[owner]
                if len(owner_cells) <= 1: continue
                new_owner = owner_cells - {nb}
                start = next(iter(new_owner))
                visited = {start}; q = deque([start])
                while q:
                    cur = q.popleft()
                    for nb2 in offset_neighbors(*cur):
                        if nb2 in new_owner and nb2 not in visited:
                            visited.add(nb2); q.append(nb2)
                if len(visited) != len(new_owner): continue
                owner_cells.discard(nb)
                cells.add(nb)
                occupied[nb] = s
                progressed = True
                break
            if progressed: break
        if not progressed: break

    # === Hungarian: 시도별 districts × cells (부분 매핑 허용) ===
    placed = {}
    for s, ds in sido_districts.items():
        cells = list(sido_cells.get(s, set()))
        n_d = len(ds)
        n_c = len(cells)
        if n_c < n_d:
            print(f'  ! {s}: cells {n_c} < districts {n_d} (일부 미배치)', file=sys.stderr)
        if n_c == 0: continue
        cell_px = [offset_to_pixel(*c) for c in cells]
        # rectangular cost — Hungarian이 min(n_d, n_c) 매핑
        cost = np.full((n_d, n_c), 1e9)
        for i, d in enumerate(ds):
            for j, (cx, cy) in enumerate(cell_px):
                cost[i, j] = (d['hex_x'] - cx) ** 2 + (d['hex_y'] - cy) ** 2
        rows, cols = linear_sum_assignment(cost)
        for i, j in zip(rows, cols):
            placed[(ds[i]['sido'], ds[i]['name'])] = cells[j]

    # === 출력 ===
    result = []
    for d in district_info:
        key = (d['sido'], d['name'])
        pos = placed.get(key)
        if pos is None:
            print(f'  X 미배치: {key}', file=sys.stderr)
            continue
        result.append({
            'sido': d['sido'],
            'name': d['name'],
            'c': pos[0], 'r': pos[1],
            'sigungus': d['sigungus'],
        })

    OUT.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    cs = [r['c'] for r in result]; rs = [r['r'] for r in result]
    print(f'배치 {len(result)} 지역구. c {min(cs)}~{max(cs)} r {min(rs)}~{max(rs)}', file=sys.stderr)
    print(f'→ {OUT.relative_to(ROOT)}', file=sys.stderr)

    # fill_holes 후처리 — 내부 hole 슬라이드로 메움
    import importlib.util
    spec = importlib.util.spec_from_file_location("fill_holes", Path(__file__).parent / "fill_holes.py")
    fh = importlib.util.module_from_spec(spec); spec.loader.exec_module(fh)
    # 호남 manual cells은 slide-fill에서 보호 (strip 형태 유지)
    filled = fh.run(result, verbose=False, protect_sidos=set(SIDO_CELLS_OVERRIDE))
    OUT.write_text(json.dumps(filled, ensure_ascii=False), encoding='utf-8')
    print(f'hole-fill 적용 → {len(filled)} cells', file=sys.stderr)


if __name__ == '__main__':
    main()
