"""hex 격자의 둘러싸인 빈칸(hole) 제거 — slide-fill.

district_hex_cartogram(centroid 비닝)이 남기는, 점유 셀에 둘러싸인 빈 격자칸을 메운다.
hole→외곽 인접 점유셀 최단경로를 찾아 경로 위 셀을 1칸씩 hole 쪽으로 밀어(slide) hole을
닫음(외곽에 닿은 셀의 빈자리는 외부와 연결돼 새 hole 안 생김). 셀 수·메타 보존, 기존
튜닝 레이아웃을 최소 왜곡(경로 셀만 1칸 이동). generate() 전체 재배치를 피함.

⚠️ 지역구(district_hex_*)만이 아니라 **시군구 hex에도 필요하다.** build_zone_hex는
"내부 빈칸 0"을 목표로 적어 뒀지만 실제로는 못 지킨다 — 9회 영남 70셀을
그 구조(대구 3×3 · 울산 3×2 L · 경북 wrap · 경남/부산 bot)로 놓으면 **빈칸 0인
후보가 아예 없고** 최소가 2다. 그 둘 중 하나가 바깥으로 못 나가고 (12,10)에
갇혔다(이웃: 대구 동구·울산 북구·경북 영천시·청송군). 경북이 공간을 더 받은 게
아니다 — 22칸으로 실제 시군구 수와 정확히 같다. 모양의 문제고, 이 slide-fill이
정확히 그걸 고친다.

재현:
  python scripts/build/fill_district_hex_holes.py [--apply] [n ...]      # 지역구
  python scripts/build/fill_district_hex_holes.py [--apply] --path P     # 아무 hex 파일
    (셀에 sido가 있으면 시도 연결성을 지키는 이동만 고른다)
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


def _split_groups(occ, key):
    """key(예: sido) 값별로 셀이 두 덩어리 이상으로 끊긴 그룹들의 집합.

    "쪼개진 게 없어야 한다"가 아니라 "더 쪼개면 안 된다"로 쓴다 — district_hex_4·5·16은
    이미 시도가 끊겨 있어서(centroid 비닝의 결과) 절대 기준을 걸면 어떤 이동도 못 고른다.
    """
    if key is None:
        return frozenset()
    split = set()
    groups = {}
    for pos, cell in occ.items():
        groups.setdefault(cell.get(key), set()).add(pos)
    for name, members in groups.items():
        start = next(iter(members))
        seen, q = {start}, deque([start])
        while q:
            cur = q.popleft()
            for nb in _nbrs(*cur):
                if nb in members and nb not in seen:
                    seen.add(nb)
                    q.append(nb)
        if len(seen) != len(members):
            split.add(name)
    return frozenset(split)


def _slide(occ, path):
    """path[i] → path[i-1]로 1칸씩 민 새 배치. 셀 객체는 그대로 옮겨 담고 좌표는
    아직 안 쓴다 — 후보를 시험만 하고 버릴 수 있어야 하므로."""
    out = dict(occ)
    for i in range(1, len(path)):
        out[path[i - 1]] = out.pop(path[i])
    return out


def fill(cells, log=None, group_key=None):
    """hole을 slide-fill로 메운다.

    group_key를 주면(시군구 hex는 "sido") 그 묶음을 **더** 쪼개지 않는 이동만 고른다. 이게 없으면 hole은 사라지지만 시도가 쪼개진다 — 실제로 sigungu_hex에서
    포항시를 (13,10)→(12,10)으로 밀자 (13,11) 경북 셀이 울산·빈칸에 둘러싸여 고립됐다.
    지역구 hex는 셀마다 독립이라 group_key 없이 쓴다.
    """
    occ = {(c["c"], c["r"]): c for c in cells}
    split0 = _split_groups(occ, group_key)
    moves = 0
    for _ in range(200):
        holes, ext = _holes(occ)
        if not holes:
            break
        h = holes[0]
        # hole에서 점유셀을 따라 BFS. 외곽에 닿은 점유셀마다 그 경로로 밀어 보고,
        # 묶음이 안 쪼개지는 첫 후보를 쓴다(가장 짧은 이동).
        par = {h: None}
        q = deque([h])
        chosen = None
        while q and chosen is None:
            cur = q.popleft()
            if cur != h and any(nb in ext for nb in _nbrs(*cur)):
                path = []
                node = cur
                while node is not None:
                    path.append(node)
                    node = par[node]
                path.reverse()  # [hole, p1, ..., target]
                trial = _slide(occ, path)
                broke = _split_groups(trial, group_key) - split0
                if not broke:
                    chosen = (path, trial)
                    break
                if log is not None:
                    log.append(f"  hole {h}: {path[-1]} 경로는 {'·'.join(sorted(broke))} 분절 — 다음 후보")
            for nb in _nbrs(*cur):
                if nb not in par and nb in occ:
                    par[nb] = cur
                    q.append(nb)
        if chosen is None:
            if log is not None:
                log.append(f"  hole {h}: 쓸 수 있는 외곽 경로 없음 — skip")
            break
        path, trial = chosen
        occ = trial
        if log is not None:
            chain = " → ".join(str(p) for p in path)
            log.append(f"  hole {h} 메움: {len(path) - 1}칸 이동 ({chain})")
        moves += 1
    for pos, cell in occ.items():
        cell["c"], cell["r"] = pos
    return moves


def main():
    args = sys.argv[1:]
    apply = "--apply" in args
    paths = [Path(args[i + 1]) for i, a in enumerate(args) if a == "--path"]
    if not paths:
        ns = [int(a) for a in args if a.isdigit()] or list(range(1, 23))
        paths = [GEO / f"district_hex_{n}.json" for n in ns]
    for p in paths:
        n = p.stem
        if not p.exists():
            continue
        doc = json.loads(p.read_text())
        # sigungu_hex_local.json은 회차 키 dict, 나머지는 셀 배열.
        groups = doc.items() if isinstance(doc, dict) else [("", doc)]
        total = 0
        for key, cells in groups:
            if not isinstance(cells, list) or not cells or "c" not in cells[0]:
                continue
            log = []
            # 시군구 hex는 셀이 시도로 묶여 있다 — 묶음을 더 쪼개는 이동은 고르면 안 된다.
            gk = "sido" if all("sido" in c for c in cells) else None
            moves = fill(cells, log, group_key=gk)
            if not moves:
                continue
            total += moves
            print(f"{n}{':' + key if key else ''}: hole {moves}개 메움")
            for line in log:
                print(line)
            # 0 기준 정규화
            mc = min(c["c"] for c in cells)
            mr = min(c["r"] for c in cells)
            for c in cells:
                c["c"] -= mc
                c["r"] -= mr
        if total and apply:
            p.write_text(json.dumps(doc, ensure_ascii=False))
            print(f"  ✓ {p.name} 저장")


if __name__ == "__main__":
    main()
