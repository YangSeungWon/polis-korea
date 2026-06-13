"""중선거구(9~12대) 조랭이떡 hex — 1선거구 2인 당선 → 인접한 두 칸.

소선거구(13대~)는 1선거구=1칸이지만, 중선거구는 1구 2인이라 셀이 적어 T자 배치가
sparse했음. 각 선거구를 두 칸으로(조랭이떡) → ① 밀도 2배(sparse 해소) ② 당선자 2명을
각 칸 단색으로 명시. 렌더(geomap.ts: renderDistrictHex)는 셀의 wi(당선자 인덱스)로 ws[wi] 색칠.

배치: 같은 선거구의 두 칸을 같은 centroid(_cen)로 복제 → build_zone_hex(T자, 시도 연결
보장)에 먹임. 같은 _cen이라 연속 배정돼 거의 인접(쌍). 그 뒤 위치로 wi(서=0·동=1) 부여.

출력: data/geo/district_hex_{n}.json = [{sido, name, _cen, c, r, wi}, ...] (선거구당 2개)
사용: python3 scripts/build/build_jungseongu_hex.py [9 10 11 12]
"""
from __future__ import annotations
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_zone_hex  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _nbrs(c, r):
    e = r % 2
    return [(c - 1, r), (c + 1, r), (c - 1 + e, r - 1), (c + e, r - 1),
            (c - 1 + e, r + 1), (c + e, r + 1)]


def _pair_adjacent(cells):
    if len(cells) != 2:
        return True  # 손댈 수 없음 — 분리로 안 셈
    a = (cells[0]["c"], cells[0]["r"])
    b = (cells[1]["c"], cells[1]["r"])
    return b in _nbrs(*a)


def repair_pairs(placed, rounds=300):
    """분리된 조랭이떡 쌍을 시도 내부 스왑으로 인접화. 같은 시도 안에서만 위치를
    교환 → 시도 연결성(점유 위치 집합 불변) 보존. greedy: 두 선거구의 분리 수가
    줄어드는 스왑만 채택."""
    bydist = defaultdict(list)
    for c in placed:
        bydist[(c["sido"], c["name"])].append(c)
    pos = {(c["c"], c["r"]): c for c in placed}

    def split2(k):  # 0 if 쌍 인접, 1 if 분리
        return 0 if _pair_adjacent(bydist[k]) else 1

    for _ in range(rounds):
        improved = False
        splits = [k for k, v in bydist.items() if len(v) == 2 and not _pair_adjacent(v)]
        for key in splits:
            sido, name = key
            cells = bydist[key]
            if len(cells) != 2:
                continue
            moved = False
            for endp, other in ((cells[0], cells[1]), (cells[1], cells[0])):
                for npos in _nbrs(other["c"], other["r"]):
                    tgt = pos.get(npos)
                    if not tgt or tgt["sido"] != sido or tgt["name"] == name:
                        continue
                    tkey = (sido, tgt["name"])
                    before = split2(key) + split2(tkey)
                    # 위치 스왑
                    endp["c"], endp["r"], tgt["c"], tgt["r"] = tgt["c"], tgt["r"], endp["c"], endp["r"]
                    pos[(endp["c"], endp["r"])] = endp
                    pos[(tgt["c"], tgt["r"])] = tgt
                    if split2(key) + split2(tkey) < before:
                        improved = moved = True
                        break
                    # 되돌림
                    endp["c"], endp["r"], tgt["c"], tgt["r"] = tgt["c"], tgt["r"], endp["c"], endp["r"]
                    pos[(endp["c"], endp["r"])] = endp
                    pos[(tgt["c"], tgt["r"])] = tgt
                if moved:
                    break
        if not improved:
            break
    return placed


def _perfect_matching(positions):
    """positions(셀 (c,r) 목록)을 인접한 쌍(도미노)으로 완전매칭. 백트래킹.
    불가하면 None."""
    posset = set(positions)
    adj = {p: [q for q in _nbrs(*p) if q in posset] for p in positions}
    matched = {}

    def bt(remaining):
        if not remaining:
            return True
        # 선택지 가장 적은 칸부터 (실패 빠르게)
        p = min(remaining, key=lambda x: sum(1 for q in adj[x] if q in remaining))
        for q in [q for q in adj[p] if q in remaining]:
            remaining.discard(p); remaining.discard(q)
            matched[p] = q; matched[q] = p
            if bt(remaining):
                return True
            remaining.add(p); remaining.add(q)
            del matched[p]; del matched[q]
        return False

    if not bt(set(positions)):
        return None
    seen, dominoes = set(), []
    for p in positions:
        if p in seen:
            continue
        q = matched[p]
        seen.add(p); seen.add(q)
        dominoes.append((p, q))
    return dominoes


def retile_split_sidos(placed):
    """분리쌍이 남은 시도를 도미노 타일링으로 재배치 — 위치를 인접 쌍으로 완전매칭하고,
    선거구를 현재 centroid 기준으로 도미노에 배정(이동 최소). 경기 wrap처럼 스왑으로
    못 붙는 쌍을 보장 인접화. 점유 위치 집합 불변 → 시도 연결성 보존."""
    try:
        import numpy as np
        from scipy.optimize import linear_sum_assignment
    except Exception:
        return placed
    bysido = defaultdict(list)
    for c in placed:
        bysido[c["sido"]].append(c)
    for sido, cells in bysido.items():
        bydist = defaultdict(list)
        for c in cells:
            bydist[c["name"]].append(c)
        if any(len(v) != 2 for v in bydist.values()):
            continue  # 쌍이 아닌 게 있으면 건드리지 않음
        if all(_pair_adjacent(v) for v in bydist.values()):
            continue  # 이미 전부 인접
        positions = [(c["c"], c["r"]) for c in cells]
        dominoes = _perfect_matching(positions)
        if not dominoes:
            continue  # 타일링 불가 → 그대로
        names = list(bydist.keys())
        dcent = {nm: (sum(c["c"] for c in v) / 2, sum(c["r"] for c in v) / 2)
                 for nm, v in bydist.items()}
        mcent = [((p[0] + q[0]) / 2, (p[1] + q[1]) / 2) for p, q in dominoes]
        cost = np.zeros((len(names), len(dominoes)))
        for i, nm in enumerate(names):
            dc = dcent[nm]
            for j, mc in enumerate(mcent):
                cost[i][j] = (dc[0] - mc[0]) ** 2 + (dc[1] - mc[1]) ** 2
        ri, cj = linear_sum_assignment(cost)
        for i, j in zip(ri, cj):
            cellpair = bydist[names[i]]
            pospair = sorted(dominoes[j])
            for cell, pos in zip(cellpair, pospair):
                cell["c"], cell["r"] = pos
    return placed


def build(n):
    hex_path = ROOT / f"data/geo/district_hex_{n}.json"
    cells = json.loads(hex_path.read_text(encoding="utf-8"))
    # 이미 조랭이떡(wi 있음)이면 선거구별 1개로 축약해 재생성 (멱등).
    if any(c.get("wi") is not None for c in cells):
        seen, base = set(), []
        for c in cells:
            key = (c["sido"], c["name"])  # name만 쓰면 동명 선거구(시도 다른) 1개 드롭됨
            if key in seen:
                continue
            seen.add(key)
            base.append({k: c[k] for k in ("sido", "name", "_cen") if k in c})
        cells = base
    n_sgg = len(cells)

    # 1) 선거구당 2칸 복제 (같은 _cen/sido/name)
    doubled = [{"sido": c["sido"], "name": c["name"], "_cen": c["_cen"]}
               for c in cells for _ in range(2)]
    hex_path.write_text(json.dumps(doubled, ensure_ascii=False), encoding="utf-8")

    # 2) build_zone_hex(T자) 배치 — 시도 연결 보장, 같은 _cen이라 쌍 인접
    build_zone_hex.process(hex_path, dry=False, backup=False)

    # 3) 분리 쌍 repair (시도 내부 스왑 — 홀수 행 경계에서 갈라진 쌍 인접화)
    placed = json.loads(hex_path.read_text(encoding="utf-8"))
    repair_pairs(placed)
    # 3.5) 스왑으로 못 붙은 쌍(경기 wrap 등) → 도미노 타일링 재배치로 보장 인접
    retile_split_sidos(placed)

    # 4) 위치로 wi 부여 (서=0·동=1). 같은 선거구 두 칸을 c(있으면 r)로 정렬.
    by_name = defaultdict(list)
    for c in placed:
        by_name[(c["sido"], c["name"])].append(c)
    for k, pair in by_name.items():
        pair.sort(key=lambda c: (c["c"], c["r"]))
        for wi, c in enumerate(pair):
            c["wi"] = wi
    hex_path.write_text(json.dumps(placed, ensure_ascii=False), encoding="utf-8")
    n_split = sum(1 for k, v in by_name.items() if len(v) == 2 and not _pair_adjacent(v))
    w = max(c["c"] for c in placed) + 1
    h = max(c["r"] for c in placed) + 1
    print(f"{n}대: {n_sgg}선거구 → {len(placed)}칸 (조랭이떡), {w}×{h}, 분리쌍 {n_split}")


if __name__ == "__main__":
    ns = [int(a) for a in sys.argv[1:]] or [9, 10, 11, 12]
    for n in ns:
        build(n)
