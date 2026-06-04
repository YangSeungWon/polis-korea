"""시군구 hex 배치 품질 평가 (강화 버전).

지표:
1. 시도 cluster 연결성 (30)
2. 시도 간 인접 F1 (15) — 시도 단위
3. 시도 centroid 위상 보존 (10) — 시도 단위 Spearman
4. 시군구 polygon 인접 F1 (25) — 시군구 단위 (sigungu_adjacency.json ground truth)
5. 시군구 위상 보존 (10) — 시군구 단위 Spearman
6. Hard tests (10) — 명시적 케이스 (부천>인천, 양양>홍천 등)

총점: 100
"""
from __future__ import annotations
import json
import math
from collections import defaultdict, deque
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _geo import sigungu_to_sido  # noqa
from _hex import offset_neighbors, polygon_centroid  # noqa

ROOT = Path(__file__).resolve().parents[2]
HEX = ROOT / "data" / "geo" / "sigungu_hex.json"
SIGUNGU = ROOT / "data" / "geo" / "sigungu_simple.json"
ADJ = ROOT / "data" / "geo" / "sigungu_adjacency.json"

GROUND_TRUTH_ADJ = {
    '서울특별시': {'인천광역시', '경기도'},
    '인천광역시': {'서울특별시', '경기도'},
    '경기도': {'서울특별시', '인천광역시', '강원특별자치도', '충청북도', '충청남도'},
    '강원특별자치도': {'경기도', '충청북도', '경상북도'},
    '충청북도': {'경기도', '강원특별자치도', '충청남도', '세종특별자치시', '대전광역시', '경상북도', '전북특별자치도'},
    '충청남도': {'경기도', '충청북도', '세종특별자치시', '대전광역시', '전북특별자치도'},
    '세종특별자치시': {'충청북도', '충청남도', '대전광역시'},
    '대전광역시': {'충청북도', '충청남도', '세종특별자치시', '전북특별자치도'},
    '경상북도': {'강원특별자치도', '충청북도', '대구광역시', '울산광역시', '경상남도'},
    '대구광역시': {'경상북도'},
    '울산광역시': {'경상북도', '경상남도', '부산광역시'},
    '부산광역시': {'울산광역시', '경상남도'},
    '경상남도': {'경상북도', '대구광역시', '울산광역시', '부산광역시', '전라남도', '전북특별자치도'},
    '전북특별자치도': {'충청북도', '충청남도', '대전광역시', '경상남도', '전라남도'},
    '광주광역시': {'전라남도'},
    '전라남도': {'전북특별자치도', '광주광역시', '경상남도', '제주특별자치도'},
    '제주특별자치도': {'전라남도'},
}

# Hard tests — 사용자가 지적한 명확한 위상 케이스
# (조건 설명, 통과 검사 함수)
def make_hard_tests(by_name):
    """by_name: {name: {sido, c, r}} dict."""
    def get(n, k):
        x = by_name.get(n)
        return x[k] if x else None

    tests = []
    # 부천·시흥은 인천 본토 시군구 (옹진 제외) max c보다 동쪽
    inch_mainland_max_c = max(
        (v['c'] for k, v in by_name.items()
         if v['sido'] == '인천광역시' and k != '옹진군'),
        default=None,
    )
    tests.append(("부천 > 인천 본토",
                  get('부천시', 'c') is not None and inch_mainland_max_c is not None
                  and get('부천시', 'c') >= inch_mainland_max_c))
    tests.append(("시흥 > 인천 본토",
                  get('시흥시', 'c') is not None and inch_mainland_max_c is not None
                  and get('시흥시', 'c') >= inch_mainland_max_c))
    # 양양은 홍천보다 동쪽 (c 큼) + 북쪽 (r 작음)
    tests.append(("양양 c > 홍천 c",
                  get('양양군', 'c') is not None and get('홍천군', 'c') is not None
                  and get('양양군', 'c') > get('홍천군', 'c')))
    tests.append(("양양 r ≤ 홍천 r (북쪽)",
                  get('양양군', 'r') is not None and get('홍천군', 'r') is not None
                  and get('양양군', 'r') <= get('홍천군', 'r')))
    # 포항 북구-남구 인접
    pn = by_name.get('포항시북구'); ps = by_name.get('포항시남구')
    if pn and ps:
        d = abs(pn['c'] - ps['c']) + abs(pn['r'] - ps['r'])
        tests.append(("포항북구↔남구 인접", d <= 2))
    else:
        tests.append(("포항북구↔남구 인접", False))
    # 제주시 r < 서귀포시 r (제주가 북쪽)
    tests.append(("제주 r < 서귀포 r",
                  get('제주시', 'r') is not None and get('서귀포시', 'r') is not None
                  and get('제주시', 'r') < get('서귀포시', 'r')))
    # 강릉시는 동해 동쪽 — 홍천보다 c 큼
    tests.append(("강릉 c > 홍천 c",
                  get('강릉시', 'c') is not None and get('홍천군', 'c') is not None
                  and get('강릉시', 'c') > get('홍천군', 'c')))
    # 김포는 부천보다 북쪽 (lat 더 큼 → r 작음)
    tests.append(("김포 r < 부천 r",
                  get('김포시', 'r') is not None and get('부천시', 'r') is not None
                  and get('김포시', 'r') < get('부천시', 'r')))
    return tests


def hex_dist(a, b):
    """offset → cube → hex distance."""
    def to_cube(c, r):
        x = c - (r - (r & 1)) // 2
        z = r
        y = -x - z
        return x, y, z
    ax, ay, az = to_cube(*a)
    bx, by, bz = to_cube(*b)
    return (abs(ax - bx) + abs(ay - by) + abs(az - bz)) // 2


# offset_neighbors·polygon_centroid → _hex.py (공용)


def spearman(a, b):
    n = len(a)
    def rank(xs):
        srt = sorted(range(len(xs)), key=lambda i: xs[i])
        ranks = [0.0] * len(xs)
        for r, idx in enumerate(srt):
            ranks[idx] = float(r)
        return ranks
    ra, rb = rank(a), rank(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((x - mb) ** 2 for x in rb))
    return num / (da * db) if da and db else 0


_geo_cache = None
_adj_cache = None
_centroid_cache = None


def _load_geo():
    global _geo_cache, _adj_cache, _centroid_cache
    if _geo_cache is None:
        _geo_cache = json.loads(SIGUNGU.read_text())
        _adj_cache = json.loads(ADJ.read_text())
        _centroid_cache = {}
        for feat in _geo_cache["features"]:
            code = feat["properties"]["code"]
            _centroid_cache[code] = polygon_centroid(feat["geometry"])
    return _geo_cache, _adj_cache, _centroid_cache


def evaluate(hex_data=None, verbose=False):
    """hex 배치 평가. hex_data 없으면 파일에서 로드. dict로 점수 반환."""
    if hex_data is None:
        hex_data = json.loads(HEX.read_text())
    geo_data, adj_data, centroid_by_code = _load_geo()

    by_code = {o["code"]: o for o in hex_data}
    by_name = {o["name"]: o for o in hex_data}
    by_sido_cells = defaultdict(set)
    for h in hex_data:
        by_sido_cells[h["sido"]].add((h["c"], h["r"]))

    # 1. 연결성
    n_disconnected = 0
    for sido, cells in by_sido_cells.items():
        if len(cells) <= 1:
            continue
        start = next(iter(cells)); visited = {start}; q = deque([start])
        while q:
            x = q.popleft()
            for nb in offset_neighbors(*x):
                if nb in cells and nb not in visited:
                    visited.add(nb); q.append(nb)
        if len(visited) != len(cells):
            n_disconnected += 1
    sc_conn = 30 if n_disconnected == 0 else 0

    # 2. 시도 인접 F1
    actual_adj_sido = defaultdict(set)
    for sido, cells in by_sido_cells.items():
        for c in cells:
            for nb in offset_neighbors(*c):
                for other, ocells in by_sido_cells.items():
                    if other != sido and nb in ocells:
                        actual_adj_sido[sido].add(other)
    tp = fp = fn = 0
    for sido, truth in GROUND_TRUTH_ADJ.items():
        actual = actual_adj_sido.get(sido, set())
        tp += len(actual & truth); fp += len(actual - truth); fn += len(truth - actual)
    tp //= 2; fp //= 2; fn //= 2
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
    sc_sido_adj = int(f1 * 15)

    # 3. 시도 centroid Spearman
    geo_sido_centroid = defaultdict(list)
    for code, ctr in centroid_by_code.items():
        h = by_code.get(code)
        if h:
            geo_sido_centroid[h["sido"]].append(ctr)
    geo_sido = {s: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
                for s, pts in geo_sido_centroid.items()}
    hex_sido = {}
    for sido, cells in by_sido_cells.items():
        xs = [c + (0.5 if r % 2 else 0) for c, r in cells]
        ys = [r * (math.sqrt(3) / 2) for _, r in cells]
        hex_sido[sido] = (sum(xs) / len(xs), sum(ys) / len(ys))
    sidos = sorted(set(geo_sido) & set(hex_sido))
    if sidos:
        rx = spearman([geo_sido[s][0] for s in sidos], [hex_sido[s][0] for s in sidos])
        ry = spearman([geo_sido[s][1] for s in sidos], [hex_sido[s][1] for s in sidos])
        sc_sido_topo = int((max(0, rx) + max(0, -ry)) / 2 * 10)
    else:
        sc_sido_topo = 0

    # 4. 시군구 인접 F1
    truth_pairs = set()
    for p in adj_data["pairs"]:
        truth_pairs.add(tuple(sorted([p["a"], p["b"]])))
    cell_to_code = {(h["c"], h["r"]): h["code"] for h in hex_data}
    actual_pairs = set()
    for code, h in by_code.items():
        cell = (h["c"], h["r"])
        for nb in offset_neighbors(*cell):
            ocode = cell_to_code.get(nb)
            if ocode and ocode != code:
                actual_pairs.add(tuple(sorted([code, ocode])))
    tp2 = len(actual_pairs & truth_pairs)
    fp2 = len(actual_pairs - truth_pairs)
    fn2 = len(truth_pairs - actual_pairs)
    prec2 = tp2 / (tp2 + fp2) if (tp2 + fp2) else 0
    rec2 = tp2 / (tp2 + fn2) if (tp2 + fn2) else 0
    f1_sg = 2 * prec2 * rec2 / (prec2 + rec2) if (prec2 + rec2) else 0
    sc_sg_adj = int(f1_sg * 25)

    # 5. 시군구 위상
    rows = []
    for code, h in by_code.items():
        ctr = centroid_by_code.get(code)
        if not ctr:
            continue
        x = h["c"] + (0.5 if h["r"] % 2 else 0)
        y = h["r"] * (math.sqrt(3) / 2)
        rows.append((ctr[0], ctr[1], x, y))
    if rows:
        rx2 = spearman([r[0] for r in rows], [r[2] for r in rows])
        ry2 = spearman([r[1] for r in rows], [r[3] for r in rows])
        sc_sg_topo = int((max(0, rx2) + max(0, -ry2)) / 2 * 10)
    else:
        sc_sg_topo = 0

    # 6. Hole
    occupied_cells = set((o["c"], o["r"]) for o in hex_data if o["sido"] != "제주특별자치도")
    n_holes = 0
    if occupied_cells:
        min_c_g = min(c for c, _ in occupied_cells); max_c_g = max(c for c, _ in occupied_cells)
        min_r_g = min(r for _, r in occupied_cells); max_r_g = max(r for _, r in occupied_cells)
        for rr in range(min_r_g, max_r_g + 1):
            for cc in range(min_c_g, max_c_g + 1):
                if (cc, rr) in occupied_cells:
                    continue
                if sum(1 for n in offset_neighbors(cc, rr) if n in occupied_cells) >= 4:
                    n_holes += 1
    sc_hole = max(0, 10 - n_holes)

    # 7. Ordering
    ord_total = 0; ord_ok = 0
    for a, b in truth_pairs:
        ca = centroid_by_code.get(a); cb = centroid_by_code.get(b)
        ha = by_code.get(a); hb = by_code.get(b)
        if not (ca and cb and ha and hb):
            continue
        if (ca[0] > cb[0]) == (ha["c"] > hb["c"]):
            ord_ok += 1
        if (ca[1] > cb[1]) == (ha["r"] < hb["r"]):
            ord_ok += 1
        ord_total += 2
    sc_order = int((ord_ok / ord_total if ord_total else 0) * 10)

    # 8. Hard tests
    tests = make_hard_tests(by_name)
    passed = sum(1 for _, ok in tests if ok)
    sc_hard = int(passed / len(tests) * 10) if tests else 0

    total = sc_conn + sc_sido_adj + sc_sido_topo + sc_sg_adj + sc_sg_topo + sc_hole + sc_order + sc_hard
    scores = {
        "conn": sc_conn, "sido_adj": sc_sido_adj, "sido_topo": sc_sido_topo,
        "sg_adj": sc_sg_adj, "sg_topo": sc_sg_topo, "hole": sc_hole,
        "order": sc_order, "hard": sc_hard, "total": total,
        "n_holes": n_holes, "hard_pass": passed, "hard_total": len(tests),
    }
    if verbose:
        print(f"연결성 {sc_conn} | 시도인접 {sc_sido_adj} | 시도위상 {sc_sido_topo}")
        print(f"시군구인접 {sc_sg_adj} | 시군구위상 {sc_sg_topo}")
        print(f"hole {sc_hole}({n_holes}개) | ordering {sc_order} | Hard {sc_hard}({passed}/{len(tests)})")
        print(f"= {total}/120")
    return scores


def main():
    hex_data = json.loads(HEX.read_text())
    geo_data = json.loads(SIGUNGU.read_text())
    adj_data = json.loads(ADJ.read_text())

    # 시군구 정보 dicts
    by_code = {o["code"]: o for o in hex_data}
    by_name = {o["name"]: o for o in hex_data}

    # 시군구 centroid
    centroid_by_code = {}
    for feat in geo_data["features"]:
        code = feat["properties"]["code"]
        centroid_by_code[code] = polygon_centroid(feat["geometry"])

    # 시도별 cells
    by_sido_cells = defaultdict(set)
    for h in hex_data:
        by_sido_cells[h["sido"]].add((h["c"], h["r"]))

    # === 1. 시도 cluster 연결성 (30) ===
    print("== 1. 시도 cluster 연결성 ==")
    n_disconnected = 0
    for sido, cells in by_sido_cells.items():
        if len(cells) <= 1:
            continue
        start = next(iter(cells))
        visited = {start}
        q = deque([start])
        while q:
            x = q.popleft()
            for nb in offset_neighbors(*x):
                if nb in cells and nb not in visited:
                    visited.add(nb); q.append(nb)
        if len(visited) != len(cells):
            n_disconnected += 1
            print(f"  ✗ {sido} {len(visited)}/{len(cells)}")
    sc_conn = 30 if n_disconnected == 0 else 0
    print(f"  ✓ 점수: {sc_conn}/30" if n_disconnected == 0 else f"  점수: {sc_conn}/30")

    # === 2. 시도 인접 F1 (15) ===
    print("\n== 2. 시도 간 인접 (시도 단위) ==")
    actual_adj_sido = defaultdict(set)
    for sido, cells in by_sido_cells.items():
        for c in cells:
            for nb in offset_neighbors(*c):
                for other, ocells in by_sido_cells.items():
                    if other != sido and nb in ocells:
                        actual_adj_sido[sido].add(other)
    tp = fp = fn = 0
    for sido, truth in GROUND_TRUTH_ADJ.items():
        actual = actual_adj_sido.get(sido, set())
        tp += len(actual & truth); fp += len(actual - truth); fn += len(truth - actual)
    tp //= 2; fp //= 2; fn //= 2
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    f1_sido = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
    sc_sido_adj = int(f1_sido * 15)
    print(f"  F1 {f1_sido:.2%} → {sc_sido_adj}/15")

    # === 3. 시도 centroid Spearman (10) ===
    geo_sido_centroid = defaultdict(list)
    for code, ctr in centroid_by_code.items():
        h = by_code.get(code)
        if h:
            geo_sido_centroid[h["sido"]].append(ctr)
    geo_sido = {s: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
                for s, pts in geo_sido_centroid.items()}
    hex_sido = {}
    for sido, cells in by_sido_cells.items():
        xs = [c + (0.5 if r % 2 else 0) for c, r in cells]
        ys = [r * (math.sqrt(3) / 2) for _, r in cells]
        hex_sido[sido] = (sum(xs) / len(xs), sum(ys) / len(ys))
    sidos = sorted(set(geo_sido) & set(hex_sido))
    lons = [geo_sido[s][0] for s in sidos]
    lats = [geo_sido[s][1] for s in sidos]
    cs = [hex_sido[s][0] for s in sidos]
    rs = [hex_sido[s][1] for s in sidos]
    rho_x = spearman(lons, cs)
    rho_y = spearman(lats, rs)
    topo_sido = (max(0, rho_x) + max(0, -rho_y)) / 2
    sc_sido_topo = int(topo_sido * 10)
    print(f"\n== 3. 시도 위상 == lon→col {rho_x:+.3f} lat→row {rho_y:+.3f} → {sc_sido_topo}/10")

    # === 4. 시군구 polygon 인접 F1 (25) ===
    print("\n== 4. 시군구 polygon 인접 ==")
    truth_pairs = set()
    for p in adj_data["pairs"]:
        truth_pairs.add(tuple(sorted([p["a"], p["b"]])))

    actual_pairs = set()
    for code, h in by_code.items():
        cell = (h["c"], h["r"])
        for nb in offset_neighbors(*cell):
            for ocode, oh in by_code.items():
                if (oh["c"], oh["r"]) == nb and ocode != code:
                    actual_pairs.add(tuple(sorted([code, ocode])))

    tp = len(actual_pairs & truth_pairs)
    fp = len(actual_pairs - truth_pairs)
    fn = len(truth_pairs - actual_pairs)
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    f1_sg = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
    sc_sg_adj = int(f1_sg * 25)
    print(f"  매칭 {tp}, 누락 {fn}, 잘못 {fp}  F1 {f1_sg:.2%} → {sc_sg_adj}/25")

    # === 5. 시군구 위상 Spearman (10) ===
    print("\n== 5. 시군구 위상 ==")
    rows = []
    for code, h in by_code.items():
        ctr = centroid_by_code.get(code)
        if not ctr:
            continue
        x = h["c"] + (0.5 if h["r"] % 2 else 0)
        y = h["r"] * (math.sqrt(3) / 2)
        rows.append((ctr[0], ctr[1], x, y))
    lons = [r[0] for r in rows]
    lats = [r[1] for r in rows]
    cs = [r[2] for r in rows]
    rs = [r[3] for r in rows]
    rx = spearman(lons, cs)
    ry = spearman(lats, rs)
    topo_sg = (max(0, rx) + max(0, -ry)) / 2
    sc_sg_topo = int(topo_sg * 10)
    print(f"  lon→c {rx:+.3f}  lat→r {ry:+.3f} → {sc_sg_topo}/10")

    # === 6. Hole penalty (10) — 그리드 안 빈칸 (인접 4+ occupied) ===
    print("\n== 6. 그리드 hole ==")
    occupied_cells = set((o["c"], o["r"]) for o in hex_data if o["sido"] != "제주특별자치도")
    if occupied_cells:
        min_c_g = min(c for c, _ in occupied_cells)
        max_c_g = max(c for c, _ in occupied_cells)
        min_r_g = min(r for _, r in occupied_cells)
        max_r_g = max(r for _, r in occupied_cells)
        n_holes = 0
        for rr in range(min_r_g, max_r_g + 1):
            for cc in range(min_c_g, max_c_g + 1):
                if (cc, rr) in occupied_cells:
                    continue
                nbrs = offset_neighbors(cc, rr)
                occ_nb = sum(1 for n in nbrs if n in occupied_cells)
                if occ_nb >= 4:
                    n_holes += 1
        # 0 holes = 10점, 많을수록 감점 (10개 이상 = 0점)
        sc_hole = max(0, 10 - n_holes)
        print(f"  hole {n_holes} → {sc_hole}/10")
    else:
        sc_hole = 0

    # === 7. 인접 시군구 ordering 보존 (10) — 동/서/북/남 순서 ===
    print("\n== 7. 인접 시군구 ordering ==")
    truth_pairs = set()
    for p in adj_data["pairs"]:
        truth_pairs.add(tuple(sorted([p["a"], p["b"]])))
    ord_total = 0; ord_ok = 0
    for a, b in truth_pairs:
        ca = centroid_by_code.get(a); cb = centroid_by_code.get(b)
        ha = by_code.get(a); hb = by_code.get(b)
        if not (ca and cb and ha and hb):
            continue
        # 동/서 (lon): a 동(lon 큼) → a c 큼
        g_east = ca[0] > cb[0]
        h_east = ha["c"] > hb["c"]
        # 북/남 (lat): a 북(lat 큼) → a r 작음
        g_north = ca[1] > cb[1]
        h_north = ha["r"] < hb["r"]
        if g_east == h_east:
            ord_ok += 1
        if g_north == h_north:
            ord_ok += 1
        ord_total += 2
    ord_ratio = ord_ok / ord_total if ord_total else 0
    sc_order = int(ord_ratio * 10)
    print(f"  ordering 맞음 {ord_ok}/{ord_total} ({ord_ratio:.1%}) → {sc_order}/10")

    # === 8. Hard tests (10) ===
    print("\n== 6. Hard tests ==")
    tests = make_hard_tests(by_name)
    passed = 0
    for desc, ok in tests:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {desc}")
        if ok:
            passed += 1
    sc_hard = int(passed / len(tests) * 10) if tests else 0
    print(f"  {passed}/{len(tests)} → {sc_hard}/10")

    total = sc_conn + sc_sido_adj + sc_sido_topo + sc_sg_adj + sc_sg_topo + sc_hole + sc_order + sc_hard
    print(f"\n== 종합 ==")
    print(f"  연결성 {sc_conn} + 시도인접 {sc_sido_adj} + 시도위상 {sc_sido_topo}")
    print(f"  + 시군구인접 {sc_sg_adj} + 시군구위상 {sc_sg_topo}")
    print(f"  + hole {sc_hole} + ordering {sc_order} + Hard {sc_hard}")
    print(f"  = {total}/120")


if __name__ == "__main__":
    main()
