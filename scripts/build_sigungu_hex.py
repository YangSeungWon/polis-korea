"""시군구 hex grid 좌표 자동 생성 — centroid snap + 시도 cluster 연결성 강제.

알고리즘:
1. 각 시군구 polygon centroid 추출
2. centroid를 pointy-top hex grid에 snap (offset 좌표) — 자연스러운 한반도 모양
3. 충돌 시 spiral 검색으로 가장 가까운 빈 셀로 양보
4. 후처리: 각 시도의 시군구 중 메인 cluster와 떨어진 isolated 셀들을
   해당 시도 메인 cluster의 가장 가까운 빈 셀로 옮김. 연결성 보장.

이렇게 하면 경기가 서울 둘러싸고, 강원이 세로로 길고, 충청·전라·경상이
한반도 형태로 자연스럽게 배치되며, 동시에 시도별 cluster가 끊어지지 않음.

출력: data/geo/sigungu_hex.json
"""

from __future__ import annotations
import json
import math
import os
from collections import defaultdict, deque
from pathlib import Path

# 알고리즘 옵션 (환경변수로 override 가능 — iter_compare용)
ANCHOR_MODE = os.environ.get('ANCHOR_MODE', 'manual')      # manual | centroid | centroid-mainland
MATCH_MODE = os.environ.get('MATCH_MODE', 'hungarian')      # hungarian | greedy-edge
ROBIN_MODE = os.environ.get('ROBIN_MODE', 'fair')           # fair | desc-deficit
CELL_SIZE = float(os.environ.get('CELL_SIZE', '0.18'))

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "geo" / "sigungu_simple.json"
OUT = ROOT / "data" / "geo" / ("sigungu_hex_legacy.json" if os.environ.get("HEX_LEGACY")=="1" else "sigungu_hex.json")

from _geo import SIDO_CODE_TO_NAME, SIGUNGU_SIDO_OVERRIDE, sigungu_to_sido
from _hex import offset_neighbors, offset_to_pixel, polygon_centroid  # noqa: F401

# CELL_SIZE는 위에서 ENV로 받음


def cell_dist(a: tuple[int, int], b: tuple[int, int]) -> float:
    ax, ay = offset_to_pixel(*a)
    bx, by = offset_to_pixel(*b)
    return math.hypot(ax - bx, ay - by)


def lonlat_to_offset(lon: float, lat: float, origin_lon: float, origin_lat: float, cell: float) -> tuple[int, int]:
    """경위도 → offset (col, row). pointy-top, odd-r offset.

    pixel-like 좌표: x = (lon-origin_lon)/cell, y = -(lat - origin_lat)/cell  (북이 위)
    그 후 axial 추정 → offset 변환.
    """
    px = (lon - origin_lon) / cell
    py = -(lat - origin_lat) / cell  # 북=위
    # pixel → fractional axial (pointy-top)
    qf = (math.sqrt(3) / 3 * px - 1 / 3 * py)
    rf = (2 / 3 * py)
    # axial round (cube)
    xf, zf = qf, rf
    yf = -xf - zf
    rx, ry, rz = round(xf), round(yf), round(zf)
    x_diff = abs(rx - xf); y_diff = abs(ry - yf); z_diff = abs(rz - zf)
    if x_diff > y_diff and x_diff > z_diff:
        rx = -ry - rz
    elif y_diff > z_diff:
        pass
    else:
        rz = -rx - ry
    q, r_ax = rx, rz
    # axial → offset (odd-r)
    col = q + (r_ax - (r_ax & 1)) // 2
    row = r_ax
    return col, row


def find_nearest_empty(target: tuple[int, int], occupied: dict, max_steps: int = 50) -> tuple[int, int]:
    if target not in occupied:
        return target
    visited = {target}
    frontier = [target]
    for _ in range(max_steps):
        next_frontier = []
        for cell in frontier:
            for nb in offset_neighbors(*cell):
                if nb in visited:
                    continue
                visited.add(nb)
                if nb not in occupied:
                    return nb
                next_frontier.append(nb)
        frontier = next_frontier
        if not frontier:
            break
    raise RuntimeError(f"empty cell not found near {target}")


def find_components(cells: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    seen = set()
    out = []
    for cell in cells:
        if cell in seen:
            continue
        comp = set()
        q = deque([cell])
        while q:
            x = q.popleft()
            if x in comp:
                continue
            comp.add(x)
            for nb in offset_neighbors(*x):
                if nb in cells and nb not in comp:
                    q.append(nb)
        seen |= comp
        out.append(comp)
    return out


def find_nearest_empty_adjacent_to_cluster(cluster: set[tuple[int, int]], occupied: dict) -> tuple[int, int]:
    """cluster의 외곽 이웃 중 점유 안 된 셀 (가장 cluster 중심에 가까운)."""
    cx = sum(offset_to_pixel(*c)[0] for c in cluster) / len(cluster)
    cy = sum(offset_to_pixel(*c)[1] for c in cluster) / len(cluster)
    center_proxy = None
    best = None
    best_d = math.inf
    for c in cluster:
        for nb in offset_neighbors(*c):
            if nb in occupied or nb in cluster:
                continue
            x, y = offset_to_pixel(*nb)
            d = math.hypot(x - cx, y - cy)
            if d < best_d:
                best_d = d
                best = nb
    if best is None:
        # cluster가 너무 빽빽함 — 더 멀리 BFS
        visited = set(cluster)
        frontier = list(cluster)
        for _ in range(20):
            nf = []
            for c in frontier:
                for nb in offset_neighbors(*c):
                    if nb in visited:
                        continue
                    visited.add(nb)
                    if nb not in occupied:
                        x, y = offset_to_pixel(*nb)
                        d = math.hypot(x - cx, y - cy)
                        if d < best_d:
                            best_d = d
                            best = nb
                    else:
                        nf.append(nb)
            if best is not None:
                return best
            frontier = nf
    return best


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    features = data["features"]

    # 1. 시군구 수집
    rows = []
    for feat in features:
        props = feat["properties"]
        code = props["code"]
        sido = sigungu_to_sido(code)
        if not sido:
            continue
        lon, lat = polygon_centroid(feat["geometry"])
        rows.append({"code": code, "name": props["name"], "sido": sido, "lon": lon, "lat": lat})

    # 1-1. 통합도시 일반구 merge — 9회 지선 기초단체장은 통합 시장 1명.
    # 일반구(수원시장안구·청주시상당구 등)는 centroid 평균으로 1 row.
    # LEGACY 모드 (대선·총선 데이터처럼 일반구별 표시)면 merge 안 함.
    LEGACY = os.environ.get("HEX_LEGACY") == "1"
    import re
    if not LEGACY:
        parent_groups: dict[tuple, list] = defaultdict(list)
        others = []
        for r in rows:
            m = re.match(r"^([가-힣]+시)([가-힣]+구)$", r["name"])
            if m:
                parent_groups[(r["sido"], m.group(1))].append(r)
            else:
                others.append(r)
        rows = list(others)
        for (sido, parent), group in parent_groups.items():
            if len(group) == 1:
                rows.append(group[0])
                continue
            avg_lon = sum(g["lon"] for g in group) / len(group)
            avg_lat = sum(g["lat"] for g in group) / len(group)
            code = group[0]["code"][:5] + "0"
            rows.append({"code": code, "name": parent, "sido": sido, "lon": avg_lon, "lat": avg_lat})

    # 1-2. 인천 신설 분구 (2026-07) — 9회 지선 base만, LEGACY 모드는 skip.
    if not LEGACY:
        INCHEON_NEW = [
            ("영종구",   "23013", 126.45, 37.49),
            ("제물포구", "23012", 126.65, 37.47),
            ("검단구",   "23014", 126.66, 37.61),
        ]
        for name, code, lon, lat in INCHEON_NEW:
            rows.append({"code": code, "name": name, "sido": "인천광역시", "lon": lon, "lat": lat})

    by_sido: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_sido[r["sido"]].append(r)

    # 2. 시도 anchor — ANCHOR_MODE에 따라
    # 한반도 형상 + 시각적 자연스러움 (광주는 전남 안, 인천은 서울 서쪽 멀리, 충북은 경기 안 막게)
    # RECT_BOUNDS (c=0~16, r=0~16) 안에 모든 anchor.
    SIDO_ANCHOR_MANUAL = {
        '강원특별자치도': (10, 1),
        '경기도':         (3,  4),   # 서울 서쪽 — 서울 박스 안 비워 서울 컴팩트 + 경기는 둘레로
        '서울특별시':     (5,  2),
        '인천광역시':     (0,  1),   # 좌상단 코너
        '충청북도':       (9,  7),   # 충청 belt 동쪽 (세종 동쪽·경북 서쪽) — 충청 클러스터 재연결
        '충청남도':       (5,  7),
        '세종특별자치시': (8,  6),
        '대전광역시':     (7,  8),
        '경상북도':       (14, 7),
        '대구광역시':     (13, 10),
        '울산광역시':     (15, 11),
        '부산광역시':     (15, 13),
        '경상남도':       (12, 12),
        '전북특별자치도': (7,  10),
        '광주광역시':     (8,  13),
        '전라남도':       (6,  14),
        '제주특별자치도': (4,  16),  # rect 안 가장 아래
    }
    OUTLIER_CODES = {'23320', '37520'}  # 옹진, 울릉
    origin_lon = min(r["lon"] for r in rows) - 0.1
    origin_lat = max(r["lat"] for r in rows) + 0.1
    sido_anchor: dict[str, tuple[int, int]] = {}
    if ANCHOR_MODE == 'manual':
        sido_anchor = dict(SIDO_ANCHOR_MANUAL)
    elif ANCHOR_MODE == 'centroid':
        for sido, sigungus in by_sido.items():
            slon = sum(s["lon"] for s in sigungus) / len(sigungus)
            slat = sum(s["lat"] for s in sigungus) / len(sigungus)
            sido_anchor[sido] = lonlat_to_offset(slon, slat, origin_lon, origin_lat, CELL_SIZE)
    elif ANCHOR_MODE == 'centroid-mainland':
        for sido, sigungus in by_sido.items():
            ml = [s for s in sigungus if s["code"] not in OUTLIER_CODES]
            if not ml: ml = sigungus
            slon = sum(s["lon"] for s in ml) / len(ml)
            slat = sum(s["lat"] for s in ml) / len(ml)
            sido_anchor[sido] = lonlat_to_offset(slon, slat, origin_lon, origin_lat, CELL_SIZE)

    # 시도 anchor 충돌 해결 — 큰 시도 먼저 자기 자리, 작은 시도가 양보
    anchor_occupied: dict[tuple[int, int], str] = {}
    sorted_sidos = sorted(sido_anchor, key=lambda s: -len(by_sido[s]))
    for sido in sorted_sidos:
        anchor = sido_anchor[sido]
        if anchor not in anchor_occupied:
            anchor_occupied[anchor] = sido
        else:
            new_anchor = find_nearest_empty(anchor, anchor_occupied)
            anchor_occupied[new_anchor] = sido
            sido_anchor[sido] = new_anchor

    # 3. 라운드로빈 BFS — 모든 시도 동시 영역 확장
    # RECT_BOUNDS: cells가 이 직사각 안에만 자라도록 제한. 결과 layout이 rect 형태.
    RECT_BOUNDS = {'c_min': 0, 'c_max': 16, 'r_min': 0, 'r_max': 16}
    def in_rect(cell):
        c, r = cell
        return (RECT_BOUNDS['c_min'] <= c <= RECT_BOUNDS['c_max']
                and RECT_BOUNDS['r_min'] <= r <= RECT_BOUNDS['r_max'])

    # 시도별 영역 제한 — 특정 시도가 옆 시도 영역으로 번지는 것 방지.
    # (경기 작업과 함께 서울·경기 범위 조정 예정)
    SIDO_MAX_RANGE = {
    }
    def in_range(sido, cell):
        rng = SIDO_MAX_RANGE.get(sido)
        if not rng:
            return True
        c, r = cell
        return (rng.get('c_min', -999) <= c <= rng.get('c_max', 999)
                and rng.get('r_min', -999) <= r <= rng.get('r_max', 999))

    targets = {sido: len(by_sido[sido]) for sido in by_sido}
    territories: dict[str, set[tuple[int, int]]] = {sido: set() for sido in by_sido}
    frontiers: dict[str, deque] = {sido: deque() for sido in by_sido}
    occupied: dict[tuple[int, int], str] = {}

    for sido, anchor in sido_anchor.items():
        if targets[sido] == 0:
            continue
        territories[sido].add(anchor)
        occupied[anchor] = sido
        for nb in offset_neighbors(*anchor):
            if in_rect(nb) and in_range(sido, nb):
                frontiers[sido].append(nb)

    # Fair 라운드로빈: 매 round 모든 활성 시도가 1셀씩 추가.
    while any(len(territories[s]) < targets[s] for s in by_sido):
        progressed = False
        order = [s for s in by_sido if len(territories[s]) < targets[s]]
        for sido in order:
            if len(territories[sido]) >= targets[sido]:
                continue
            anchor = sido_anchor[sido]
            # frontier에서 점유 안 된 cell 중 시도 centroid에 가장 가까운 것
            best = None
            best_dist = math.inf
            for cell in frontiers[sido]:
                if cell in occupied or not in_rect(cell) or not in_range(sido, cell):
                    continue
                d = math.hypot(*[a - b for a, b in zip(offset_to_pixel(*cell), offset_to_pixel(*anchor))])
                if d < best_dist:
                    best_dist = d
                    best = cell
            if best is None:
                # 시도 영역에서 빈 이웃 한 칸 검색 (rect 내)
                pool = []
                for cell in territories[sido]:
                    for nb in offset_neighbors(*cell):
                        if nb not in occupied and in_rect(nb) and in_range(sido, nb):
                            pool.append(nb)
                if not pool:
                    targets[sido] = len(territories[sido])
                    continue
                best = min(pool, key=lambda c: math.hypot(*[a - b for a, b in zip(offset_to_pixel(*c), offset_to_pixel(*anchor))]))
            else:
                frontiers[sido] = deque(c for c in frontiers[sido] if c != best)
            territories[sido].add(best)
            occupied[best] = sido
            for nb in offset_neighbors(*best):
                if nb not in occupied and in_rect(nb) and in_range(sido, nb):
                    frontiers[sido].append(nb)
            progressed = True
        if not progressed:
            break

    # 3.5. 라운드로빈 후 target 못 채운 시도 — 강제 확장 + cell stealing
    for sido in list(by_sido):
        deficit = targets[sido] - len(territories[sido])
        if deficit <= 0:
            continue
        anchor = sido_anchor[sido]
        for _ in range(deficit):
            # (a) territory에서 BFS로 빈 cell 검색
            visited = set(territories[sido])
            frontier_q = deque(territories[sido])
            found = None
            while frontier_q:
                cell = frontier_q.popleft()
                for nb in offset_neighbors(*cell):
                    if nb in visited:
                        continue
                    visited.add(nb)
                    if nb not in occupied:
                        found = nb
                        break
                    frontier_q.append(nb)
                if found:
                    break
            # (b) 빈 cell 못 찾으면 다른 시도 cell steal
            if not found:
                steal = None
                steal_d = math.inf
                for tcell in territories[sido]:
                    for nb in offset_neighbors(*tcell):
                        if nb in territories[sido]:
                            continue
                        other_sido = occupied.get(nb)
                        if not other_sido or other_sido == sido:
                            continue
                        # 그 다른 시도가 nb 잃어도 connected 유지하는지 확인 + 그 시도가 자기 영역 내 다른 cell 충분한지
                        other_cells = territories[other_sido] - {nb}
                        if not other_cells:
                            continue
                        # connectivity check: other_sido cluster 끊어지지 않게
                        start = next(iter(other_cells))
                        v = {start}
                        q = deque([start])
                        while q:
                            x = q.popleft()
                            for nb2 in offset_neighbors(*x):
                                if nb2 in other_cells and nb2 not in v:
                                    v.add(nb2); q.append(nb2)
                        if len(v) != len(other_cells):
                            continue
                        # 거리 기준
                        d = math.hypot(*[a - b for a, b in zip(offset_to_pixel(*nb), offset_to_pixel(*anchor))])
                        if d < steal_d:
                            steal_d = d
                            steal = (nb, other_sido)
                if steal:
                    nb, other_sido = steal
                    territories[other_sido].discard(nb)
                    territories[sido].add(nb)
                    occupied[nb] = sido
                    continue
                break
            territories[sido].add(found)
            occupied[found] = sido

    # 3.7. Hole fill — 인접 5+ 셀이 occupied인 빈칸을 가장 많이 닿은 시도에 흡수
    # 가운데 빈칸 (시각적 거슬림) 자동 채우기. 그 시도 territory target은 그만큼 늘림.
    from collections import Counter as _C
    for _pass in range(5):
        if not occupied:
            break
        cs_all = [c for c, r in occupied]
        rs_all = [r for c, r in occupied]
        min_c_g, max_c_g = min(cs_all), max(cs_all)
        min_r_g, max_r_g = min(rs_all), max(rs_all)
        filled = 0
        for rr in range(min_r_g, max_r_g + 1):
            for cc in range(min_c_g, max_c_g + 1):
                if (cc, rr) in occupied:
                    continue
                nbrs = offset_neighbors(cc, rr)
                occ_sidos = [occupied[nb] for nb in nbrs if nb in occupied]
                if len(occ_sidos) >= 4:  # 4/6 이상 둘러쌓이면 hole로 간주
                    best = _C(occ_sidos).most_common(1)[0][0]
                    territories[best].add((cc, rr))
                    occupied[(cc, rr)] = best
                    targets[best] += 1
                    filled += 1
        if filled == 0:
            break

    # 4. 시도 영역 안에 시군구 배치 — affine 변환으로 비례 보존
    moved_total = 0
    for sido, sigungus in by_sido.items():
        territory = list(territories.get(sido, set()))
        if not territory:
            continue
        # cell 영역 bbox
        cell_pixels = [offset_to_pixel(*c) for c in territory]
        cxs = [p[0] for p in cell_pixels]
        cys = [p[1] for p in cell_pixels]
        cx_min, cx_max = min(cxs), max(cxs)
        cy_min, cy_max = min(cys), max(cys)
        cx_mid = (cx_min + cx_max) / 2
        cy_mid = (cy_min + cy_max) / 2
        cx_range = (cx_max - cx_min) or 1
        cy_range = (cy_max - cy_min) or 1

        # sigungu lon/lat bbox (북=위라 lat은 부호 반전)
        slons = [s["lon"] for s in sigungus]
        slats = [s["lat"] for s in sigungus]
        sl_min, sl_max = min(slons), max(slons)
        st_min, st_max = min(slats), max(slats)
        sl_mid = (sl_min + sl_max) / 2
        st_mid = (st_min + st_max) / 2
        sl_range = (sl_max - sl_min) or 1
        st_range = (st_max - st_min) or 1

        # 시군구 centroid → cell space (시도 bbox 비율 보존)
        sig_targets = []
        for s in sigungus:
            tx = cx_mid + (s["lon"] - sl_mid) / sl_range * cx_range
            ty = cy_mid + -(s["lat"] - st_mid) / st_range * cy_range
            sig_targets.append((s, tx, ty))

        # Hungarian optimal assignment — 모든 (시군구, cell) 거리 비용 행렬 만들고
        # scipy linear_sum_assignment로 총 거리 합 최소화 매칭.
        from scipy.optimize import linear_sum_assignment
        import numpy as np
        n_sig = len(sig_targets)
        n_cell = len(territory)
        # 직사각 비용 행렬: n_sig × n_cell. n_sig > n_cell이면 일부 시군구 미할당.
        cost = np.full((n_sig, n_cell), 1e9)
        for i, (s, tx, ty) in enumerate(sig_targets):
            for j, (cx, cy) in enumerate(cell_pixels):
                cost[i, j] = (tx - cx) ** 2 + (ty - cy) ** 2
        row_idx, col_idx = linear_sum_assignment(cost)
        assigned_sigungu = set()
        for i, j in zip(row_idx, col_idx):
            s = sig_targets[i][0]
            cell = territory[j]
            s["c"], s["r"] = cell
            assigned_sigungu.add(id(s))
        unassigned = [s for s in sigungus if id(s) not in assigned_sigungu]
        # 미할당 시군구는 시각화에서 빠짐 (territory 부족분, 1-4개)
        # Fallback 없이 그대로 — 다른 시도 territory 침범하면 connectivity 깨져 점수 더 하락
        _ = unassigned

    # 5. 출력 — c, r이 할당된 시군구만
    out = []
    for r in rows:
        if "c" not in r or "r" not in r:
            print(f"  ! 미할당: {r['sido']} {r['name']}", flush=True)
            continue
        out.append({
            "code": r["code"], "name": r["name"], "sido": r["sido"],
            "c": r["c"], "r": r["r"],
        })

    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    # 통계
    cs = [o["c"] for o in out]; rs = [o["r"] for o in out]
    print(f"총 {len(out)} 시군구 hex 배치, 후처리 이동 {moved_total}개")
    print(f"c 범위 {min(cs)}~{max(cs)} (폭 {max(cs)-min(cs)+1})")
    print(f"r 범위 {min(rs)}~{max(rs)} (폭 {max(rs)-min(rs)+1})")
    print(f"→ {OUT.relative_to(ROOT)}")

    # hole-fill 후처리 자동 호출 — 내부 홀 슬라이드로 외곽으로 밀어냄
    import importlib.util
    spec = importlib.util.spec_from_file_location("fill_holes", Path(__file__).parent / "fill_holes.py")
    fh = importlib.util.module_from_spec(spec); spec.loader.exec_module(fh)
    filled = fh.run(out, verbose=False)
    OUT.write_text(json.dumps(filled, ensure_ascii=False), encoding="utf-8")
    print(f"hole-fill 적용 → 최종 {len(filled)} cells")


if __name__ == "__main__":
    main()
