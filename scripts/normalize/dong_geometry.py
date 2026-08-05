"""과거 동이 현 선거구 하나에 온전히 들어가는지 **폴리곤으로** 확인한다.

이름만 믿으면 조용히 틀린다. 부천은 2019년에 36개 동을 10개 광역동으로 합쳤다가
2024년에 3개 구·37개 동으로 되돌렸다. 2020년 '중동'(광역동)과 2024년 '중동'은
이름이 같지만 크기가 다르다. 이름으로 이으면 큰 덩어리 표가 작은 동에 붙는다.

그리고 이름이 정확히 이어져도 재집계가 안 되는 경우가 있다. 2020년 부천동은
2024년 부천시갑 72.7% / 부천시병 27.3%로 **선거구 경계를 가로지른다**. 동 단위로는
나눌 수 없고, 면적·인구로 쪼개는 건 추정이라 하지 않는다. 이런 곳은 `context_only`다.

    읍면동 자료가 있다 ≠ 모든 획정 변경을 재집계할 수 있다.

결과는 data/geography/dong_membership/ 에 캐시한다 — 재집계 엔진이 실행 때
shapefile을 읽지 않아도 되게.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data/geography/dong_membership"

# 회차 → (경계 shapefile, 인코딩, 코드 필드, 이름 필드). 필드명이 연도마다 다르다.
SHP = {
    21: ("data/raw/sgis/bnd_dong_2020/bnd_dong_00_2020_4Q.shp", "cp949",
         "ADM_DR_CD", "ADM_DR_NM"),
    22: ("data/raw/sgis/bnd_dong_2025/bnd_dong_00_2025_2Q.shp", "utf-8",
         "ADM_CD", "ADM_NM"),
}
MIN_SHARE = 0.02        # 이 이상이 다른 선거구에 걸리면 가로지르는 것으로 본다


def _read(rnd: int):
    import shapefile
    p, enc, cdf, nmf = SHP[rnd]
    sf = shapefile.Reader(str(ROOT / p), encoding=enc)
    f = [x[0] for x in sf.fields[1:]]
    ic, inm = f.index(cdf), f.index(nmf)
    return sf, ic, inm


def _prefixes(rnd: int, names: set[str]) -> set[str]:
    """이름 집합을 덮는 시군구 코드 접두들.

    동명이동이 흔해서(반송동·중동·남구…) 이름만으로는 못 고른다. 그렇다고 하나만
    고를 수도 없다 — 선거구가 여러 시군구에 걸치고, 군위군처럼 시도를 옮겨 가면
    (경북→대구, 2023) 회차마다 접두가 달라진다. 많이 맞는 것부터 욕심껏 덮는다.
    """
    import collections
    sf, ic, inm = _read(rnd)
    by: dict = collections.defaultdict(set)
    for r in sf.records():
        n = str(r[inm])
        if n in names:
            by[str(r[ic])[:4]].add(n)
    out, seen = set(), set()
    for pfx, ns in sorted(by.items(), key=lambda x: -len(x[1])):
        if ns - seen:                 # 새로 덮는 이름이 있을 때만 채택
            out.add(pfx)
            seen |= ns
    return out


def _polys(rnd: int, pfx: set[str], keep: set[str] | None = None) -> dict:
    from shapely.geometry import shape
    from shapely.ops import unary_union
    sf, ic, inm = _read(rnd)
    out: dict = {}
    for sr in sf.shapeRecords():
        c, n = str(sr.record[ic]), str(sr.record[inm])
        if c[:4] in pfx and (keep is None or n in keep):
            g = shape(sr.shape.__geo_interface__)
            out[n] = unary_union([out[n], g]) if n in out else g
    return out


def membership(cur: int, prev: int, fixture: str,
               cur_dmap: dict[str, str], prev_dongs: set[str]) -> dict:
    """과거 동 → {현 선거구: 면적비}. 캐시가 있으면 그대로 쓴다."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{cur}__{prev}_{fixture or 'all'}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))

    pfx_c = _prefixes(cur, set(cur_dmap))
    pfx_p = _prefixes(prev, prev_dongs)
    if not pfx_c or not pfx_p:
        return {}
    cur_g = _polys(cur, pfx_c, set(cur_dmap))
    prev_g = _polys(prev, pfx_p, prev_dongs)

    out: dict = {}
    for n, g in prev_g.items():
        if g.area <= 0:
            continue
        sh: dict = {}
        for m, h in cur_g.items():
            if g.intersects(h):
                r = g.intersection(h).area / g.area
                if r > 0.005:
                    sh[cur_dmap[m]] = round(sh.get(cur_dmap[m], 0) + r, 4)
        out[n] = sh
    res = {
        "_note": ("과거 동이 현 선거구에 걸치는 면적비. 표를 이 비율로 나누는 데 쓰지 "
                  "않는다 — 가로지르는지 판정하는 데만 쓴다. 면적비 배분은 추정이다."),
        "current": cur, "previous": prev, "fixture": fixture,
        "membership": out,
        "crossing": sorted(n for n, sh in out.items()
                           if len([1 for v in sh.values() if v > MIN_SHARE]) > 1),
    }
    f.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def resolve(cur: int, prev: int, fixture: str, cur_dmap: dict[str, str],
            prev_dongs: set[str]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """과거 동 → 현 선거구(단일). 가로지르는 동은 **닿는 선거구 목록과 함께** 돌려준다.

    가로지르는 동 하나 때문에 그 시군구 전체를 막지 않는다. 고양시는 흥도동만
    갑·병에 걸치는데 을·정까지 막으면 멀쩡한 비교를 버리는 것이다.
    """
    m = membership(cur, prev, fixture, cur_dmap, prev_dongs)
    if not m:
        return {}, {}
    ok, cross = {}, {}
    for n, sh in m["membership"].items():
        big = sorted(k for k, v in sh.items() if v > MIN_SHARE)
        if len(big) == 1:
            ok[n] = big[0]
        elif len(big) > 1:
            cross[n] = big
    return ok, cross
