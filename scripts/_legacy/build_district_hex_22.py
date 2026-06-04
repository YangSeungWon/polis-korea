"""총선 N대 지역구 hex layout 빌더 (회차 generic).

사용:
  .venv/bin/python scripts/_legacy/build_district_hex_22.py        # 22대 (기본)
  .venv/bin/python scripts/_legacy/build_district_hex_22.py 20     # 20대

알고리즘:
1. 각 지역구의 관할 시군구 추출 (지역구명 patterns 매칭)
2. 지역구 centroid = 관할 시군구들의 hex 좌표 평균
3. build_sigungu_hex.py 의 anchor + round-robin BFS + Hungarian 차용
4. fill_holes.py 후처리

출력: data/geo/district_hex_N.json
"""
from __future__ import annotations
import argparse
import json
import math
import re
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


# 통합 시명 → 분할 구 alias (시군구 hex가 일반구 단위로만 있는 경우)
PARENT_TO_CHILDREN = {
    ('전북특별자치도', '전주시'): ['전주시완산구', '전주시덕진구'],
    ('충청남도', '천안시'): ['천안시동남구', '천안시서북구'],
    ('경기도', '용인시'): ['용인시처인구', '용인시기흥구', '용인시수지구'],
    ('경기도', '고양시'): ['고양시덕양구', '고양시일산동구', '고양시일산서구'],
    ('경기도', '수원시'): ['수원시장안구', '수원시권선구', '수원시팔달구', '수원시영통구'],
    ('경기도', '안산시'): ['안산시상록구', '안산시단원구'],
    ('경기도', '성남시'): ['성남시수정구', '성남시중원구', '성남시분당구'],
    ('경기도', '안양시'): ['안양시만안구', '안양시동안구'],
    ('경상남도', '창원시'): ['창원시의창구', '창원시성산구', '창원시마산합포구', '창원시마산회원구', '창원시진해구'],
    ('경상북도', '포항시'): ['포항시남구', '포항시북구'],
    ('충청북도', '청주시'): ['청주시상당구', '청주시서원구', '청주시흥덕구', '청주시청원구'],
}

# 지역구명에 사용되는 시군구 이름 → hex 시군구 alias
SGG_ALIAS = {
    ('인천광역시', '미추홀구'): '남구',  # 2018 개명 (hex는 옛 이름)
    # 옛 회차 시군구 (현 hex 이름과 다름)
    ('경기도', '여주군'): '여주시',        # 2013 시 승격
    ('충청북도', '청원군'): '청주시청원구',  # 2014 청주 통합
    ('충청남도', '연기군'): '세종시',       # 2012 세종 출범
    ('충청남도', '당진군'): '당진시',       # 2012 시 승격
    # 17·18대 옛 시군구 (이후 통합·폐지)
    ('제주특별자치도', '북제주군'): '제주시',
    ('제주특별자치도', '남제주군'): '서귀포시',
    ('경기도', '고양시일산구'): '고양시일산서구',   # 17대 (이후 일산동·서로 분할)
    ('경상남도', '마산시'): '창원시마산합포구',     # 2010 창원 통합
    ('경상남도', '진해시'): '창원시진해구',
}

# 세종특별자치시 자체: '세종특별자치시갑/을' → 세종시
SIDO_AS_SGG = {
    '세종특별자치시': '세종시',
}

# Manual 시도 anchor — 한반도 형상 손수 배치.
# 인천이 서울 왼쪽 위, 강원이 경기 오른쪽, 남부지방 (호남+영남+제주) 중부 아래 다닥다닥.
# 지역구 수에 따라 cluster가 자연스럽게 grow 하므로 시도간 간격은 적당히 띄움.
SIDO_ANCHOR_MANUAL = {
    # 수도권 — 서울+경기 통합 (서울 가운데, 경기 둘레), 인천 별도 (왼쪽 위)
    '인천광역시':     (-2, -1),
    '서울특별시':     (5,   2),
    '경기도':         (5,   2),
    '강원특별자치도': (15, -2),    # 동북 끝 — 세로로 길게 자라도록
    # 충청 — 중부 가운데
    '충청남도':       (4,   6),
    '세종특별자치시': (7,   6),
    '충청북도':       (9,   5),    # 강원 (c=9) 아래, 경북(c=10,11) 왼쪽
    '대전광역시':     (6,   8),
    # 영남 동북 — 대구 왼쪽, 경북은 manual로 강원 우측 strip
    '대구광역시':     (9,  10),    # 경북 manual strip 아래
    '경상북도':       (11,  5),    # manual로 처리 — anchor 자체는 사용 안 함
    # 영남 남부 — 별도 cluster. 부산이 왼쪽, 울산 그 위, 경남 부산 옆에서 짜부
    '경상남도':       (9,  12),    # 짜부 — 부산이 옆에서 누름
    '울산광역시':     (13, 10),    # 동쪽
    '부산광역시':     (11, 13),    # 왼쪽으로 — 경남 짜부시키고 동해안에서 떨어짐
    # 호남 — 전북 위, 광주 가운데, 전남 광주 남·서로 별도 cluster
    '전북특별자치도': (5,   9),
    '광주광역시':     (6,  13),
    '전라남도':       (4,  14),    # 광주 남서 — 별도 cluster
    # 제주
    '제주특별자치도': (8,  16),
}

# 통합 grow할 시도 그룹 — anchor가 같거나 인접해도 separate cluster 안 되고
# 한 cluster로 자란 후 Hungarian으로 시도별 cell 분리
SIDO_MERGE_GROUPS = [
    {'서울특별시', '경기도'},                          # 서울 inner, 경기 둘레. 인천 별도.
    # 경북·대구·울산·부산·경남·전남·광주: 통합 안 함 — 각자 별도 anchor
]

# 시도별 manual cell shape — Phase 0에서 pre-place. BFS·pull-in 모두 skip.
# 회차마다 district 수 다를 수 있으니, 정확한 수만큼만 사용 (앞부터).
# 강원: 동해안 따라 2-wide 세로 strip
SIDO_CELLS_MANUAL = {
    # 강원: top cell (8,-5)이 경기와 인접 (경기 r=-5 c=7 옆), 나머지는 col 9 strip
    '강원특별자치도': [
        (8, -5),
        (9, -5), (9, -4), (9, -3), (9, -2),
        (9, -1), (9,  0), (9,  1),
        (9,  2), (9,  3),  # 19대 9~10 districts용 여분
    ],
    # 경북: 2-wide 세로 c=10,11 — 강원 c=9 strip 우측. 충북 (c=9 r=3~6) 자리 확보.
    '경상북도': [
        (10, 3), (11, 3),
        (10, 4), (11, 4),
        (10, 5), (11, 5),
        (10, 6), (11, 6),
        (10, 7), (11, 7),
        (10, 8), (11, 8),
        (11, 9),
        (10, 9), (11, 10), (11, 11),  # 19대 15 cells용 여분
    ],
    # 제주: 한반도와 한 row 떨어뜨림 (전남 마지막 row r=16 → 제주 r=18)
    '제주특별자치도': [
        (5, 18), (6, 18), (7, 18),
    ],
    # 대구: 경북 strip(c=10,11) 아래·서쪽. 12 cells trapezoid.
    '대구광역시': [
        (9, 8),  (10, 8),
        (8, 9),  (9, 9),  (10, 9),
        (8, 10), (9, 10), (10, 10),
        (8, 11), (9, 11), (10, 11),
        (8, 12),  # 19대 등 여분
        (9, 12), (10, 12),
    ],
}


def parse_district_name(sido: str, name: str, sgg_by_sido: dict) -> list[str]:
    """지역구명에서 관할 시군구 추출.
    '원주시갑' → ['원주시']
    '동해시태백시삼척시정선군' → ['동해시','태백시','삼척시','정선군']
    '청주시상당구' → ['청주시상당구']
    '동구미추홀구갑' (인천) → ['동구','미추홀구']
    '전주시갑' → ['전주시완산구','전주시덕진구'] (통합 시명 alias)
    """
    # 분할 suffix (갑/을/병/정/무) 제거 + 구분자 (·, +, ,) 제거 (17·18대 형식)
    s = re.sub(r'[갑을병정무]$', '', name)
    s = re.sub(r'[·,+]', '', s)
    # 세종 광역시 자체 → 세종시 매핑
    if s == sido and sido in SIDO_AS_SGG:
        return [SIDO_AS_SGG[sido]]
    if s == sido:
        return [s]
    # 통합 시명 alias
    alias = PARENT_TO_CHILDREN.get((sido, s))
    if alias:
        return list(alias)
    candidates = sgg_by_sido.get(sido, set())
    # 광주·대구·인천의 통합 선거구는 다른 시도 시군구 (예: 대구 동구+군위군) 인 경우도 있어
    # 일단 같은 시도 안에서 greedy 매칭, 못 찾으면 전체 시군구에서
    all_candidates = set()
    for ss in sgg_by_sido.values():
        all_candidates |= ss

    result = []
    remaining = s
    while remaining:
        # 가장 긴 매칭 우선
        matched = None
        for sgg in sorted(candidates, key=len, reverse=True):
            if remaining.startswith(sgg):
                matched = sgg
                break
        if not matched:
            # 다른 시도 시군구에서 (예: 대구 동구+군위군 같은 통합)
            for sgg in sorted(all_candidates, key=len, reverse=True):
                if remaining.startswith(sgg):
                    matched = sgg
                    break
        if matched:
            # 옛 이름 alias 적용
            mapped = SGG_ALIAS.get((sido, matched), matched)
            result.append(mapped)
            remaining = remaining[len(matched):]
        else:
            # 매칭 실패 — leftover 남겨두고 stop
            print(f'  ! "{sido} {name}": "{remaining}" 매칭 실패. 부분 결과 {result}', file=sys.stderr)
            break
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('n', type=int, nargs='?', default=22, help='회차 (기본 22)')
    ap.add_argument('--anchor-scale', type=float, default=1.3,
                    help='시도 anchor 사이 거리 scale factor (--anchor-mode auto 일 때만)')
    ap.add_argument('--anchor-mode', choices=['auto', 'manual'], default='manual',
                    help='auto=시군구 centroid에 scale, manual=SIDO_ANCHOR_MANUAL dict (한반도 손수 배치)')
    args = ap.parse_args()
    n = args.n
    DISTRICT_META = ROOT / f"data/geo/district_{n}_centroid.json"
    OUT = ROOT / f"data/geo/district_hex_{n}.json"

    # 시군구 데이터 + centroid
    hex_data = json.loads(SIGUNGU_HEX.read_text(encoding='utf-8'))
    geo = json.loads(SIGUNGU_GEO.read_text(encoding='utf-8'))

    sgg_centroid_geo = {}  # (sido, name) → (lon, lat)
    sgg_by_code = {}
    for feat in geo['features']:
        code = feat['properties']['code']
        sido = sigungu_to_sido(code)
        name = feat['properties']['name']
        if sido and name:
            sgg_centroid_geo[(sido, name)] = polygon_centroid(feat['geometry'])
            sgg_by_code[code] = (sido, name)

    sgg_hex_pos = {}  # (sido, name) → (c, r)
    sgg_by_sido = defaultdict(set)
    for h in hex_data:
        sgg_hex_pos[(h['sido'], h['name'])] = (h['c'], h['r'])
        sgg_by_sido[h['sido']].add(h['name'])
    # 옛 이름 alias도 매칭 후보에 추가 (예: 인천 미추홀구 → 인천 남구)
    for (sido, old_name), new_name in SGG_ALIAS.items():
        sgg_by_sido[sido].add(old_name)

    # 지역구 메타
    districts = json.loads(DISTRICT_META.read_text(encoding='utf-8'))

    # 각 지역구 → 관할 시군구 → centroid
    district_info = []
    for d in districts:
        sido, name = d['sido'], d['name']
        sgg_list = parse_district_name(sido, name, sgg_by_sido)
        if not sgg_list:
            print(f'  X 시군구 매칭 실패: {sido} {name}', file=sys.stderr)
            continue
        # centroid = 관할 시군구 polygon centroid 평균 (지리 좌표)
        lons, lats = [], []
        hex_xs, hex_ys = [], []
        for sgg in sgg_list:
            ctr = sgg_centroid_geo.get((sido, sgg))
            if ctr is None:
                # 다른 시도 시군구 검색
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

    # 시도별 group
    by_sido = defaultdict(list)
    for d in district_info:
        by_sido[d['sido']].append(d)

    # 시도 anchor 결정
    sido_anchor = {}
    if args.anchor_mode == 'manual':
        for sido in by_sido:
            if sido in SIDO_ANCHOR_MANUAL:
                sido_anchor[sido] = SIDO_ANCHOR_MANUAL[sido]
            else:
                print(f'  ! manual anchor 누락: {sido} → fallback (0,0)', file=sys.stderr)
                sido_anchor[sido] = (0, 0)
    else:
        # auto: 시군구 hex centroid + scale
        sido_cells_existing = defaultdict(list)
        for h in hex_data:
            sido_cells_existing[h['sido']].append((h['c'], h['r']))
        all_cs, all_rs = [], []
        for cells in sido_cells_existing.values():
            for c, r in cells:
                all_cs.append(c); all_rs.append(r)
        overall_cx = sum(all_cs) / len(all_cs)
        overall_cy = sum(all_rs) / len(all_rs)
        scale = args.anchor_scale
        for sido, cells in sido_cells_existing.items():
            cx = sum(c for c, r in cells) / len(cells)
            cy = sum(r for c, r in cells) / len(cells)
            scaled_cx = overall_cx + (cx - overall_cx) * scale
            scaled_cy = overall_cy + (cy - overall_cy) * scale
            sido_anchor[sido] = (round(scaled_cx), round(scaled_cy))

    # anchor 충돌 — 큰 시도 먼저
    sorted_sidos = sorted(by_sido, key=lambda s: -len(by_sido[s]))
    anchor_occupied = {}
    for sido in sorted_sidos:
        a = sido_anchor.get(sido)
        if a is None: continue
        if a not in anchor_occupied:
            anchor_occupied[a] = sido
        else:
            # spiral
            visited = {a}; q = deque([a])
            while q:
                x = q.popleft()
                for nb in offset_neighbors(*x):
                    if nb in visited: continue
                    visited.add(nb)
                    if nb not in anchor_occupied:
                        sido_anchor[sido] = nb
                        anchor_occupied[nb] = sido
                        q.clear(); break
                    q.append(nb)
                if sido_anchor[sido] != a: break

    # 통합 grow group 처리: 같은 그룹은 super-sido로 묶어서 한 cluster로 자람.
    # 예: {서울, 경기} → 같은 anchor, 합쳐서 grow → Hungarian 시 시도별 분리.
    sido_to_group = {}
    for grp in SIDO_MERGE_GROUPS:
        for s in grp:
            sido_to_group[s] = frozenset(grp)
    # 시도 → group key (자기 자신이 키 또는 frozenset 그룹)
    def group_of(s):
        return sido_to_group.get(s, frozenset({s}))

    # 라운드로빈 BFS: 시도별로 cell 추가. 통합 group은 한 super-territory.
    targets = {s: len(by_sido[s]) for s in by_sido}
    territories = {s: set() for s in by_sido}
    occupied = {}

    # Phase 0: manual cell shape를 가진 시도는 미리 점유 (BFS·pull-in 제외)
    manual_sidos = set()
    for sido, cells_list in SIDO_CELLS_MANUAL.items():
        if sido not in by_sido: continue
        n = len(by_sido[sido])
        if len(cells_list) < n:
            print(f'  ! {sido} manual cells {len(cells_list)} < districts {n}', file=sys.stderr)
            continue
        chosen = cells_list[:n]
        territories[sido] = set(chosen)
        for c in chosen:
            occupied[c] = sido
        manual_sidos.add(sido)

    # group 단위 cells (서울+경기 합친 cluster)
    group_cells = {}  # group_key → set of cells
    for sido, anchor in sido_anchor.items():
        if sido not in by_sido: continue
        if sido in manual_sidos: continue  # manual은 BFS 건너뜀
        gkey = group_of(sido)
        if gkey not in group_cells:
            group_cells[gkey] = {anchor}
            # 첫 시도가 anchor 점유 (충돌 시 그룹의 다른 시도는 같은 anchor 공유)
            occupied[anchor] = sido
            territories[sido].add(anchor)
        elif anchor not in group_cells[gkey]:
            # 같은 그룹 다른 anchor (보통 anchor 같지만 다를 수도)
            group_cells[gkey].add(anchor)
            occupied[anchor] = sido
            territories[sido].add(anchor)

    # group 단위로 grow. 같은 group은 한 cluster (서울+경기).
    # group target = group 내 시도들의 지역구 수 합.
    group_targets = {}
    for s, gkey in [(s, group_of(s)) for s in by_sido]:
        group_targets[gkey] = group_targets.get(gkey, 0) + targets[s]

    def group_size(gkey):
        return len(group_cells.get(gkey, set()))

    while any(group_size(gkey) < group_targets[gkey] for gkey in group_targets):
        progressed = False
        # 부족 큰 group 부터
        order = sorted(group_targets, key=lambda g: -(group_targets[g] - group_size(g)))
        for gkey in order:
            if group_size(gkey) >= group_targets[gkey]:
                continue
            cells = group_cells.get(gkey, set())
            # 그 그룹 시도들의 anchor centroid
            anchors_in_grp = [sido_anchor[s] for s in gkey if s in sido_anchor]
            ax = sum(a[0] for a in anchors_in_grp) / len(anchors_in_grp)
            ay = sum(a[1] for a in anchors_in_grp) / len(anchors_in_grp)
            ax_px, ay_px = offset_to_pixel(ax, ay)
            cand = set()
            for c in cells:
                for nb in offset_neighbors(*c):
                    if nb not in occupied:
                        cand.add(nb)
            if not cand:
                continue
            best = min(cand, key=lambda p: math.hypot(
                *[a - b for a, b in zip(offset_to_pixel(*p), (ax_px, ay_px))]
            ))
            cells.add(best)
            occupied[best] = '|'.join(sorted(gkey))  # group marker
            progressed = True
        if not progressed:
            break

    # group cells → 시도별 cells 매핑.
    # 통합 group: 안쪽 시도 (서울)가 cluster 중심을 차지, 바깥 시도 (경기)가 외곽 둘러쌈.
    # SIDO_INNER로 어느 시도가 안쪽인지 지정 (그룹 안에서 cell 수 적은 시도가 보통 안쪽).
    SIDO_INNER = {'서울특별시', '인천광역시', '대구광역시', '광주광역시', '부산광역시'}  # cluster center 우선
    for gkey in group_cells:
        if len(gkey) == 1:
            s = next(iter(gkey))
            if s in by_sido:
                territories[s] = group_cells[gkey].copy()
            continue
        # 다중 시도 group
        cells = list(group_cells[gkey])
        cell_px = [offset_to_pixel(*c) for c in cells]
        # cluster centroid
        ccx = sum(p[0] for p in cell_px) / len(cell_px)
        ccy = sum(p[1] for p in cell_px) / len(cell_px)
        # 안쪽 시도 cell 수만큼 center 가까운 cells 할당
        inner_sidos = [s for s in gkey if s in SIDO_INNER]
        outer_sidos = [s for s in gkey if s not in SIDO_INNER]
        inner_target = sum(len(by_sido.get(s, [])) for s in inner_sidos)
        # outer를 cluster boundary부터 BFS로 채워 ring 형태로 — connected 보장.
        cluster_set = set(cells)
        outer_target = len(cells) - inner_target
        boundary = [c for c in cells
                    if any(nb not in cluster_set for nb in offset_neighbors(*c))]
        outer_set = set()
        bfs_q = deque(boundary)
        seen = set(boundary)
        while len(outer_set) < outer_target and bfs_q:
            cur = bfs_q.popleft()
            if cur in outer_set:
                continue
            outer_set.add(cur)
            for nb in offset_neighbors(*cur):
                if nb in cluster_set and nb not in seen:
                    seen.add(nb)
                    bfs_q.append(nb)
        outer_cells = list(outer_set)
        inner_cells = [c for c in cells if c not in outer_set]
        # 각 시도별 cells 묶음 (안쪽 / 바깥)
        for s in gkey:
            territories[s] = set()
        # 안쪽 시도 — Hungarian으로 자체 cells에 매핑
        if inner_sidos and inner_cells:
            inner_dists = [(s, d) for s in inner_sidos for d in by_sido.get(s, [])]
            cell_list = list(inner_cells)
            cell_px2 = [offset_to_pixel(*c) for c in cell_list]
            cost = np.full((len(inner_dists), len(cell_list)), 1e9)
            for i, (s, d) in enumerate(inner_dists):
                for j, (cx, cy) in enumerate(cell_px2):
                    cost[i, j] = (d['hex_x'] - cx) ** 2 + (d['hex_y'] - cy) ** 2
            rows, cols = linear_sum_assignment(cost)
            for i, j in zip(rows, cols):
                territories[inner_dists[i][0]].add(cell_list[j])
        # 바깥 시도 — Hungarian으로 자체 cells에 매핑
        if outer_sidos and outer_cells:
            outer_dists = [(s, d) for s in outer_sidos for d in by_sido.get(s, [])]
            cell_list = list(outer_cells)
            cell_px2 = [offset_to_pixel(*c) for c in cell_list]
            cost = np.full((len(outer_dists), len(cell_list)), 1e9)
            for i, (s, d) in enumerate(outer_dists):
                for j, (cx, cy) in enumerate(cell_px2):
                    cost[i, j] = (d['hex_x'] - cx) ** 2 + (d['hex_y'] - cy) ** 2
            rows, cols = linear_sum_assignment(cost)
            for i, j in zip(rows, cols):
                territories[outer_dists[i][0]].add(cell_list[j])
        # occupied 갱신
        for s in gkey:
            for c in territories[s]:
                occupied[c] = s

    # === Phase 2: cluster 끌어당김 (compaction) ===
    # 각 시도 cluster를 전체 중심 방향으로 한 칸씩 이동. 다른 cluster와 충돌 안 하는 한 반복.
    # odd-r offset 좌표계 무결성 위해 vertical 이동은 짝수 row만 허용.
    def pull_clusters_in(territories, max_iters=80):
        for it in range(max_iters):
            # 전체 중심
            all_cells = [c for cells in territories.values() for c in cells]
            if not all_cells: break
            mid_c = sum(c for c, r in all_cells) / len(all_cells)
            mid_r = sum(r for c, r in all_cells) / len(all_cells)
            moved_any = False
            # 큰 시도부터 (작은 시도가 그 다음 빈자리로 끌려가게)
            for sido in sorted(territories, key=lambda s: -len(territories[s])):
                if sido in manual_sidos: continue  # manual 시도는 이동 안 함
                cells = territories[sido]
                if not cells: continue
                cx = sum(c for c, r in cells) / len(cells)
                cy = sum(r for c, r in cells) / len(cells)
                dx_target = mid_c - cx
                dy_target = mid_r - cy
                # 우선순위 방향 시도 — 더 먼 축부터, vertical은 ±2
                candidates = []
                if abs(dx_target) > 0.5:
                    candidates.append((1 if dx_target > 0 else -1, 0))
                if abs(dy_target) > 1:
                    candidates.append((0, 2 if dy_target > 0 else -2))
                if abs(dx_target) > 0.5 and abs(dy_target) > 1:
                    candidates.append((1 if dx_target > 0 else -1, 2 if dy_target > 0 else -2))
                # 그래도 안 움직이면 작은 단위
                for dc, dr in candidates:
                    new_cells = {(c + dc, r + dr) for c, r in cells}
                    other = set()
                    for s2, c2 in territories.items():
                        if s2 != sido: other |= c2
                    if new_cells & other: continue
                    if new_cells == cells: continue
                    territories[sido] = new_cells
                    moved_any = True
                    break
            if not moved_any: break
        # occupied 재구성
        new_occ = {}
        for sido, cells in territories.items():
            for c in cells:
                new_occ[c] = sido
        return new_occ

    occupied = pull_clusters_in(territories)

    # 각 시도 안 지역구 → Hungarian 매핑
    placed = {}
    for sido, ds in by_sido.items():
        cells = list(territories.get(sido, set()))
        if len(cells) < len(ds):
            print(f'  ! {sido}: cells {len(cells)} < districts {len(ds)}', file=sys.stderr)
        n_d = len(ds)
        n_c = len(cells)
        if not cells:
            continue
        cell_pixels = [offset_to_pixel(*c) for c in cells]
        # 지역구의 hex_x/hex_y 기반 매칭 (이미 시군구 hex centroid에서 추정)
        # 단 시도별 hex centroid 기준으로 normalize 필요. 일단 raw 사용.
        cost = np.full((n_d, n_c), 1e9)
        for i, d in enumerate(ds):
            for j, (cx, cy) in enumerate(cell_pixels):
                cost[i, j] = (d['hex_x'] - cx) ** 2 + (d['hex_y'] - cy) ** 2
        rows, cols = linear_sum_assignment(cost)
        for i, j in zip(rows, cols):
            placed[(ds[i]['sido'], ds[i]['name'])] = cells[j]

    # 결과 출력
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

    # fill_holes 후처리
    import importlib.util
    spec = importlib.util.spec_from_file_location("fill_holes", Path(__file__).parent / "fill_holes.py")
    fh = importlib.util.module_from_spec(spec); spec.loader.exec_module(fh)
    filled = fh.run(result, verbose=False, protect_sidos=set(SIDO_CELLS_MANUAL))

    # connectivity 후처리: 외톨이 component를 같은 시도의 메인 component 옆 셀과 swap.
    # swap 대상 시도도 여전히 connected 인지 확인 (외톨이 만들지 않음).
    def fix_isolated(records):
        pos_to_rec = {(r['c'], r['r']): r for r in records}
        def cells_of(sido):
            return [pos for pos, r in pos_to_rec.items() if r['sido'] == sido]
        def is_connected(cells_iter):
            cs = set(cells_iter)
            if not cs: return True
            start = next(iter(cs))
            visited = {start}; q = deque([start])
            while q:
                cur = q.popleft()
                for nb in offset_neighbors(*cur):
                    if nb in cs and nb not in visited:
                        visited.add(nb); q.append(nb)
            return len(visited) == len(cs)
        def comps_of(cells_iter):
            cs = set(cells_iter); seen = set(); comps = []
            for c in cs:
                if c in seen: continue
                comp = set(); q = deque([c])
                while q:
                    cur = q.popleft()
                    if cur in comp: continue
                    comp.add(cur)
                    for nb in offset_neighbors(*cur):
                        if nb in cs and nb not in comp:
                            q.append(nb)
                seen |= comp; comps.append(comp)
            return comps
        all_sidos = list({r['sido'] for r in records})
        for _ in range(20):
            swapped = False
            for sido in all_sidos:
                if sido in SIDO_CELLS_MANUAL: continue
                cells = cells_of(sido)
                comps = comps_of(cells)
                if len(comps) <= 1: continue
                main = max(comps, key=len)
                for comp in comps:
                    if comp is main: continue
                    for iso_cell in list(comp):
                        # main 인접 + 다른 시도 cell 중 swap 가능한 것 찾기
                        for mcell in main:
                            for nb in offset_neighbors(*mcell):
                                if nb == iso_cell: continue
                                other = pos_to_rec.get(nb)
                                if not other or other['sido'] == sido: continue
                                if other['sido'] in SIDO_CELLS_MANUAL: continue
                                # swap 결과: sido cells에 nb 추가, iso 제거 / other_sido cells에 iso 추가, nb 제거
                                other_sido = other['sido']
                                new_self_cells = (set(cells) - {iso_cell}) | {nb}
                                new_other_cells = (set(cells_of(other_sido)) - {nb}) | {iso_cell}
                                if not is_connected(new_self_cells): continue
                                if not is_connected(new_other_cells): continue
                                # 실행
                                rec_iso = pos_to_rec[iso_cell]
                                rec_iso['c'], rec_iso['r'] = nb
                                other['c'], other['r'] = iso_cell
                                del pos_to_rec[iso_cell]; del pos_to_rec[nb]
                                pos_to_rec[nb] = rec_iso
                                pos_to_rec[iso_cell] = other
                                swapped = True
                                break
                            if swapped: break
                        if swapped: break
                    if swapped: break
                if swapped: break
            if not swapped: break

    fix_isolated(filled)

    OUT.write_text(json.dumps(filled, ensure_ascii=False), encoding='utf-8')
    print(f'hole-fill 적용 → {len(filled)} cells', file=sys.stderr)


if __name__ == '__main__':
    main()
