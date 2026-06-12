"""지역구 hex 카토그램의 둘러싸인 빈칸(hole) 제거 — slide-fill.

district_hex_cartogram(centroid 비닝)이 남기는, 점유 셀에 둘러싸인 빈 격자칸을 메운다.
hole→외곽 인접 점유셀 최단경로를 찾아 경로 위 셀을 1칸씩 hole 쪽으로 밀어(slide) hole을
닫음(외곽에 닿은 셀의 빈자리는 외부와 연결돼 새 hole 안 생김). 셀 수·메타 보존, 기존
튜닝 레이아웃을 최소 왜곡(경로 셀만 1칸 이동). generate() 전체 재배치를 피함.

재현: python scripts/build/fill_district_hex_holes.py [--apply] [n ...]
"""
import json, sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data" / "geo"


def _nbrs(c, r):
    return ([(c - 1, r - 1), (c, r - 1), (c - 1, r), (c + 1, r), (c - 1, r + 1), (c, r + 1)]
            if r % 2 == 0 else
            [(c, r - 1), (c + 1, r - 1), (c - 1, r), (c + 1, r), (c, r + 1), (c + 1, r + 1)])


def _exterior(occ, c0, c1, r0, r1):
    """경계 박스 밖 코너에서 빈칸을 flood — 외부와 연결된 빈칸 집합."""
    start = (c0, r0)
    seen = {start}
    q = deque([start])
    while q:
        c, r = q.popleft()
        for nc, nr in _nbrs(c, r):
            if c0 <= nc <= c1 and r0 <= nr <= r1 and (nc, nr) not in occ and (nc, nr) not in seen:
                seen.add((nc, nr))
                q.append((nc, nr))
    return seen


def _holes(occ):
    cs = [c for c, r in occ]
    rs = [r for c, r in occ]
    c0, c1, r0, r1 = min(cs) - 2, max(cs) + 2, min(rs) - 2, max(rs) + 2
    ext = _exterior(occ, c0, c1, r0, r1)
    return [(c, r) for c in range(c0, c1 + 1) for r in range(r0, r1 + 1)
            if (c, r) not in occ and (c, r) not in ext], ext


def fill(cells, log=None):
    occ = {(c["c"], c["r"]): c for c in cells}
    moves = 0
    for _ in range(200):
        holes, ext = _holes(occ)
        if not holes:
            break
        h = holes[0]
        # hole에서 점유셀을 따라 BFS → 외부에 인접한 점유셀(target)까지 경로
        par = {h: None}
        q = deque([h])
        target = None
        while q:
            cur = q.popleft()
            if cur != h and any(nb in ext for nb in _nbrs(*cur)):
                target = cur
                break
            for nb in _nbrs(*cur):
                if nb not in par and nb in occ:
                    par[nb] = cur
                    q.append(nb)
        if target is None:
            if log:
                log.append(f"  hole {h}: 외곽 경로 없음 — skip")
            break
        path = []
        cur = target
        while cur is not None:
            path.append(cur)
            cur = par[cur]
        path.reverse()  # [hole, p1, ..., target]
        # 경로 셀을 hole 쪽으로 1칸씩 이동 (path[i] → path[i-1])
        for i in range(1, len(path)):
            cell = occ.pop(path[i])
            cell["c"], cell["r"] = path[i - 1]
            occ[path[i - 1]] = cell
        if log:
            chain = " → ".join(f"{path[i]}" for i in range(len(path)))
            log.append(f"  hole {h} 메움: {len(path) - 1}칸 이동 ({chain})")
        moves += 1
    return moves


def main():
    args = sys.argv[1:]
    apply = "--apply" in args
    ns = [int(a) for a in args if a.isdigit()] or list(range(1, 23))
    for n in ns:
        p = GEO / f"district_hex_{n}.json"
        if not p.exists():
            continue
        cells = json.loads(p.read_text())
        log = []
        moves = fill(cells, log)
        if not moves:
            continue
        print(f"{n}대: hole {moves}개 메움")
        for line in log:
            print(line)
        if apply:
            # 0 기준 정규화 후 저장
            cs = [c["c"] for c in cells]
            rs = [c["r"] for c in cells]
            mc, mr = min(cs), min(rs)
            for c in cells:
                c["c"] -= mc
                c["r"] -= mr
            p.write_text(json.dumps(cells, ensure_ascii=False))
            print(f"  ✓ {p.name} 저장")


if __name__ == "__main__":
    main()
