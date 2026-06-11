"""hex layout — 시도별 주먹밥 (rectangle blob) 수동 layout.

구조:
  N zone:
                [        경기 top         ]
       인천   │   서울   │ 경기 right │ 강원
                [        경기 bot         ]
  S zone:
                [        충청             ]
                호남     │     영남
  P zone:
                제주

각 시도 = 직사각형 (또는 거의). 내부 빈칸 0, 만 없음, cluster 연결성 보장.
회차마다 cell 수 변동 → 시도별 W·H 동적 계산.

사용:
  python3 scripts/build/build_zone_hex.py
"""
from __future__ import annotations
import argparse
import json
import math
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIGUNGU_GEO = ROOT / 'data/geo/sigungu_simple.json'
SIGUNGU_OVERRIDES = ROOT / 'data/geo/sigungu_centroid_overrides.json'

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
    # geojson(base_year=2018) 이후 신설·개편 시군구는 overrides로 보정.
    if SIGUNGU_OVERRIDES.exists():
        ov = json.loads(SIGUNGU_OVERRIDES.read_text(encoding='utf-8'))
        for code, entry in (ov.get('centroids') or {}).items():
            lon, lat = entry['lonlat']
            by_code[code] = (lon, lat)
            by_name[entry['name']].append((code, lon, lat))
    return by_code, by_name


def cell_centroid(cell, by_code, by_name):
    if cell.get('_cen'):  # 선거구 geojson에서 직접 계산한 centroid(옛 회차·폐지 시군구 대응)
        return tuple(cell['_cen'])
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


def fill_rect(cells, col_start, row_start, W, H, sort_key=None, partial_align='left_top'):
    """cells을 col_start..col_start+W-1, row_start..row_start+H-1 직사각형에 채움.
    sort_key: 정렬 기준. None이면 2-pass: row 분배는 -lat (북 먼저), row 내 col은 lon (서 먼저).
    sort_key 명시 시 1-pass (기존 동작).
    partial_align: 마지막 row 미달 시 정렬 — 'left_top'/'right_top'/'left_bot'/'right_bot'.
    """
    if not cells:
        return
    two_pass = sort_key is None
    if sort_key is None:
        sort_key = lambda c: -c['lat']
    sorted_cells = sorted(cells, key=sort_key)
    N = len(sorted_cells)
    capacity = W * H
    # 마지막 row 미달분
    full_rows = N // W
    remainder = N - full_rows * W
    # partial row 정렬 결정
    rows_filled = []
    if partial_align in ('bot_anchor', 'right_bot_anchor'):
        # 바닥(row H-1)에 항상 채움. 빈 row는 위쪽으로. partial row는 full rows의 바로 위.
        # cells 분배: 마지막 H-1 row부터 거꾸로 full_rows 채우고, 그 위 row는 partial.
        rows_used = full_rows + (1 if remainder > 0 else 0)
        empty_top = max(0, H - rows_used)
        if remainder > 0:
            rows_filled.append((empty_top, remainder))
            first_full = empty_top + 1
        else:
            first_full = empty_top
        for r in range(full_rows):
            rows_filled.append((first_full + r, W))
    elif partial_align in ('left_bot', 'right_bot'):
        # 모든 full row 위쪽 + 마지막 row 아래
        for r in range(full_rows):
            rows_filled.append((r, W))
        if remainder > 0:
            rows_filled.append((full_rows, remainder))
    else:  # left_top, right_top — partial row가 맨 위쪽
        if remainder > 0:
            rows_filled.append((0, remainder))
            offset = 1
        else:
            offset = 0
        for r in range(full_rows):
            rows_filled.append((r + offset, W))
    idx = 0
    for local_r, count in rows_filled:
        right_align = partial_align in ('right_top', 'right_bot', 'right_bot_anchor')
        if right_align and count < W:
            col_offset = W - count
        else:
            col_offset = 0
        # 2-pass: row 안에서 lon으로 다시 정렬 (서 → 동)
        if two_pass:
            row_slice = sorted_cells[idx:idx+count]
            row_slice.sort(key=lambda c: c['lon'])
            for i in range(count):
                row_slice[i]['c'] = col_start + col_offset + i
                row_slice[i]['r'] = row_start + local_r
            idx += count
        else:
            for i in range(count):
                c = sorted_cells[idx]
                c['c'] = col_start + col_offset + i
                c['r'] = row_start + local_r
                idx += 1


def fill_wrap_top_left_right(cells, inner_col, inner_row, inner_W, inner_H, top_h, left_w, right_w):
    """3-side wrap (top + left + right). bottom 무. inner block의 위·좌·우 둘러쌈.
    cells lat 분포로 top/left/right 분배."""
    if not cells:
        return
    total_w = left_w + inner_W + right_w
    cells_sorted = sorted(cells, key=lambda c: -c['lat'])
    n = len(cells_sorted)
    N_top = top_h * total_w
    N_left = left_w * inner_H
    N_right = right_w * inner_H
    take_top = min(N_top, n)
    take_left = min(N_left, n - take_top)
    take_right = min(N_right, n - take_top - take_left)
    top_cells = cells_sorted[:take_top]
    middle = cells_sorted[take_top:take_top + take_left + take_right]
    middle_lon = sorted(middle, key=lambda c: c['lon'])
    left_cells = middle_lon[:take_left]
    right_cells = middle_lon[take_left:]
    fill_rect(
        top_cells,
        col_start=inner_col - left_w, row_start=inner_row - top_h,
        W=total_w, H=top_h,
        sort_key=None,
        partial_align='left_top',
    )
    fill_rect(
        left_cells,
        col_start=inner_col - left_w, row_start=inner_row,
        W=left_w, H=inner_H,
        sort_key=None,
        partial_align='left_bot',
    )
    fill_rect(
        right_cells,
        col_start=inner_col + inner_W, row_start=inner_row,
        W=right_w, H=inner_H,
        sort_key=lambda c: (-c['lat'], -c['lon']),
        partial_align='right_bot',
    )


def fill_horizontal_stack(sido_cell_pairs, col_start, row_start, H, sort_key=None, partial_align='right_bot'):
    """여러 시도 cells을 좌→우 수평 stack. 각 시도 = 직사각형 sub-rect.
    sido_cell_pairs: [(sido_name, cells), ...] in 좌→우 lon 순.
    각 시도 W_s = ceil(n_s / H). 시도별 cluster 보장.
    Return: 다 합친 cols 수.
    """
    cur_col = col_start
    for sido, cells in sido_cell_pairs:
        if not cells:
            continue
        w_s = math.ceil(len(cells) / H)
        fill_rect(cells, cur_col, row_start, w_s, H, sort_key=sort_key, partial_align=partial_align)
        cur_col += w_s
    return cur_col - col_start


def fill_wrap_top_right_bot(cells, inner_col, inner_row, inner_W, inner_H, top_h, right_w, bot_h, bot_extra_left=0, top_extra_left=0, in_extra_top_row=0, in_extra_w=0, inner_holes=None):
    """경기 wrap — inner block 위·우·아래 둘러쌈.
    top/bot_extra_left: top/bot 좌측 확장 cols.
    in_extra_top_row: top wrap에 인천 위 추가 1 row 포함 (cols 0..in_extra_w-1).
    cells lat 분포로 top/right/bot 분배 (top=북, right=중간, bot=남)."""
    if not cells:
        return
    top_w = inner_W + right_w + top_extra_left
    bot_w = inner_W + right_w + bot_extra_left
    N_top = top_h * top_w + (in_extra_w if in_extra_top_row else 0)
    N_bot = bot_h * bot_w
    N_right = right_w * inner_H
    N_total = N_top + N_right + N_bot
    # 분배 전략:
    # 1) top  = 가장 북 N_top cells (lat 큰 순). 북부는 lon 무관.
    # 2) 나머지에서 east-most N_right cells = right wrap. 진짜 동쪽만.
    # 3) 그 나머지 = bot wrap (남부 + 서남).
    # 이전 단순 lat 분배는 부천·광명 같은 mid-lat 서쪽이 right 박혀 부자연 → lon 고려.
    cells_by_lat = sorted(cells, key=lambda c: -c['lat'])
    n_actual = len(cells_by_lat)
    take_top = min(N_top, n_actual)
    top_cells = cells_by_lat[:take_top]
    leftover = cells_by_lat[take_top:]
    leftover_by_lon = sorted(leftover, key=lambda c: -c['lon'])
    take_right = min(N_right, len(leftover_by_lon))
    right_cells = leftover_by_lon[:take_right]
    bot_pool = leftover_by_lon[take_right:]
    take_bot = min(N_bot, len(bot_pool))
    bot_cells = bot_pool[:take_bot]

    # inner block(서울) 직사각형의 빈칸 → 경기 최북단 bot 셀로 메움.
    # 서울 바로 아래/안쪽 = 남부 경기 북단이라 지리적으로 자연스럽고, 서울·경기 사이
    # 갇힌 구멍을 없앤다. 사용한 셀은 bot pool에서 빼 bot wrap은 그만큼 서측이 비게 됨(외곽 notch).
    if inner_holes:
        bot_by_lat = sorted(bot_cells, key=lambda c: -c['lat'])
        n_hole = min(len(inner_holes), len(bot_by_lat))
        hole_cells = bot_by_lat[:n_hole]
        holes_sorted = sorted(inner_holes, key=lambda p: (p[1], p[0]))
        for cell, (hc, hr) in zip(hole_cells, holes_sorted):
            cell['c'] = hc
            cell['r'] = hr
        used = {id(c) for c in hole_cells}
        bot_cells = [c for c in bot_cells if id(c) not in used]

    # top wrap: top_h rows + 추가 row (인천 위 1 row, cols 0..in_extra_w-1)
    # cells을 2 그룹으로 — 추가 row (인천 위, 가장 lat 큰 in_extra_w 개? 아니면 중간 위치라 단순화)
    # 단순화: top_cells 전체를 lat 큰 순으로 배치. 추가 row 먼저 (가장 위 = 가장 북), 그 다음 top_h rows.
    if in_extra_top_row and in_extra_w > 0:
        # 인천 위 추가 row = 가장 북 in_extra_w cells (lat 가장 큰)
        # 단, 추가 row는 시각상 row 0이 아니라 row top_h-1 의 아래 (= 인천 첫 row 위)
        # → 추가 row를 가장 남쪽에 배치 (lat 작은 것을 추가 row에)
        # 정확히: top_h * top_w cells을 row 0..top_h-1 채우고, 마지막 in_extra_w 셀이 row top_h cols 0..in_extra_w-1
        main_count = top_h * top_w
        main_cells = top_cells[:main_count]
        extra_cells = top_cells[main_count:main_count + in_extra_w]
        fill_rect(
            main_cells,
            col_start=inner_col - top_extra_left,
            row_start=inner_row - top_h,
            W=top_w, H=top_h,
            sort_key=None,
            partial_align='left_top',
        )
        # extra row: cols 0..in_extra_w-1 at row inner_row - 1 + 1 = inner_row (인천 위 = row top_h - 1 of wrap)
        # 실제 위치: 인천 row_start = inner_row + 1 이므로 인천 위 = inner_row.
        extra_col_start = inner_col - top_extra_left - (in_extra_w - top_extra_left) if in_extra_w > top_extra_left else inner_col - top_extra_left
        # 단순화: cols 0..in_extra_w-1 (N zone 좌측 인천 area)
        zone_left = inner_col - top_extra_left  # top wrap 좌측 col
        # 인천 area는 col 0..in_extra_w-1 (N zone 시작)
        extra_cells_sorted = sorted(extra_cells, key=lambda c: c['lon'])
        for i, cell in enumerate(extra_cells_sorted):
            cell['c'] = inner_col - in_extra_w + i  # 인천 area 우측 정렬
            cell['r'] = inner_row
    else:
        fill_rect(
            top_cells,
            col_start=inner_col - top_extra_left,
            row_start=inner_row - top_h,
            W=top_w, H=top_h,
            sort_key=None,
            partial_align='left_top',
        )
    # right wrap: rows inner_row..inner_row+inner_H-1, cols inner_col+inner_W..inner_col+inner_W+right_w-1
    fill_rect(
        right_cells,
        col_start=inner_col + inner_W,
        row_start=inner_row,
        W=right_w, H=inner_H,
        sort_key=None,
        partial_align='right_top',  # 미달 시 우측 outer
    )
    # bot wrap: inner_row+inner_H..inner_row+inner_H+bot_h-1, cols 인천 아래까지 확장
    # column-major from RIGHT: 동쪽 col (강원 옆) 우선 full bot_h, partial col은 westmost.
    # 이유: row-major 'right_bot'은 마지막 row가 좌측 잘려 보임 → bot row 항상 full로 유지.
    # partial col bot-align → westmost col 위쪽 빈자리 (인천 아래 notch, 자연 흡수).
    bot_col_start = inner_col - bot_extra_left
    bot_row_start = inner_row + inner_H
    if bot_cells and bot_w > 0 and bot_h > 0:
        bot_by_lon = sorted(bot_cells, key=lambda c: -c['lon'])
        n_bot = len(bot_by_lon)
        full_cols = n_bot // bot_h
        remainder = n_bot - full_cols * bot_h
        idx = 0
        for batch_idx in range(full_cols):
            col_global = (bot_w - 1) - batch_idx
            col_cells = sorted(bot_by_lon[idx:idx + bot_h], key=lambda c: -c['lat'])
            for row_idx, cell in enumerate(col_cells):
                cell['c'] = bot_col_start + col_global
                cell['r'] = bot_row_start + row_idx
            idx += bot_h
        if remainder > 0:
            col_global = (bot_w - 1) - full_cols
            col_cells = sorted(bot_by_lon[idx:idx + remainder], key=lambda c: -c['lat'])
            row_offset_partial = bot_h - remainder  # bot-align
            for row_idx, cell in enumerate(col_cells):
                cell['c'] = bot_col_start + col_global
                cell['r'] = bot_row_start + row_offset_partial + row_idx


def design_zone_N(zone_cells_by_sido):
    """N zone: 인천 | 서울 inner + 경기 wrap top·right·bot + 강원 right.
    return: (zone_W, zone_H, top_h, inner_row) — 외부에서 위치 계산용."""
    n_seoul = len(zone_cells_by_sido.get('서울특별시', []))
    n_in = len(zone_cells_by_sido.get('인천광역시', []))
    n_gg = len(zone_cells_by_sido.get('경기도', []))
    n_gw = len(zone_cells_by_sido.get('강원특별자치도', [])) + len(zone_cells_by_sido.get('강원도', []))

    # 서울 square-ish
    if n_seoul == 0:
        h_seoul = 1; w_seoul = 0
    else:
        h_seoul = max(1, round(math.sqrt(n_seoul)))
        # 정확 인수분해 우선
        for h in range(h_seoul, h_seoul + 3):
            if n_seoul % h == 0:
                h_seoul = h; w_seoul = n_seoul // h
                break
        else:
            w_seoul = math.ceil(n_seoul / h_seoul)
    inner_H = h_seoul

    # 인천 width 임시 (cap 계산용). 인천 H = inner_H - 1 (한 칸 아래로 내리고 row top_h는 경기 차지)
    in_H_avail = max(1, inner_H - 1) if inner_H else 0
    if n_in == 0:
        w_in_est = 0
    elif n_in < 4:
        w_in_est = 1
    else:
        h_est = max(2, math.ceil(math.sqrt(n_in * 1.5)))
        w_in_est = math.ceil(n_in / h_est)
        if in_H_avail and h_est > in_H_avail:
            w_in_est = math.ceil(n_in / in_H_avail)
    # 경기 wrap: top + right + bot. top·bot 모두 인천 전체 폭(w_in)까지 감쌀 수 있도록 영역 확보.
    # 단 cells 부족 시 westmost col은 column-major 알고리즘상 자연 탈락 (빈 공간으로 보임) —
    # 영역 설계는 가득 덮음 의도, 실제 fill은 cells 양에 따름.
    top_extra = (w_in_est + 1) // 2  # top wrap rows는 절반만 (extra row가 따로 위 덮음)
    bot_extra = w_in_est              # bot은 full width 영역 (빈 col 탈락 허용)
    # cells = top_h*top_w + right_w*inner_H + bot_h*bot_w
    best = None
    # 인천 위 추가 row (인천이 1 row 내려가서 row top_h 자리) — 인천 가득
    in_extra_top_row = w_in_est
    for right_w in range(1, 4):
        top_w = top_extra + w_seoul + right_w
        bot_w = bot_extra + w_seoul + right_w
        for top_h in range(1, 4):
            for bot_h in range(1, 6):
                cap = top_h * top_w + in_extra_top_row + right_w * inner_H + bot_h * bot_w
                if cap >= n_gg:
                    # Bridge 조건 (column-major bot): 동쪽 col 최소 1개 full → bot row 최우측 채움 + right wrap 연결
                    bot_cells = n_gg - top_h * top_w - right_w * inner_H
                    if bot_cells < bot_h:
                        continue
                    waste = cap - n_gg
                    top_heavy = max(0, top_h - bot_h)
                    east_penalty = right_w * 5
                    # top_heavy 페널티 + bot_h 보상 (남부 인구 집중)
                    score = (waste + east_penalty + top_heavy * 10 - bot_h * 4, top_h + bot_h)
                    if best is None or score < best[0]:
                        best = (score, right_w, top_h, bot_h, cap)
    if best is None:
        right_w, top_h, bot_h = 1, 1, 1
    else:
        _, right_w, top_h, bot_h, _ = best

    # N zone 전체 높이 = 경기 top + 서울 inner + 경기 bot
    H_N = top_h + inner_H + bot_h

    # 인천: 한 칸 아래로 내림. H = inner_H - 1 (row top_h은 경기 북부로).
    h_in_avail = max(1, inner_H - 1) if inner_H else 0
    if n_in == 0:
        w_in = 0
    elif n_in < 4:
        w_in = 1
    else:
        h_in_pref = max(2, math.ceil(math.sqrt(n_in * 1.5)))
        w_in = math.ceil(n_in / h_in_pref)
        if h_in_avail and h_in_pref > h_in_avail:
            w_in = math.ceil(n_in / h_in_avail)

    # 강원: 필요한 h(N zone 높이) 채우는 게 우선 — 1-col 지렁이도 OK
    if n_gw == 0:
        w_gw, h_gw = 0, 0
    else:
        # w = ceil(n / H_N). 셀 적고 H_N 크면 자연히 1×N strip이 됨.
        w_gw = max(1, math.ceil(n_gw / H_N)) if H_N else 1
        h_gw = math.ceil(n_gw / w_gw)

    zone_W = w_in + w_seoul + right_w + w_gw
    zone_H = H_N

    return {
        'zone_W': zone_W, 'zone_H': zone_H,
        'top_h': top_h, 'bot_h': bot_h, 'right_w': right_w,
        'inner_W': w_seoul,  # 경기 wrap 대상 = 서울만
        'inner_H': inner_H,
        'w_in': w_in, 'w_seoul': w_seoul, 'w_gw': w_gw, 'h_gw': h_gw,
        'H_N': H_N,
    }


def square_factor(n, prefer_tall=True):
    """n cells을 (h, w) 직사각으로 — waste + asym 최소 (tie: -h)."""
    if n == 0:
        return 1, 0
    h_root = max(1, round(math.sqrt(n)))
    best = None
    for h in range(max(1, h_root - 1), h_root + 3):
        w = math.ceil(n / h)
        waste = w * h - n
        if waste < 0:
            continue
        # waste + asym 같으면 -h (높이 큰 게 우선) 또는 +h (낮은 게 우선)
        score = (waste + abs(h - w), -h if prefer_tall else h)
        if best is None or score < best[0]:
            best = (score, h, w)
    return best[1], best[2]


def fill_wrap_left_right_bot(cells, inner_col, inner_row, inner_W, inner_H, left_w, right_w, bot_h, extra_positions=None):
    """3-side wrap (left + right + bot) + optional extra positions (e.g., inner box 빈자리 채움)."""
    if not cells:
        return
    extra_positions = list(extra_positions or [])
    total_w = left_w + inner_W + right_w
    cells_sorted = sorted(cells, key=lambda c: -c['lat'])
    n = len(cells_sorted)
    N_left = left_w * inner_H
    N_right = right_w * inner_H
    N_extra = len(extra_positions)
    N_bot = bot_h * total_w
    # 분배: middle wrap (lat 큰) + extra (mid lat, inner box 빈자리) + bot (lat 작은)
    middle_count = min(N_left + N_right, n)
    extra_count = min(N_extra, n - middle_count)
    bot_count = min(N_bot, n - middle_count - extra_count)
    middle = cells_sorted[:middle_count]
    extra_cells = cells_sorted[middle_count:middle_count + extra_count]
    bot_cells_arr = cells_sorted[middle_count + extra_count:middle_count + extra_count + bot_count]
    # extra: 광주 box 빈자리를 전남으로 메움
    for cell, pos in zip(extra_cells, extra_positions):
        cell['c'], cell['r'] = pos
    middle_lon = sorted(middle, key=lambda c: c['lon'])
    take_left = min(N_left, len(middle_lon))
    left_cells = middle_lon[:take_left]
    right_cells = middle_lon[take_left:]
    fill_rect(
        left_cells,
        col_start=inner_col - left_w, row_start=inner_row,
        W=left_w, H=inner_H,
        sort_key=None,
        partial_align='left_bot',
    )
    fill_rect(
        right_cells,
        col_start=inner_col + inner_W, row_start=inner_row,
        W=right_w, H=inner_H,
        sort_key=lambda c: (-c['lat'], -c['lon']),
        partial_align='right_bot',
    )
    fill_rect(
        bot_cells_arr,
        col_start=inner_col - left_w, row_start=inner_row + inner_H,
        W=total_w, H=bot_h,
        sort_key=None,
        partial_align='left_bot',
    )


def design_honam(zone_cells_by_sido, target_W=None, target_H=None):
    """호남 sub-layout: 광주 inner + 전남 wrap (left+right+bot) + 전북 top.
    광주 shape + 전남 wrap 동시 최적화 — waste 최소 + 연결성 보장.
    target_W 주면 W_ho==target_W 후보 우선 (strict). 없으면 free search.
    target_H 주면 H_ho==target_H 후보 우선 (영남과 Left H 맞춤)."""
    n_gj = len(zone_cells_by_sido.get('광주광역시', []))
    n_jn = len(zone_cells_by_sido.get('전라남도', []))
    n_jb = len(zone_cells_by_sido.get('전북특별자치도', [])) + len(zone_cells_by_sido.get('전라북도', []))

    # 광주 후보 shape (square_factor 주변)
    gj_candidates = []
    if n_gj > 0:
        h_root = max(1, round(math.sqrt(n_gj)))
        for h in range(max(1, h_root - 1), h_root + 3):
            w = math.ceil(n_gj / h)
            waste = w * h - n_gj
            if 0 <= waste <= 2:
                gj_candidates.append((h, w, waste))
    else:
        gj_candidates.append((1, 0, 0))

    # 동시 최적화: 광주 + 전남 wrap. 연결성 — bot row 완전 채워짐(또는 bot_h≥2).
    best = None
    for h_gj, w_gj, gj_waste in gj_candidates:
        for bot_h in range(0, 6):
            for left_w in range(1, 5):
                for right_w in range(1, 5):
                    total_w = left_w + w_gj + right_w
                    cap = bot_h * total_w + (left_w + right_w) * h_gj
                    if cap < n_jn:
                        continue
                    bot_used = n_jn - (left_w + right_w) * h_gj
                    if bot_used < 0:
                        continue
                    # 연결성: bot_h=0이면 좌우 분리. bot_h=1이고 partial이면 좌우 wrap과 단절 가능
                    if bot_used > 0 and bot_h == 0:
                        continue
                    if bot_h == 1 and 0 < bot_used < total_w:
                        # 1행 partial → 좌·우 boundary 둘 다 못 닿음
                        continue
                    if bot_h == 0 and (left_w + right_w) > 0 and bot_used == 0:
                        # bot 없이 left+right만 → 좌·우 단절
                        continue
                    # left·right 둘 다 있으면 bot이 좌·우 연결해야 함.
                    # bot이 full row 못 채우면 (left_bot align으로 좌측에만 셀) 우측 wrap 단절.
                    if left_w > 0 and right_w > 0 and bot_used < total_w:
                        continue
                    jn_waste = cap - n_jn
                    asym = abs(left_w - right_w)
                    total_w = left_w + w_gj + right_w
                    # target_W 매칭 페널티
                    w_penalty = abs(total_w - target_W) * 5 if target_W else 0
                    # target_H 매칭 페널티 — 영남 H에 맞춰 Left H stretch
                    top_h_jb_try = math.ceil(n_jb / total_w) if total_w and n_jb else 0
                    H_ho_try = top_h_jb_try + h_gj + bot_h
                    h_penalty = abs(H_ho_try - target_H) * 10 if target_H else 0
                    score = (gj_waste + jn_waste + w_penalty + h_penalty, asym, bot_h + left_w + right_w, h_gj * 10 + w_gj)
                    if best is None or score < best[0]:
                        best = (score, h_gj, w_gj, bot_h, left_w, right_w)
    if best is None:
        # fallback
        h_gj, w_gj = square_factor(n_gj)
        bot_h, left_w, right_w = 1, 1, 1
    else:
        _, h_gj, w_gj, bot_h, left_w, right_w = best
    total_w = left_w + w_gj + right_w
    top_h_jb = math.ceil(n_jb / total_w) if total_w and n_jb else 0
    W_ho = total_w
    H_ho = top_h_jb + h_gj + bot_h
    return {
        'W_ho': W_ho, 'H_ho': H_ho,
        'top_h_jb': top_h_jb, 'bot_h': bot_h,
        'left_w': left_w, 'right_w': right_w,
        'h_gj': h_gj, 'w_gj': w_gj,
        'total_w': total_w,
    }


def design_yeongnam(zone_cells_by_sido):
    """영남 sub-layout — blob mode:
       Top: 경북 north-wrap (top + left + bridge), 대구 직사각형 좌-중앙 bot, 울산 직사각형/L 우-bot.
            대구 bot row = 울산 bot row (정렬). 둘 다 bot region과 직접 접촉.
       Bot: 경남 (서쪽 cols 0..w_gn-1), 부산 (동쪽 cols w_gn..W-1).
       빈자리는 outer-east (top 우상) + outer-bot (남동).
       사용자 의도: 울산이 뭉친 blob + east 라인, 대구·울산이 경남부산과 접촉."""
    n_dg = len(zone_cells_by_sido.get('대구광역시', []))
    n_kb = len(zone_cells_by_sido.get('경상북도', []))
    n_gn = len(zone_cells_by_sido.get('경상남도', []))
    n_bs = len(zone_cells_by_sido.get('부산광역시', []))
    n_us = len(zone_cells_by_sido.get('울산광역시', []))

    # 대구 직사각형 — near-square (빈칸 최소 + 정사각 가까이). 소수/난수 셀(13·11 등)도
    # 1×N 기둥(영남 길쭉) 회피. 정확 약수면 빈칸 0이라 자연 우선. 배정부가 남는 칸을 비움.
    dg_cands = []
    for h in range(1, n_dg + 1):
        w = math.ceil(n_dg / h)
        waste = h * w - n_dg
        dg_cands.append((waste + abs(h - w) * 0.5, h, w))
    dg_cands.sort()
    h_dg, w_dg = (dg_cands[0][1], dg_cands[0][2]) if dg_cands else (max(n_dg, 1), 1)

    # 울산: 5셀이면 L자 (3×2 -1 corner), 6셀이면 3×2 직사각, 그 외 정사각 가까이
    if n_us == 5:
        h_us, w_us, us_l = 3, 2, True
    elif n_us == 6:
        h_us, w_us, us_l = 3, 2, False
    elif n_us == 4:
        h_us, w_us, us_l = 2, 2, False
    elif n_us == 0:
        h_us, w_us, us_l = 0, 0, False
    else:
        h_us = max(2, round(math.sqrt(n_us)))
        w_us = math.ceil(n_us / h_us)
        # L-corner(경북 bridge)는 n_us=5 전용. 그 외 빈칸은 울산 영역으로 둠 — 안 그러면
        # corner 경북 셀이 위쪽 빈칸과 만나 고립됨(예: 16대 울산 3석 2×2 L → 경북 1셀 분리).
        us_l = False

    inner_h = max(h_dg, h_us)
    inner_w = w_dg + w_us
    n_bot = n_gn + n_bs

    # 검색: (top_h, left_w, W_extra, H_bot, w_gn)
    # 점수: (total_empties, W) — 빈자리 최소 + 더 좁은 W (taller blob) 선호
    best = None
    for top_h in range(1, 5):
        for left_w in range(1, 3):
            for W_extra in range(0, 4):
                W = left_w + inner_w + W_extra
                H_top = top_h + inner_h
                top_slots = W * H_top
                # 대구·울산은 직사각 면적(빈칸 포함)을 차지 — near-square라 면적 > 셀수일 수 있음.
                # n_dg/n_us로 계산하면 경북 공간을 과대평가해 경북 셀이 넘쳐 고립됨.
                dg_area = w_dg * h_dg
                us_area = w_us * h_us - (1 if us_l else 0)
                top_taken = dg_area + us_area + n_kb
                if top_slots < top_taken:
                    continue
                top_empties = top_slots - top_taken
                # T 경계: row 0 (W) + col 0 (inner_h) + bridges + L corner = 필수 경북 cells.
                bridge_us = (h_dg - h_us) * w_us
                us_corner = 1 if us_l else 0
                kb_must = W + (H_top - 1) + bridge_us + us_corner  # 단순화
                if n_kb < W:
                    continue  # 경북이 row 0도 못 채움 (T 경계 violation)
                for H_bot in range(3, 12):
                    if W * H_bot < n_bot:
                        continue
                    bot_empties = W * H_bot - n_bot
                    for w_gn in range(1, W):
                        # 경남이 w_gn col 다 채우고 인접 col에 1행 overflow 허용
                        if w_gn * H_bot + H_bot < n_gn:
                            continue
                        # 부산도 마찬가지로 borrow 1 row 가능
                        if (W - w_gn) * H_bot + H_bot < n_bs:
                            continue
                        total_empties = top_empties + bot_empties
                        score = (total_empties, W, abs((H_top + H_bot) - W))
                        if best is None or score < best[0]:
                            best = (score, W, H_top, H_bot, top_h, left_w, W_extra, w_gn)

    if best is None:
        # fallback: 단순 H=W 정사각
        n_total = n_dg + n_kb + n_gn + n_bs + n_us
        H = max(3, math.ceil(math.sqrt(n_total)))
        W = math.ceil(n_total / H)
        return {'W_yn': W, 'H_yn': H, 'mode': 'fallback',
                'h_dg': h_dg, 'w_dg': w_dg, 'h_us': h_us, 'w_us': w_us, 'us_l': us_l}

    _, W, H_top, H_bot, top_h, left_w, W_extra, w_gn = best
    return {
        'W_yn': W, 'H_yn': H_top + H_bot,
        'mode': 'blob',
        'H_top': H_top, 'H_bot': H_bot,
        'top_h': top_h, 'left_w': left_w, 'W_extra': W_extra,
        'h_dg': h_dg, 'w_dg': w_dg,
        'h_us': h_us, 'w_us': w_us, 'us_l': us_l,
        'w_gn': w_gn,
    }


def _legacy_design_yeongnam(zone_cells_by_sido):
    """레거시 wrap mode (참고용, 사용 안 함)."""
    n_dg = len(zone_cells_by_sido.get('대구광역시', []))
    n_kb = len(zone_cells_by_sido.get('경상북도', []))
    n_gn = len(zone_cells_by_sido.get('경상남도', []))
    n_bs = len(zone_cells_by_sido.get('부산광역시', []))
    n_us = len(zone_cells_by_sido.get('울산광역시', []))

    # 대구 inner — square-ish (waste 동률이면 |h-w| 작은 게 우선)
    if n_dg == 0:
        h_dg, w_dg = 1, 0
    else:
        h_root = max(1, round(math.sqrt(n_dg)))
        best = None
        for h in range(max(1, h_root - 1), h_root + 3):
            w = math.ceil(n_dg / h)
            waste = w * h - n_dg
            if waste < 0:
                continue
            # tie-break: prefer taller (h ≥ w) for vertical-ish blob
            score = (waste, abs(h - w), -h)
            if best is None or score < best[0]:
                best = (score, h, w)
        _, h_dg, w_dg = best

    # 경북 wrap (top + left + right) 최소 enclosure
    # 좌·우 wrap 둘 다 있으면 top ≥ 1 필수 (좌·우 연결 보장 → cluster 1개)
    best_wrap = None
    for top_h in range(0, 6):
        for left_w in range(0, 5):
            for right_w in range(0, 5):
                # 연결성 가드
                if left_w > 0 and right_w > 0 and top_h < 1:
                    continue
                total_w = left_w + w_dg + right_w
                cap = top_h * total_w + (left_w + right_w) * h_dg
                if cap >= n_kb:
                    waste = cap - n_kb
                    asym = abs(left_w - right_w)
                    score = (waste, asym, top_h + left_w + right_w)
                    if best_wrap is None or score < best_wrap[0]:
                        best_wrap = (score, top_h, left_w, right_w)
    _, top_h, left_w, right_w = best_wrap if best_wrap else ((0, 0, 0), 1, 1, 1)
    total_top_w = left_w + w_dg + right_w
    top_half_h = top_h + h_dg

    # bottom: 경남/부산/울산 horizontal stack — compact (h_bot + bot_w 최소)
    bot_cells = n_gn + n_bs + n_us
    if bot_cells == 0:
        h_bot = 0
        w_gn = w_bs = w_us = 0
        actual_bot_w = 0
    else:
        best_bot = None
        for h_try in range(1, bot_cells + 1):
            w_gn_try = math.ceil(n_gn / h_try) if n_gn else 0
            w_bs_try = math.ceil(n_bs / h_try) if n_bs else 0
            w_us_try = math.ceil(n_us / h_try) if n_us else 0
            bot_w_try = w_gn_try + w_bs_try + w_us_try
            # 영남 전체 zone shape도 고려 — top과의 mismatch도 페널티
            zone_w_try = max(total_top_w, bot_w_try)
            score = (h_try + bot_w_try, abs(zone_w_try - (top_half_h + h_try)))
            if best_bot is None or score < best_bot[0]:
                best_bot = (score, h_try, w_gn_try, w_bs_try, w_us_try, bot_w_try)
        _, h_bot, w_gn, w_bs, w_us, actual_bot_w = best_bot

    W_yn = max(total_top_w, actual_bot_w)
    H_yn = top_half_h + h_bot

    # column-based perfect-fit는 시도 stripe 형태가 비지리적이라 사용 안 함.
    # wrap mode (경북이 대구 둘러쌈 + 경남/부산/울산 bottom stack) — 한반도 영남 지리 자연.
    return {
        'W_yn': W_yn, 'H_yn': H_yn,
        'mode': 'wrap',
        'top_h': top_h, 'left_w': left_w, 'right_w': right_w,
        'h_dg': h_dg, 'w_dg': w_dg,
        'h_bot': h_bot, 'w_gn': w_gn, 'w_bs': w_bs, 'w_us': w_us,
        'total_top_w': total_top_w,
    }


def find_yeongnam_wh_smart(n_total, n_us, target_h=None):
    """울산을 마지막 col 단독 + 나머지 col 0..W-2 column-major.
    조건: n_us ≤ H AND (W-1)*H ≥ (n_total - n_us).
    empties는 마지막 col(울산 아래) + 마지막 col-1 하단에 모임 (outer-right).
    target_h 가까운 H 우선, empties 최소."""
    n_other = n_total - n_us
    candidates = []
    for H in range(max(n_us, 3), n_total + 1):
        if H > 30:
            break
        W = max(2, math.ceil(n_other / H) + 1)  # +1 col for 울산
        if (W - 1) * H < n_other:
            continue
        empties = W * H - n_total
        h_score = abs(H - target_h) if target_h else 0
        score = (h_score, empties, abs(W - H))
        candidates.append((score, W, H))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1], candidates[0][2]


def partition_yeongnam_blob(by_sido, plan):
    """blob layout: 대구·울산 bot-aligned 직사각형/L. 경북 north wrap. 경남·부산 bot stack.
    return: grid_map {(c, r): sido_name} (영남 zone local 좌표)."""
    W = plan['W_yn']
    H_top = plan['H_top']
    H_bot = plan['H_bot']
    top_h = plan['top_h']
    left_w = plan['left_w']
    w_dg, h_dg = plan['w_dg'], plan['h_dg']
    w_us, h_us, us_l = plan['w_us'], plan['h_us'], plan['us_l']
    w_gn = plan['w_gn']
    n_kb = len(by_sido.get('경상북도', []))
    n_gn = len(by_sido.get('경상남도', []))
    n_bs = len(by_sido.get('부산광역시', []))

    grid = {}
    inner_h = max(h_dg, h_us)

    # 대구 직사각형
    dg_col0 = left_w
    dg_row0 = top_h + (inner_h - h_dg)
    for dc in range(w_dg):
        for dr in range(h_dg):
            grid[(dg_col0 + dc, dg_row0 + dr)] = '대구광역시'

    # 울산 (직사각 or L)
    us_col0 = left_w + w_dg
    us_row0 = top_h + (inner_h - h_us)
    for dc in range(w_us):
        for dr in range(h_us):
            if us_l and dc == w_us - 1 and dr == 0:
                continue  # L자: top-right corner = 경북 bridge
            grid[(us_col0 + dc, us_row0 + dr)] = '울산광역시'

    # 경북: 우선순위 — (1) row 0 T-boundary, (2) col 0 T-boundary, (3) 울산 위 bridge,
    # (4) L-corner, (5) 나머지 top region. n_kb개까지 채우고 나머지 empty.
    kb_ordered = []
    seen = set()
    def add(p):
        if p in grid or p in seen: return
        seen.add(p)
        kb_ordered.append(p)
    # (1) row 0 — T-boundary top
    for c in range(W):
        add((c, 0))
    # (2) col 0 rows 1..H_top-1 — T-boundary left
    for r in range(1, H_top):
        add((0, r))
    # (3) bridge above 울산 (h_dg > h_us 경우)
    for r in range(top_h, us_row0):
        for c in range(us_col0, us_col0 + w_us):
            add((c, r))
    # (4) L-corner + 그 위 연결 col — 대구가 짧으면(near-square) bridge가 안 깔려 corner가
    #     위쪽 빈칸과 만나 고립됨. L-corner 위 col을 채워 row 0(T경계 경북)과 직접 연결.
    if us_l:
        l_col = us_col0 + w_us - 1
        add((l_col, us_row0))
        for r in range(us_row0):
            add((l_col, r))
    # (5) 나머지 top cells (top-first / inner-first 우선 → cluster 유지)
    for r in range(H_top):
        for c in range(W):
            add((c, r))
    for i, p in enumerate(kb_ordered):
        if i < n_kb:
            grid[p] = '경상북도'

    # Bot region: 경남 + 부산
    bot_row0 = H_top
    bot_cells = [(c, r) for r in range(bot_row0, bot_row0 + H_bot) for c in range(W)]
    gn_pool = [p for p in bot_cells if p[0] < w_gn]
    bs_pool = [p for p in bot_cells if p[0] >= w_gn]

    # 경남 채우기 (top first)
    gn_pool.sort(key=lambda p: (p[1], p[0]))
    gn_short = n_gn - len(gn_pool)
    if gn_short > 0:
        # 경남이 col w_gn에 침투 (bot row부터, 부산과 인접)
        bs_west_col = [p for p in bs_pool if p[0] == w_gn]
        bs_west_col.sort(key=lambda p: (-p[1], p[0]))  # bot first
        for p in bs_west_col[:gn_short]:
            gn_pool.append(p)
            bs_pool.remove(p)
    for i, p in enumerate(gn_pool[:n_gn]):
        grid[p] = '경상남도'

    # 부산 채우기 (top first)
    bs_pool.sort(key=lambda p: (p[1], p[0]))
    for i, p in enumerate(bs_pool[:n_bs]):
        grid[p] = '부산광역시'

    return grid


def partition_yeongnam(by_sido, W, H):
    """LEGACY column-major (사용 안 함)."""
    n_us = len(by_sido.get('울산광역시', []))
    if n_us > H:
        return False  # 울산이 col 한 개에 못 들어감
    # 비-울산 cells
    OTHER_ORDER = {'경상남도': 0, '대구광역시': 1, '경상북도': 2, '부산광역시': 3}
    other_cells = []
    for sido_name, idx in OTHER_ORDER.items():
        for c in by_sido.get(sido_name, []):
            other_cells.append((idx, c))
    other_cells.sort(key=lambda x: (x[0], -x[1]['lat'], x[1]['lon']))
    if len(other_cells) > (W - 1) * H:
        return False  # cols 0..W-2에 못 들어감
    # cols 0..W-2 column-major
    for i, (_, cell) in enumerate(other_cells):
        cell['_yn_c'] = i // H
        cell['_yn_r'] = i % H
    # 울산 col W-1 rows 0..n_us-1
    us_cells = sorted(by_sido.get('울산광역시', []), key=lambda c: (-c['lat'], c['lon']))
    for i, cell in enumerate(us_cells):
        cell['_yn_c'] = W - 1
        cell['_yn_r'] = i
    return True


def partition_chungcheong(n_cn, n_sj, n_dj, n_cb, w_ch, h_ch):
    """w_ch × h_ch grid을 4 시도(충남·세종·대전·충북)로 partition.
    빈자리 없음 (n_cn+n_sj+n_dj+n_cb == w_ch × h_ch 가정).

    구조: 충남 좌 cols (bot_anchor) → 충남 last col top 빈자리 + 추가 2-col block에
          세종 + 대전 compact 배치 → 나머지 cells을 충북 (우측부터 fill).
    대전 P자/2-col compact 보장 (지렁이 방지).

    return: dict {(c,r): sido_name}"""
    grid = {}
    # 빈칸(waste)은 충남 남서(col 0 bottom)부터 위로 — 서해안 외곽 notch (갇힌 구멍 아님).
    waste = max(0, w_ch * h_ch - (n_cn + n_sj + n_dj + n_cb))
    blocked = {(0, h_ch - 1 - i) for i in range(min(waste, h_ch))}
    # 충남 좌, column-major bot_anchor (남서 blocked 회피 → 서해안 코너만 빔)
    cn_rem = n_cn
    last_cn_col = -1
    cn_last_col_cells = 0
    col = 0
    while cn_rem > 0 and col < w_ch:
        free = [h_ch - 1 - o for o in range(h_ch) if (col, h_ch - 1 - o) not in blocked]
        cells_in_col = min(cn_rem, len(free))
        for i in range(cells_in_col):
            grid[(col, free[i])] = '충청남도'
        cn_rem -= cells_in_col
        if cn_rem == 0:
            last_cn_col = col
            cn_last_col_cells = cells_in_col
        col += 1
    last_free = len([1 for o in range(h_ch) if (last_cn_col, h_ch - 1 - o) not in blocked]) if last_cn_col >= 0 else 0
    cn_last_col_empty = last_free - cn_last_col_cells if last_cn_col >= 0 else 0

    # 세종+대전 통합 영역: 충남 last col top 빈자리 + 추가 col(들).
    # 충남 last col에 남는 빈자리 cn_last_col_empty 셀, 추가 cells = sj+dj - 그것.
    sj_dj_total = n_sj + n_dj
    extra_needed = max(0, sj_dj_total - cn_last_col_empty)
    extra_cols_needed = math.ceil(extra_needed / h_ch) if extra_needed > 0 else 0

    # 세종+대전 positions: 충남 last col top + 추가 col 전체
    sj_dj_positions = []
    if last_cn_col >= 0 and cn_last_col_empty > 0:
        for r in range(cn_last_col_empty):
            sj_dj_positions.append((last_cn_col, r))
    for ec in range(extra_cols_needed):
        c = last_cn_col + 1 + ec if last_cn_col >= 0 else ec
        if c >= w_ch:
            break
        for r in range(h_ch):
            sj_dj_positions.append((c, r))

    # 정렬: (row, col) — top first, west first
    sj_dj_positions.sort(key=lambda p: (p[1], p[0]))

    # 세종 + 대전 할당
    for i, p in enumerate(sj_dj_positions):
        if i < n_sj:
            grid[p] = '세종특별자치시'
        elif i < n_sj + n_dj:
            grid[p] = '대전광역시'
        # 나머지 positions은 충북

    # 충북: 모든 남은 cells, 우측부터 fill (bot_anchor 비슷)
    cb_rem = n_cb
    for col in range(w_ch - 1, -1, -1):
        for r in range(h_ch):
            if cb_rem == 0:
                break
            if (col, r) not in grid and (col, r) not in blocked:
                grid[(col, r)] = '충청북도'
                cb_rem -= 1
    return grid


def find_chungcheong_wh(n_total, prefer_h=4, max_waste=3):
    """충청 W×H. 정사각보다 '하우스 높이'(prefer_h≈4행) 통일을 우선 — 회차마다 충청이
    3·4·5행으로 들쭉날쭉하지 않게. 정확 인수쌍이 없어도 빈칸 ≤ max_waste 허용하고,
    그 빈칸은 partition_chungcheong이 충남 남서(서해안) 외곽 notch로 둔다(갇힌 구멍 아님).
    예: 27석=4×7(빈칸1), 24석=4×6·28석=4×7(빈칸0)."""
    best = None
    for h in range(1, n_total + 1):
        w = math.ceil(n_total / h)
        waste = w * h - n_total
        if waste > max_waste:
            continue
        score = (abs(h - prefer_h), waste, abs(w - h))
        if best is None or score < best[0]:
            best = (score, w, h)
    return best[1], best[2]


def design_zone_S(zone_cells_by_sido):
    """S zone: 영남이 전체 오른쪽 (full height). 왼쪽은 충청 top + 호남 bot.
    영남 = 대구 wrap (경북) + 경남/부산/울산 bottom.
    충청: 빈자리 0 보장 — n_total의 인수쌍으로 W×H 결정."""
    호남_sidos = ['전북특별자치도', '전라북도', '전라남도', '광주광역시', '전남광주특별시']
    충청_sidos = ['충청남도', '충청북도', '세종특별자치시', '대전광역시']

    n_ho = sum(len(zone_cells_by_sido.get(s, [])) for s in 호남_sidos)
    n_ch = sum(len(zone_cells_by_sido.get(s, [])) for s in 충청_sidos)

    yn_plan = design_yeongnam(zone_cells_by_sido)
    w_yn = yn_plan['W_yn']

    # 충청: 하우스 높이 4행 우선(회차 간 통일). 빈칸은 충남 남서 외곽 notch.
    w_ch, h_ch = find_chungcheong_wh(n_ch, prefer_h=4)

    # 호남: 충청 W에 맞춰 + 영남 H에 맞춤 (Left H = 영남 H로 stretch)
    target_H_ho = yn_plan['H_yn'] - h_ch
    ho_plan = design_honam(zone_cells_by_sido, target_W=w_ch, target_H=target_H_ho)

    w_left = max(w_ch, ho_plan['W_ho'])
    H_left = h_ch + ho_plan['H_ho']
    H_S = max(yn_plan['H_yn'], H_left)

    zone_W = w_left + w_yn
    zone_H = H_S

    return {
        'zone_W': zone_W, 'zone_H': zone_H,
        'w_left': w_left, 'h_ch': h_ch, 'w_yn': w_yn, 'H_S': H_S,
        'w_ch': w_ch,
        'yn_plan': yn_plan, 'ho_plan': ho_plan,
    }


def design_zone_P(zone_cells_by_sido):
    n_p = len(zone_cells_by_sido.get('제주특별자치도', []))
    if n_p == 0:
        return {'zone_W': 0, 'zone_H': 0, 'w_p': 0, 'h_p': 0}
    # 한 줄로 (지리 — 제주는 한반도 남쪽 바다 위 섬, 가로 strip)
    h_p = 1
    w_p = n_p
    return {'zone_W': w_p, 'zone_H': h_p, 'w_p': w_p, 'h_p': h_p}


def layout_zone_N(zone_cells_by_sido, plan, col_offset, row_offset):
    """zone N cells에 c, r 부여.
    구조 (인천이 경기 wrap 밖, top-aligned):
      인천 [경기 top 위 서울]
      인천  서울  경기right  강원
      인천 [경기 bot 위 서울]
    """
    inner_row = row_offset + plan['top_h']
    # 인천 — 서울보다 1 row 아래로 시작 (row top_h은 경기 북부가 차지).
    # column-major from RIGHT: 동쪽 col (서울 인접) 우선 채움, 빈자리는 서쪽 outer col (강화도 쪽).
    # partial col은 bot-align (남부 인천 밀집 반영).
    # 2-pass: (1) lon 큰 → 작은 (east first), H씩 batch로 col에 분배
    #         (2) col 안 lat 큰 → 작은 (북 → 남)
    in_H = max(1, plan['inner_H'] - 1)
    in_cells = zone_cells_by_sido.get('인천광역시', [])
    in_W = plan['w_in']
    if in_cells and in_W > 0 and in_H > 0:
        in_by_lon = sorted(in_cells, key=lambda c: -c['lon'])
        n_in_cells = len(in_by_lon)
        full_cols = n_in_cells // in_H
        remainder = n_in_cells - full_cols * in_H
        idx = 0
        # full cols: east 먼저 (col in_W-1, in_W-2, ...)
        for batch_idx in range(full_cols):
            col_global = (in_W - 1) - batch_idx
            col_cells = sorted(in_by_lon[idx:idx + in_H], key=lambda c: -c['lat'])
            for row_idx, cell in enumerate(col_cells):
                cell['c'] = col_offset + col_global
                cell['r'] = inner_row + 1 + row_idx
            idx += in_H
        # partial col (leftmost = westernmost, col 0) — top-aligned
        # (cells 위쪽, 빈자리 아래쪽 → 강화도 등 서북 섬을 윗줄에 두는 인상)
        if remainder > 0:
            col_global = (in_W - 1) - full_cols
            col_cells = sorted(in_by_lon[idx:idx + remainder], key=lambda c: -c['lat'])
            for row_idx, cell in enumerate(col_cells):
                cell['c'] = col_offset + col_global
                cell['r'] = inner_row + 1 + row_idx
    # 서울 — 인천 우측, inner row range
    seoul_col0 = col_offset + plan['w_in']
    seoul_cells = zone_cells_by_sido.get('서울특별시', [])
    fill_rect(
        seoul_cells,
        col_start=seoul_col0, row_start=inner_row,
        W=plan['w_seoul'], H=plan['inner_H'],
        sort_key=None,
        partial_align='left_bot',
    )
    # 서울 직사각형의 빈칸(셀 수 < W×H일 때 마지막 줄 우측) → 경기가 메우게 위치 수집.
    seoul_filled = {(c['c'], c['r']) for c in seoul_cells}
    seoul_holes = [
        (seoul_col0 + cc, inner_row + rr)
        for rr in range(plan['inner_H'])
        for cc in range(plan['w_seoul'])
        if (seoul_col0 + cc, inner_row + rr) not in seoul_filled
    ]
    # 경기 wrap — top은 절반(extra row가 위 가득) + bot은 인천 전체 폭 영역 확보.
    # bot column-major에서 cells 부족 시 westmost col은 자연 탈락 (빈 col로 남음).
    top_extra = (plan['w_in'] + 1) // 2
    bot_extra = plan['w_in']
    fill_wrap_top_right_bot(
        zone_cells_by_sido.get('경기도', []),
        inner_col=seoul_col0, inner_row=inner_row,
        inner_W=plan['w_seoul'], inner_H=plan['inner_H'],
        top_h=plan['top_h'], right_w=plan['right_w'], bot_h=plan['bot_h'],
        bot_extra_left=bot_extra, top_extra_left=top_extra,
        in_extra_top_row=1, in_extra_w=plan['w_in'],
        inner_holes=seoul_holes,
    )
    # 강원 — 경기 right 옆, bot 정렬 (N zone 하단 = S zone 경북과 접촉)
    gw_cells = zone_cells_by_sido.get('강원특별자치도', []) + zone_cells_by_sido.get('강원도', [])
    h_gw = plan.get('h_gw', plan['inner_H'])
    gw_row_start = row_offset + plan['H_N'] - h_gw
    fill_rect(
        gw_cells,
        col_start=seoul_col0 + plan['w_seoul'] + plan['right_w'],
        row_start=gw_row_start,
        W=plan['w_gw'], H=h_gw,
        sort_key=None,
        partial_align='left_bot',
    )


def layout_zone_S(zone_cells_by_sido, plan, col_offset, row_offset):
    호남_sidos = ['전북특별자치도', '전라북도', '전라남도', '광주광역시', '전남광주특별시']
    충청_sidos = ['충청남도', '충청북도', '세종특별자치시', '대전광역시']
    영남_sidos = ['경상남도', '경상북도', '대구광역시', '울산광역시', '부산광역시']
    ho_cells = [c for s in 호남_sidos for c in zone_cells_by_sido.get(s, [])]
    ch_cells = [c for s in 충청_sidos for c in zone_cells_by_sido.get(s, [])]
    yn_cells = [c for s in 영남_sidos for c in zone_cells_by_sido.get(s, [])]

    # 영남 layout — blob mode (대구·울산 bot-aligned, 경남부산 직접 접촉)
    yn_plan = plan['yn_plan']
    yn_col0 = col_offset + plan['w_left']
    if yn_plan.get('mode') == 'blob':
        grid_map = partition_yeongnam_blob(zone_cells_by_sido, yn_plan)
        sido_positions = {}
        for (c, r), sido in grid_map.items():
            sido_positions.setdefault(sido, []).append((c, r))
        for sido, positions in sido_positions.items():
            sido_cells = list(zone_cells_by_sido.get(sido, []))
            # 2-pass: cells을 lat 순으로 row 그룹에 분배 (북 → 남)
            # 같은 row 안에서는 lon 순으로 col에 배치 (서 → 동)
            sido_cells.sort(key=lambda c: -c['lat'])
            row_to_positions = {}
            for p in positions:
                row_to_positions.setdefault(p[1], []).append(p)
            rows_sorted = sorted(row_to_positions.keys())
            cell_idx = 0
            for row in rows_sorted:
                row_positions = sorted(row_to_positions[row], key=lambda p: p[0])
                n_in_row = len(row_positions)
                row_cells = sido_cells[cell_idx:cell_idx + n_in_row]
                row_cells.sort(key=lambda c: c['lon'])  # west first
                for cell, pos in zip(row_cells, row_positions):
                    cell['c'] = yn_col0 + pos[0]
                    cell['r'] = row_offset + pos[1]
                cell_idx += n_in_row
    else:
        # wrap mode: 대구 inner + 경북 wrap + 경남/부산/울산 bottom stack
        dg_col = yn_col0 + yn_plan['left_w']
        dg_row = row_offset + yn_plan['top_h']
        fill_rect(
            zone_cells_by_sido.get('대구광역시', []),
            col_start=dg_col, row_start=dg_row,
            W=yn_plan['w_dg'], H=yn_plan['h_dg'],
            sort_key=None,
            partial_align='left_bot',
        )
        fill_wrap_top_left_right(
            zone_cells_by_sido.get('경상북도', []),
            inner_col=dg_col, inner_row=dg_row,
            inner_W=yn_plan['w_dg'], inner_H=yn_plan['h_dg'],
            top_h=yn_plan['top_h'], left_w=yn_plan['left_w'], right_w=yn_plan['right_w'],
        )
        bot_row = row_offset + yn_plan['top_h'] + yn_plan['h_dg']
        yn_bot_order = [('경상남도', zone_cells_by_sido.get('경상남도', [])),
                        ('부산광역시', zone_cells_by_sido.get('부산광역시', [])),
                        ('울산광역시', zone_cells_by_sido.get('울산광역시', []))]
        fill_horizontal_stack(
            yn_bot_order,
            col_start=yn_col0, row_start=bot_row,
            H=yn_plan['h_bot'],
            sort_key=None,
            partial_align='left_bot',
        )
    # 충청 perfect-fit layout: 좌(충남) | 중앙(세종 위 + 대전 아래) | 우(충북). 빈자리 0.
    n_cn = len(zone_cells_by_sido.get('충청남도', []))
    n_sj = len(zone_cells_by_sido.get('세종특별자치시', []))
    n_dj = len(zone_cells_by_sido.get('대전광역시', []))
    n_cb = len(zone_cells_by_sido.get('충청북도', []))
    w_ch = plan['w_ch']
    h_ch = plan['h_ch']
    grid_map = partition_chungcheong(n_cn, n_sj, n_dj, n_cb, w_ch, h_ch)
    # 시도별 positions 정리
    sido_positions = {}
    for (c, r), sido in grid_map.items():
        sido_positions.setdefault(sido, []).append((c, r))
    # 충청 right-align — 호남과 동일하게 우측(영남 boundary) 정렬. 충청 W < 호남 W일 때
    # 좌측정렬하면 충북이 영남에서 1칸 떨어져 T경계가 어긋남(충북이 왼쪽으로 밀림).
    ch_col_shift = plan['w_left'] - w_ch
    for sido, positions in sido_positions.items():
        cells_list = sorted(zone_cells_by_sido.get(sido, []), key=lambda c: (-c['lat'], c['lon']))
        positions_sorted = sorted(positions, key=lambda p: (p[1], p[0]))
        for cell, (c, r) in zip(cells_list, positions_sorted):
            cell['c'] = col_offset + ch_col_shift + c
            cell['r'] = row_offset + r
    # 호남 right-align: W_ho < w_left 면 좌측 비고 우측 정렬 (영남 boundary와 일치)
    ho_plan = plan['ho_plan']
    ho_col_shift = plan['w_left'] - ho_plan['W_ho']
    ho_col0 = col_offset + ho_col_shift
    ho_row0 = row_offset + plan['h_ch']
    # 전북 top — column-major from RIGHT (우측 col부터 위→아래 채움)
    # 빈자리는 좌측 col (서쪽 outer) — 호남 right-align과 일관
    # 2-pass: (1) lon으로 col 그룹핑 (east col 먼저), (2) col 내 lat sort (북→남)
    jb_cells = zone_cells_by_sido.get('전북특별자치도', []) + zone_cells_by_sido.get('전라북도', [])
    jb_W = ho_plan['total_w']
    jb_H = ho_plan['top_h_jb']
    if jb_cells and jb_W > 0 and jb_H > 0:
        # (1) lon 큰 → 작은 (east first) 정렬해서 H씩 batch로 col에 분배
        jb_by_lon = sorted(jb_cells, key=lambda c: -c['lon'])
        for batch_idx in range(jb_W):
            start = batch_idx * jb_H
            end = min(start + jb_H, len(jb_by_lon))
            if start >= end:
                break
            col_global = (jb_W - 1) - batch_idx  # east col 먼저
            # (2) col 안에서 lat 큰 → 작은 (북 → 남)
            col_cells = sorted(jb_by_lon[start:end], key=lambda c: -c['lat'])
            for row_idx, cell in enumerate(col_cells):
                cell['c'] = ho_col0 + col_global
                cell['r'] = ho_row0 + row_idx
    # 광주 inner block
    gj_col = ho_col0 + ho_plan['left_w']
    gj_row = ho_row0 + ho_plan['top_h_jb']
    fill_rect(
        zone_cells_by_sido.get('광주광역시', []),
        col_start=gj_col, row_start=gj_row,
        W=ho_plan['w_gj'], H=ho_plan['h_gj'],
        sort_key=None,
        partial_align='left_bot',
    )
    # 광주 box 안 빈자리 (광주 셀이 못 채운 위치) → 전남이 메움
    gj_placed_set = {(c['c'], c['r']) for c in zone_cells_by_sido.get('광주광역시', []) if 'c' in c}
    gj_box_empty = []
    for cc in range(ho_plan['w_gj']):
        for rr in range(ho_plan['h_gj']):
            p = (gj_col + cc, gj_row + rr)
            if p not in gj_placed_set:
                gj_box_empty.append(p)
    # 전남 wrap (좌·우·아래) + 광주 빈자리 메움
    jn_cells = zone_cells_by_sido.get('전라남도', [])
    fill_wrap_left_right_bot(
        jn_cells,
        inner_col=gj_col, inner_row=gj_row,
        inner_W=ho_plan['w_gj'], inner_H=ho_plan['h_gj'],
        left_w=ho_plan['left_w'], right_w=ho_plan['right_w'], bot_h=ho_plan['bot_h'],
        extra_positions=gj_box_empty,
    )


def layout_zone_P(zone_cells_by_sido, plan, col_offset, row_offset):
    p_cells = zone_cells_by_sido.get('제주특별자치도', [])
    fill_rect(
        p_cells,
        col_start=col_offset, row_start=row_offset,
        W=plan['w_p'], H=plan['h_p'],
        sort_key=None,
        partial_align='left_bot',
    )


def manual_layout(cells):
    # 시도별 그룹
    by_sido = defaultdict(list)
    for c in cells:
        if 'lon' not in c:
            continue
        by_sido[c['sido']].append(c)

    # zone plans
    plan_N = design_zone_N(by_sido)
    plan_S = design_zone_S(by_sido)
    plan_P = design_zone_P(by_sido)

    # 전역 bbox: max zone_W
    bbox_W = max(plan_N['zone_W'], plan_S['zone_W'], plan_P['zone_W'])

    # zone 중앙 정렬 (col_offset)
    n_col_offset = (bbox_W - plan_N['zone_W']) // 2
    s_col_offset = (bbox_W - plan_S['zone_W']) // 2
    # 제주: 호남 아래 좌측 정렬 (호남 actual leftmost col에 맞춤)
    # 호남 right-aligned with shift = w_left - W_ho. 제주도 그 col에 시작.
    ho_shift = plan_S['w_left'] - plan_S['ho_plan']['W_ho']
    p_col_offset = s_col_offset + ho_shift

    row_off = 0
    layout_zone_N(by_sido, plan_N, n_col_offset, row_off)
    row_off += plan_N['zone_H']
    s_row_start = row_off
    layout_zone_S(by_sido, plan_S, s_col_offset, row_off)
    row_off += plan_S['zone_H']
    # 제주는 호남 실제 cells bot에서 1 행 떨어뜨려 배치 (영남 길이 무관)
    if plan_P['zone_H'] > 0:
        ho_sidos = ['전북특별자치도', '전라북도', '전라남도', '광주광역시']
        ho_rows = [c['r'] for s in ho_sidos for c in by_sido.get(s, []) if 'r' in c]
        if ho_rows:
            row_off = max(ho_rows) + 2  # 호남 실제 bot + 1 row gap
    layout_zone_P(by_sido, plan_P, p_col_offset, row_off)
    row_off += plan_P['zone_H']

    return row_off, bbox_W


def process(path: Path, dry: bool, backup: bool):
    cells = json.loads(path.read_text(encoding='utf-8'))
    by_code, by_name = load_centroids()
    missing = []
    for c in cells:
        cent = cell_centroid(c, by_code, by_name)
        if cent is None:
            missing.append(c.get('name', c.get('code', '?')))
            continue
        c['lon'], c['lat'] = cent
    rows, W = manual_layout(cells)
    for c in cells:
        c.pop('lon', None); c.pop('lat', None)
    valid = [c for c in cells if 'c' in c]
    info = {
        'path': str(path.relative_to(ROOT)),
        'n': len(valid),
        'bbox': f'{W}×{rows}',
        'missing': missing,
    }
    if not dry:
        if backup:
            bak = path.with_suffix(path.suffix + '.manual.bak')
            if not bak.exists():
                shutil.copy2(path, bak)
        path.write_text(json.dumps(cells, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--no-backup', action='store_true')
    args = ap.parse_args()
    paths = [ROOT / p if not Path(p).is_absolute() else Path(p) for p in (args.paths or DEFAULT_TARGETS)]
    paths = [p for p in paths if p.exists()]
    print(f'[build_zone_hex] {len(paths)} files\n')
    for p in paths:
        info = process(p, dry=args.dry, backup=not args.no_backup)
        print(f"{info['path']}")
        print(f"  n={info['n']} bbox={info['bbox']}")
        if info['missing']:
            print(f"  missing: {len(info['missing'])} → {info['missing'][:3]}")


if __name__ == '__main__':
    main()
