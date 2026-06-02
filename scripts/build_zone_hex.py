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
  python3 scripts/build_zone_hex.py
"""
from __future__ import annotations
import argparse
import json
import math
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


def fill_rect(cells, col_start, row_start, W, H, sort_key=None, partial_align='left_top'):
    """cells을 col_start..col_start+W-1, row_start..row_start+H-1 직사각형에 채움.
    sort_key: 정렬 기준 (default: (-lat, lon) — 위 row 위쪽 lat 큰 cell)
    partial_align: 마지막 row 미달 시 정렬 — 'left_top'/'right_top'/'left_bot'/'right_bot'.
    """
    if not cells:
        return
    if sort_key is None:
        sort_key = lambda c: (-c['lat'], c['lon'])
    sorted_cells = sorted(cells, key=sort_key)
    N = len(sorted_cells)
    capacity = W * H
    # 마지막 row 미달분
    full_rows = N // W
    remainder = N - full_rows * W
    # partial row 정렬 결정
    rows_filled = []
    if partial_align in ('left_bot', 'right_bot'):
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
        right_align = partial_align in ('right_top', 'right_bot')
        if right_align and count < W:
            col_offset = W - count
        else:
            col_offset = 0
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
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='left_top',
    )
    fill_rect(
        left_cells,
        col_start=inner_col - left_w, row_start=inner_row,
        W=left_w, H=inner_H,
        sort_key=lambda c: (-c['lat'], c['lon']),
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


def fill_wrap_top_right_bot(cells, inner_col, inner_row, inner_W, inner_H, top_h, right_w, bot_h):
    """경기 wrap — inner block 위·우·아래 둘러쌈.
    cells lat 분포로 top/right/bot 분배:
      top wrap: 가장 높은 lat 시군구 (위 row 일수록 lat 더 큼)
      bot wrap: 가장 낮은 lat
      right wrap: 중간 lat + 높은 lon (또는 단순히 남은 cells)
    """
    if not cells:
        return
    total_wrap_w = inner_W + right_w
    N_top = top_h * total_wrap_w
    N_bot = bot_h * total_wrap_w
    N_right = right_w * inner_H
    N_total = N_top + N_right + N_bot
    cells_sorted = sorted(cells, key=lambda c: -c['lat'])
    # cells_sorted: lat 큰 → 작은
    # top: 가장 lat 큰 N_top cells
    # bot: 가장 lat 작은 N_bot cells
    # right: 중간 N_right cells
    n_actual = len(cells_sorted)
    # 남은 empty 분배: top/right/bot 비례. 단순화 — top·bot에 empty 우선
    # 일단 cells_sorted 전체를 top → right → bot 순으로 채움 (lat 내림차순)
    # top section 채울 cell 수 = min(N_top, available)
    # 다음 right section, bot section
    take_top = min(N_top, n_actual)
    take_right = min(N_right, n_actual - take_top)
    take_bot = min(N_bot, n_actual - take_top - take_right)
    top_cells = cells_sorted[:take_top]
    right_cells = cells_sorted[take_top:take_top + take_right]
    bot_cells = cells_sorted[take_top + take_right:take_top + take_right + take_bot]

    # top wrap: row inner_row-top_h .. inner_row-1, col inner_col .. inner_col+total_wrap_w-1
    # 안에서 lat 내림차순 row, lon 오름차순 col
    fill_rect(
        top_cells,
        col_start=inner_col,
        row_start=inner_row - top_h,
        W=total_wrap_w, H=top_h,
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='left_top',  # 미달 시 위쪽 outer
    )
    # right wrap: rows inner_row..inner_row+inner_H-1, cols inner_col+inner_W..inner_col+inner_W+right_w-1
    fill_rect(
        right_cells,
        col_start=inner_col + inner_W,
        row_start=inner_row,
        W=right_w, H=inner_H,
        sort_key=lambda c: (-c['lat'], -c['lon']),  # 위쪽 row lat 큰, 같은 row lon 큰
        partial_align='right_top',  # 미달 시 우측 outer
    )
    # bot wrap: row inner_row+inner_H..inner_row+inner_H+bot_h-1
    fill_rect(
        bot_cells,
        col_start=inner_col,
        row_start=inner_row + inner_H,
        W=total_wrap_w, H=bot_h,
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='left_bot',  # 미달 시 아래쪽 outer
    )


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

    # 인천: W 같은 H로
    w_in = math.ceil(n_in / inner_H) if inner_H else 0
    # 서울 정확 fit 확인
    if n_seoul > 0 and w_seoul * inner_H < n_seoul:
        # 부족 — H 늘려야
        inner_H = math.ceil(n_seoul / w_seoul)
        w_in = math.ceil(n_in / inner_H) if inner_H else 0

    inner_W = w_in + w_seoul

    # 경기 wrap: top + right + bot. right_w, top_h, bot_h 결정
    # cells = (top_h + bot_h)*(inner_W + right_w) + right_w * inner_H
    # 작은 wrap 부터 시도
    best = None
    for right_w in range(1, 4):
        for top_h in range(1, 4):
            for bot_h in range(1, 4):
                cap = (top_h + bot_h) * (inner_W + right_w) + right_w * inner_H
                if cap >= n_gg:
                    waste = cap - n_gg
                    # 작은 waste 우선, 같은 waste면 wrap 두께 균형
                    score = (waste, abs(top_h - bot_h), right_w + top_h + bot_h)
                    if best is None or score < best[0]:
                        best = (score, right_w, top_h, bot_h, cap)
    if best is None:
        right_w, top_h, bot_h = 1, 1, 1
    else:
        _, right_w, top_h, bot_h, _ = best

    # 강원: 경기 right 옆 column. inner_H 높이.
    w_gw = math.ceil(n_gw / inner_H) if (inner_H and n_gw) else 0

    zone_W = inner_W + right_w + w_gw
    zone_H = top_h + inner_H + bot_h

    return {
        'zone_W': zone_W, 'zone_H': zone_H,
        'top_h': top_h, 'bot_h': bot_h, 'right_w': right_w,
        'inner_W': inner_W, 'inner_H': inner_H,
        'w_in': w_in, 'w_seoul': w_seoul, 'w_gw': w_gw,
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


def fill_wrap_left_right_bot(cells, inner_col, inner_row, inner_W, inner_H, left_w, right_w, bot_h):
    """3-side wrap (left + right + bot). top 무. inner block의 좌·우·아래 둘러쌈."""
    if not cells:
        return
    total_w = left_w + inner_W + right_w
    cells_sorted = sorted(cells, key=lambda c: -c['lat'])
    n = len(cells_sorted)
    N_left = left_w * inner_H
    N_right = right_w * inner_H
    N_bot = bot_h * total_w
    # 위쪽 inner 옆 (left+right): lat 중간 cells. bot은 가장 아래 (lat 낮은).
    # 분배: 위에서부터 left+right (lat 큰), 그 다음 bot (lat 작은)
    middle_count = min(N_left + N_right, n)
    bot_count = min(N_bot, n - middle_count)
    middle = cells_sorted[:middle_count]
    bot_cells_arr = cells_sorted[middle_count:middle_count + bot_count]
    middle_lon = sorted(middle, key=lambda c: c['lon'])
    take_left = min(N_left, len(middle_lon))
    left_cells = middle_lon[:take_left]
    right_cells = middle_lon[take_left:]
    fill_rect(
        left_cells,
        col_start=inner_col - left_w, row_start=inner_row,
        W=left_w, H=inner_H,
        sort_key=lambda c: (-c['lat'], c['lon']),
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
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='left_bot',
    )


def design_honam(zone_cells_by_sido):
    """호남 sub-layout: 광주 inner + 전남 wrap (left+right+bot) + 전북 top.
    광주 shape + 전남 wrap 동시 최적화 — waste 최소 + 연결성 보장."""
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
                    jn_waste = cap - n_jn
                    asym = abs(left_w - right_w)
                    score = (gj_waste + jn_waste, asym, bot_h + left_w + right_w, h_gj * 10 + w_gj)
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
    """영남 sub-layout: 대구 inner + 경북 wrap (top+left+right) + 경남/부산/울산 bottom stack."""
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
    return {
        'W_yn': W_yn, 'H_yn': H_yn,
        'top_h': top_h, 'left_w': left_w, 'right_w': right_w,
        'h_dg': h_dg, 'w_dg': w_dg,
        'h_bot': h_bot, 'w_gn': w_gn, 'w_bs': w_bs, 'w_us': w_us,
        'total_top_w': total_top_w,
    }


def design_zone_S(zone_cells_by_sido):
    """S zone: 영남이 전체 오른쪽 (full height). 왼쪽은 충청 top + 호남 bot.
    영남 = 대구 wrap (경북) + 경남/부산/울산 bottom."""
    호남_sidos = ['전북특별자치도', '전라북도', '전라남도', '광주광역시', '전남광주특별시']
    충청_sidos = ['충청남도', '충청북도', '세종특별자치시', '대전광역시']

    n_ho = sum(len(zone_cells_by_sido.get(s, [])) for s in 호남_sidos)
    n_ch = sum(len(zone_cells_by_sido.get(s, [])) for s in 충청_sidos)

    yn_plan = design_yeongnam(zone_cells_by_sido)
    ho_plan = design_honam(zone_cells_by_sido)
    w_yn = yn_plan['W_yn']

    # 충청 시도별 stack width — 시도별 W = ceil(n/h_ch). Sum이 충청 stripe 실제 width.
    ch_counts = [len(zone_cells_by_sido.get(s, [])) for s in
                 ['충청남도', '세종특별자치시', '대전광역시', '충청북도']]

    # h_ch 결정: 충청 stack 너비 + 호남 너비 균형, S zone height도 영남과 맞춤.
    best = None
    for h_ch_try in range(1, max(2, n_ch + 1)):
        ch_widths = [math.ceil(c / h_ch_try) if c else 0 for c in ch_counts]
        w_ch_stack = sum(ch_widths)
        w_left = max(w_ch_stack, ho_plan['W_ho'])
        # 호남 row count
        H_left = h_ch_try + ho_plan['H_ho']
        H_S_try = max(yn_plan['H_yn'], H_left)
        zone_W_try = w_left + w_yn
        # 컴팩트 — 전체 bbox + waste 최소
        ch_waste = h_ch_try * w_left - n_ch
        if ch_waste < 0:
            continue
        score = (zone_W_try + H_S_try, ch_waste, h_ch_try)
        if best is None or score < best[0]:
            best = (score, h_ch_try, w_ch_stack, w_left, H_S_try)
    _, h_ch, w_ch_stack, w_left, H_S = best

    zone_W = w_left + w_yn
    zone_H = H_S

    return {
        'zone_W': zone_W, 'zone_H': zone_H,
        'w_left': w_left, 'h_ch': h_ch, 'w_yn': w_yn, 'H_S': H_S,
        'yn_plan': yn_plan, 'ho_plan': ho_plan,
    }


def design_zone_P(zone_cells_by_sido):
    n_p = len(zone_cells_by_sido.get('제주특별자치도', []))
    if n_p == 0:
        return {'zone_W': 0, 'zone_H': 0, 'w_p': 0, 'h_p': 0}
    h_p = max(1, round(math.sqrt(n_p)))
    w_p = math.ceil(n_p / h_p)
    return {'zone_W': w_p, 'zone_H': h_p, 'w_p': w_p, 'h_p': h_p}


def layout_zone_N(zone_cells_by_sido, plan, col_offset, row_offset):
    """zone N cells에 c, r 부여."""
    inner_row = row_offset + plan['top_h']
    # 인천: cols [col_offset, col_offset+w_in), rows [inner_row, inner_row+inner_H)
    fill_rect(
        zone_cells_by_sido.get('인천광역시', []),
        col_start=col_offset, row_start=inner_row,
        W=plan['w_in'], H=plan['inner_H'],
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='right_bot',  # 인천 우측이 서울에 붙어야 → 마지막 cell들이 우측 (서울 인접)
    )
    # 서울
    fill_rect(
        zone_cells_by_sido.get('서울특별시', []),
        col_start=col_offset + plan['w_in'], row_start=inner_row,
        W=plan['w_seoul'], H=plan['inner_H'],
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='left_bot',
    )
    # 경기 wrap
    gg_cells = zone_cells_by_sido.get('경기도', [])
    fill_wrap_top_right_bot(
        gg_cells,
        inner_col=col_offset, inner_row=inner_row,
        inner_W=plan['inner_W'], inner_H=plan['inner_H'],
        top_h=plan['top_h'], right_w=plan['right_w'], bot_h=plan['bot_h'],
    )
    # 강원: 경기 right 옆
    gw_cells = zone_cells_by_sido.get('강원특별자치도', []) + zone_cells_by_sido.get('강원도', [])
    fill_rect(
        gw_cells,
        col_start=col_offset + plan['inner_W'] + plan['right_w'], row_start=inner_row,
        W=plan['w_gw'], H=plan['inner_H'],
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='left_bot',
    )


def layout_zone_S(zone_cells_by_sido, plan, col_offset, row_offset):
    호남_sidos = ['전북특별자치도', '전라북도', '전라남도', '광주광역시', '전남광주특별시']
    충청_sidos = ['충청남도', '충청북도', '세종특별자치시', '대전광역시']
    영남_sidos = ['경상남도', '경상북도', '대구광역시', '울산광역시', '부산광역시']
    ho_cells = [c for s in 호남_sidos for c in zone_cells_by_sido.get(s, [])]
    ch_cells = [c for s in 충청_sidos for c in zone_cells_by_sido.get(s, [])]
    yn_cells = [c for s in 영남_sidos for c in zone_cells_by_sido.get(s, [])]

    # 영남: 대구 inner + 경북 wrap + 경남/부산/울산 bottom stack
    yn_plan = plan['yn_plan']
    yn_col0 = col_offset + plan['w_left']
    # 대구 inner block 위치
    dg_col = yn_col0 + yn_plan['left_w']
    dg_row = row_offset + yn_plan['top_h']
    fill_rect(
        zone_cells_by_sido.get('대구광역시', []),
        col_start=dg_col, row_start=dg_row,
        W=yn_plan['w_dg'], H=yn_plan['h_dg'],
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='left_bot',
    )
    # 경북 wrap top+left+right
    fill_wrap_top_left_right(
        zone_cells_by_sido.get('경상북도', []),
        inner_col=dg_col, inner_row=dg_row,
        inner_W=yn_plan['w_dg'], inner_H=yn_plan['h_dg'],
        top_h=yn_plan['top_h'], left_w=yn_plan['left_w'], right_w=yn_plan['right_w'],
    )
    # 영남 bottom: 경남 → 부산 → 울산 (lon 오름차순)
    bot_row = row_offset + yn_plan['top_h'] + yn_plan['h_dg']
    yn_bot_order = [('경상남도', zone_cells_by_sido.get('경상남도', [])),
                    ('부산광역시', zone_cells_by_sido.get('부산광역시', [])),
                    ('울산광역시', zone_cells_by_sido.get('울산광역시', []))]
    fill_horizontal_stack(
        yn_bot_order,
        col_start=yn_col0, row_start=bot_row,
        H=yn_plan['h_bot'],
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='left_bot',
    )
    # 충청 top (left side) — 충남(서) → 세종 → 대전 → 충북(동)
    ch_order = ['충청남도', '세종특별자치시', '대전광역시', '충청북도']
    ch_pairs = [(s, zone_cells_by_sido.get(s, [])) for s in ch_order]
    fill_horizontal_stack(
        ch_pairs,
        col_start=col_offset, row_start=row_offset,
        H=plan['h_ch'],
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='left_bot',  # partial을 stripe 아래쪽으로 — 위 row 빈자리 줄여 시도 인접 보장
    )
    # 호남: 전북 top + 전남 wrap (좌·우·아래) + 광주 inner
    ho_plan = plan['ho_plan']
    ho_col0 = col_offset
    ho_row0 = row_offset + plan['h_ch']
    # 전북 top
    jb_cells = zone_cells_by_sido.get('전북특별자치도', []) + zone_cells_by_sido.get('전라북도', [])
    fill_rect(
        jb_cells,
        col_start=ho_col0, row_start=ho_row0,
        W=ho_plan['total_w'], H=ho_plan['top_h_jb'],
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='left_top',
    )
    # 광주 inner block
    gj_col = ho_col0 + ho_plan['left_w']
    gj_row = ho_row0 + ho_plan['top_h_jb']
    fill_rect(
        zone_cells_by_sido.get('광주광역시', []),
        col_start=gj_col, row_start=gj_row,
        W=ho_plan['w_gj'], H=ho_plan['h_gj'],
        sort_key=lambda c: (-c['lat'], c['lon']),
        partial_align='left_bot',
    )
    # 전남 wrap (좌·우·아래)
    jn_cells = zone_cells_by_sido.get('전라남도', [])
    fill_wrap_left_right_bot(
        jn_cells,
        inner_col=gj_col, inner_row=gj_row,
        inner_W=ho_plan['w_gj'], inner_H=ho_plan['h_gj'],
        left_w=ho_plan['left_w'], right_w=ho_plan['right_w'], bot_h=ho_plan['bot_h'],
    )


def layout_zone_P(zone_cells_by_sido, plan, col_offset, row_offset):
    p_cells = zone_cells_by_sido.get('제주특별자치도', [])
    fill_rect(
        p_cells,
        col_start=col_offset, row_start=row_offset,
        W=plan['w_p'], H=plan['h_p'],
        sort_key=lambda c: (-c['lat'], c['lon']),
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
    p_col_offset = (bbox_W - plan_P['zone_W']) // 2

    row_off = 0
    layout_zone_N(by_sido, plan_N, n_col_offset, row_off)
    row_off += plan_N['zone_H']
    layout_zone_S(by_sido, plan_S, s_col_offset, row_off)
    row_off += plan_S['zone_H']
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
