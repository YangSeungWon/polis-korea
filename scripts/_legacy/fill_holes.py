"""시군구 hex의 내부 홀을 슬라이드로 메우는 후처리.

알고리즘:
1. 모든 내부 홀(빈 자리인데 ≥4 occupied 이웃) 검출
2. 각 홀 H에서 occupied cells 따라 BFS
   → peripheral cell C 발견 (자기 위치의 occupied 이웃 < 4)
3. C부터 H로 이어지는 path를 따라 cell들을 한 칸씩 H 쪽으로 슬라이드
4. H 채워지고, C의 원래 자리는 외곽 빈 자리 (홀 아님)
5. 같은 시도 내에서 슬라이드 우선 (시도 응집 보존)

사용:
  .venv/bin/python scripts/_legacy/fill_holes.py [--in PATH] [--out PATH]
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IN = ROOT / "data" / "geo" / "sigungu_hex.json"
DEFAULT_OUT = ROOT / "data" / "geo" / "sigungu_hex.json"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _hex import offset_neighbors  # noqa: E402


def find_holes(occupied):
    """≥4 occupied 이웃을 가진 빈 자리들."""
    cs = [c for c, r in occupied]
    rs = [r for c, r in occupied]
    holes = []
    for r in range(min(rs), max(rs) + 1):
        for c in range(min(cs), max(cs) + 1):
            if (c, r) in occupied:
                continue
            n = sum(1 for nb in offset_neighbors(c, r) if nb in occupied)
            if n >= 4:
                holes.append((c, r))
    return holes


def occ_neighbor_count(pos, occupied):
    return sum(1 for nb in offset_neighbors(*pos) if nb in occupied)


def find_slide_path(hole, occupied, prefer_sido=None, max_depth=30, protect_sidos=None):
    """홀에서 BFS, peripheral cell까지 path 찾기.

    peripheral 조건: 그 cell 위치의 occupied 이웃 수 < 4 (= 그 자리가 빈 자리 됐을 때 hole 아님).
    같은 시도 우선 (시도 응집 보존).
    return: [hole_adj_cell, ..., peripheral_cell] (occupied cell들의 좌표 리스트, hole 다음 칸부터 peripheral 끝까지)
    """
    # 우선 같은 시도 path, 못 찾으면 시도 무시 path
    for restrict_sido in ([prefer_sido] if prefer_sido else [None]) + [None]:
        if restrict_sido is None and prefer_sido is None:
            pass  # 중복 방지
        # BFS
        visited = {hole}
        queue = deque()
        # 1st level: hole의 occupied 이웃
        for nb in offset_neighbors(*hole):
            if nb in occupied:
                if protect_sidos and occupied[nb]['sido'] in protect_sidos:
                    continue
                if restrict_sido and occupied[nb]['sido'] != restrict_sido:
                    continue
                queue.append([nb])
                visited.add(nb)
        while queue:
            path = queue.popleft()
            cur = path[-1]
            # peripheral?
            if occ_neighbor_count(cur, occupied) - 1 < 4:
                # cur이 슬라이드되어 빠지면 그 자리의 occupied 이웃은 변하지 않지만,
                # cur 자리 자체가 빈 자리가 됐을 때 그 자리의 occupied 이웃 수를 본다.
                # occ_neighbor_count(cur, occupied)는 cur의 6 이웃 중 occupied 수.
                # cur 자리가 빈 자리 됐을 때 그 자리의 occupied 이웃 수 = 그 값 그대로.
                # 단, 만약 hole→cur path 상 cur 다음 칸(occupied이지만 우리가 옮길 칸)이 있다면 그것도 -1.
                # 정확히: cur이 빈 자리 됐을 때, cur의 이웃 중 path 안에 있는 cell(우리가 cur로 옮길 cell)
                # 만 자리에서 빠지진 않음 — 우리는 path를 hole 쪽으로 1칸씩 미는 거라 cur 다음 칸도 비게 됨.
                # 즉 cur가 마지막이면, cur는 빈 자리, cur의 occupied 이웃 그대로.
                # 그래서 cur 위치의 occupied 이웃이 <4면 OK.
                n = occ_neighbor_count(cur, occupied)
                if n < 4:
                    return path
            if len(path) >= max_depth:
                continue
            for nb in offset_neighbors(*cur):
                if nb in visited or nb not in occupied:
                    continue
                if protect_sidos and occupied[nb]['sido'] in protect_sidos:
                    continue
                if restrict_sido and occupied[nb]['sido'] != restrict_sido:
                    continue
                visited.add(nb)
                queue.append(path + [nb])
    return None


def fill_one_hole(hole, occupied, protect_sidos=None):
    """홀 H를 슬라이드로 메움. occupied 갱신. 성공 시 True."""
    # 주변 시도 중 가장 많은 시도 (시도 응집 위해 그 시도 path 선호)
    from collections import Counter
    sido_count = Counter()
    for nb in offset_neighbors(*hole):
        if nb in occupied:
            if protect_sidos and occupied[nb]['sido'] in protect_sidos:
                continue
            sido_count[occupied[nb]['sido']] += 1
    prefer_sido = sido_count.most_common(1)[0][0] if sido_count else None

    path = find_slide_path(hole, occupied, prefer_sido=prefer_sido, protect_sidos=protect_sidos)
    if path is None:
        return False
    # 슬라이드: path = [C1, C2, ..., Cn]
    # C1 (hole 인접) → hole로 이동
    # C2 → C1 자리로 이동
    # ...
    # Cn → Cn-1 자리로 이동
    # Cn 자리는 빈 자리 (외곽 hole 아님)
    new_positions = [hole] + path[:-1]
    moved_records = []  # (cell, old_pos, new_pos)
    for i, old_pos in enumerate(path):
        cell = occupied[old_pos]
        new_pos = new_positions[i]
        moved_records.append((cell, old_pos, new_pos))
    # 실제 적용 — 한 번에 (occupied dict 업데이트)
    # 우선 path 셀들 다 제거
    for _, old_pos, _ in moved_records:
        del occupied[old_pos]
    # 그 후 새 위치로 다시 add
    for cell, _, new_pos in moved_records:
        cell['c'], cell['r'] = new_pos
        occupied[new_pos] = cell
    return True


def run(data, max_passes=8, verbose=True, protect_sidos=None):
    occupied = {(d['c'], d['r']): d for d in data}
    for pass_n in range(max_passes):
        holes = find_holes(occupied)
        if not holes:
            if verbose:
                print(f'pass {pass_n + 1}: 홀 0 — 종료', file=sys.stderr)
            break
        if verbose:
            print(f'pass {pass_n + 1}: 홀 {len(holes)}', file=sys.stderr)
        filled = 0
        # 가장 둘러싸인 홀부터 (안쪽부터 메움)
        holes.sort(key=lambda h: -occ_neighbor_count(h, occupied))
        for hole in holes:
            # 다시 확인 (이전 슬라이드로 occupied 변했을 수 있음)
            if hole in occupied: continue
            if occ_neighbor_count(hole, occupied) < 4: continue
            if fill_one_hole(hole, occupied, protect_sidos=protect_sidos):
                filled += 1
                if verbose:
                    print(f'  filled {hole}', file=sys.stderr)
        if filled == 0:
            if verbose:
                print(f'  더 못 메움 — 종료', file=sys.stderr)
            break
    return list(occupied.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='in_path', type=Path, default=DEFAULT_IN)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    data = json.loads(args.in_path.read_text(encoding='utf-8'))
    print(f'입력 {len(data)} cells from {args.in_path.name}', file=sys.stderr)
    result = run(data)
    args.out.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    print(f'출력 {len(result)} cells → {args.out.name}', file=sys.stderr)


if __name__ == '__main__':
    main()
