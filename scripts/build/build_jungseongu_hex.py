"""중선거구(9~12대) 조랭이떡 hex — 1선거구 2인 당선 → 인접한 두 칸.

소선거구(13대~)는 1선거구=1칸이지만, 중선거구는 1구 2인이라 셀이 적어 T자 배치가
sparse했음. 각 선거구를 두 칸으로(조랭이떡) → ① 밀도 2배(sparse 해소) ② 당선자 2명을
각 칸 단색으로 명시. 렌더(render-district.js)는 셀의 wi(당선자 인덱스)로 ws[wi] 색칠.

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


def build(n):
    hex_path = ROOT / f"data/geo/district_hex_{n}.json"
    cells = json.loads(hex_path.read_text(encoding="utf-8"))
    # 이미 조랭이떡(wi 있음)이면 선거구별 1개로 축약해 재생성 (멱등).
    if any(c.get("wi") is not None for c in cells):
        seen, base = set(), []
        for c in cells:
            if c["name"] in seen:
                continue
            seen.add(c["name"])
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
