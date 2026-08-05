"""선거구 폴리곤 출처 정합성 감사 — 차이가 표현 문제인지 실제 경계인지 가른다.

lineage의 `comparable == "unknown"` 141건이 출처가 다른 3쌍(21↔20·6↔5·2↔1)에만
몰려 있다. 그 원인을 **수치로 분해**한다. 폴리곤을 새로 구하기 전에 할 일이다.

한 방향 overlap만 보면 원인을 놓친다. 한쪽이 단순화돼 조금 작아졌다면 한 방향은
99%인데 다른 방향은 95%다 — IoU 하나로 압축하면 그 비대칭이 사라진다.

사용: python3 scripts/audit/audit_geometry_sources.py --pair 21 20
"""
from __future__ import annotations
import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"


def load(n: int) -> dict:
    from shapely.geometry import shape
    d = json.loads((GEO / f"district_{n}_geojson.json").read_text(encoding="utf-8"))
    out = {}
    for f in d.get("features", []):
        p = f.get("properties") or {}
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        out[f"{p.get('SIDO', '')} {p.get('SGG', '')}".strip()] = g
    return out


def vertices(n: int) -> int:
    d = json.loads((GEO / f"district_{n}_geojson.json").read_text(encoding="utf-8"))
    tot = 0
    for f in d.get("features", []):
        g = f["geometry"]
        if g["type"] == "Polygon":
            tot += sum(len(r) for r in g["coordinates"])
        else:
            tot += sum(len(r) for poly in g["coordinates"] for r in poly)
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", nargs=2, type=int, required=True, metavar=("CUR", "PREV"))
    args = ap.parse_args()
    cur_n, prev_n = args.pair
    B, A = load(cur_n), load(prev_n)
    same = sorted(set(A) & set(B))

    print(f"\n─ {cur_n}대 ↔ {prev_n}대 폴리곤 정합성 ─\n")
    va, vb = vertices(prev_n), vertices(cur_n)
    aa = sum(g.area for g in A.values())
    ab = sum(g.area for g in B.values())
    print(f"  {'':18}{prev_n:>10}대{cur_n:>10}대")
    print(f"  {'선거구':18}{len(A):>11}{len(B):>11}")
    print(f"  {'vertex/선거구':18}{va // len(A):>11}{vb // len(B):>11}"
          f"   ← {vb / len(B) / (va / len(A)):.1f}배")
    print(f"  {'총면적(deg²)':18}{aa:>11.3f}{ab:>11.3f}"
          f"   ← {(ab / aa - 1) * 100:+.2f}%")

    # ── 계통 offset — 측지계가 다르면 전체가 한 방향으로 밀린다 ─────────────
    dx = [B[k].centroid.x - A[k].centroid.x for k in same]
    dy = [B[k].centroid.y - A[k].centroid.y for k in same]
    print(f"\n  centroid 이동 (같은 이름 {len(same)}쌍)")
    print(f"    경도 중앙 {statistics.median(dx) * 111000:+7.1f}m"
          f" · 위도 중앙 {statistics.median(dy) * 111000:+7.1f}m")
    sys_off = max(abs(statistics.median(dx)), abs(statistics.median(dy))) * 111000
    print(f"    → 계통 offset {'있음' if sys_off > 100 else '없음'}"
          f" ({sys_off:.0f}m) — 있으면 측지계 차이를 먼저 맞춰야 한다")

    # ── 단순화로 설명되는가 ─────────────────────────────────────────────────
    print(f"\n  같은 tolerance로 단순화했을 때 90~97% 구간이 줄어드는가")
    print(f"    {'tolerance':>10}{'≈m':>7}{'90~97':>8}{'중앙 overlap':>13}")
    for tol in (0, 0.001, 0.005):
        band, mins = 0, []
        for k in same:
            a = A[k].simplify(tol, preserve_topology=True) if tol else A[k]
            b = B[k].simplify(tol, preserve_topology=True) if tol else B[k]
            if not a.is_valid:
                a = a.buffer(0)
            if not b.is_valid:
                b = b.buffer(0)
            i = b.intersection(a).area
            m = min(i / b.area if b.area else 0, i / a.area if a.area else 0)
            mins.append(m)
            if 0.90 <= m < 0.97:
                band += 1
        print(f"    {tol:>10}{tol * 111000:>7.0f}{band:>8}{statistics.median(mins) * 100:>12.1f}%")

    # ── 양방향 overlap — 비대칭이 단순화의 지문이다 ─────────────────────────
    fwd = [B[k].intersection(A[k]).area / B[k].area for k in same if B[k].area]
    bwd = [B[k].intersection(A[k]).area / A[k].area for k in same if A[k].area]
    print(f"\n  양방향 overlap 중앙")
    print(f"    현재가 이전에 담긴 비율  {statistics.median(fwd) * 100:5.1f}%")
    print(f"    이전이 현재에 담긴 비율  {statistics.median(bwd) * 100:5.1f}%")
    asym = abs(statistics.median(fwd) - statistics.median(bwd)) * 100
    print(f"    → 비대칭 {asym:.1f}%p — 크면 한쪽이 단순화된 것,"
          f" 작으면 서로 다른 경계다")

    # ── 어디에 몰리는가 ─────────────────────────────────────────────────────
    low = [(k, B[k].intersection(A[k]).area / max(A[k].area, B[k].area)) for k in same]
    low.sort(key=lambda x: x[1])
    c = collections.Counter(k.split()[0] for k, v in low if v < 0.9)
    print(f"\n  overlap<90% {sum(c.values())}곳의 시도 분포")
    print(f"    {dict(c.most_common(8))}")
    print(f"    → 도시에 몰리면 실제 인구 재획정, 고르면 데이터 문제다")
    print(f"\n  가장 낮은 5곳: " + ", ".join(f"{k}({v * 100:.0f}%)" for k, v in low[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
