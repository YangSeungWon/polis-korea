"""과거 동이 현 선거구 하나에 온전히 들어가는지 **폴리곤으로** 확인한다.

## 이름은 identity가 아니다 — 동에서도 그렇다

전국 21대 자료에서 **동 이름 223종이 둘 이상의 시군구에 걸친다**(강남동·검단동·
가산면…). 시군구 하나씩 돌릴 땐 안 보이다가 전국 실행에서 다른 도시의 표가 섞였다.
대조군 검증(경계가 그대로인 선거구에서 direct와 reaggregated가 수렴하는지)이 이걸
잡았다 — 서울 영등포구을은 동 구성이 양 회차 완전히 같은데 delta가 5.2%p 어긋났다.

그래서 동의 키를 **SGIS 행정동 코드**로 잡는다. 코드는 시군구 안에서 이름으로 찾는다 —
그 범위 안에서는 이름이 유일하다. 이름은 표시용이다.

## 이름이 이어져도 재집계가 안 되는 경우

부천은 2019년에 36개 동을 10개 광역동으로 합쳤다가 2024년에 되돌렸다. 2020년
'중동'(광역동)과 2024년 '중동'은 이름이 같은데 크기가 다르다. 그리고 2020년 부천동은
2024년 부천시갑 72.7% / 부천시병 27.3%로 **선거구 경계를 가로지른다**. 동 단위로는
나눌 수 없고 면적·인구로 쪼개는 건 추정이라 하지 않는다. 이런 곳은 `context_only`다.

    읍면동 자료가 있다 ≠ 모든 획정 변경을 재집계할 수 있다.

결과는 data/geography/dong_membership/ 에 캐시한다.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data/geography/dong_membership"

# 회차 → (경계 shapefile, 인코딩, 코드 필드, 이름 필드). 필드명이 연도마다 다르다.
SHP = {
    20: ("data/raw/sgis/bnd_dong_2016/bnd_dong_00_2016_4Q.shp", "cp949",
         "ADM_CD", "ADM_NM"),
    21: ("data/raw/sgis/bnd_dong_2020/bnd_dong_00_2020_4Q.shp", "cp949",
         "ADM_DR_CD", "ADM_DR_NM"),
    22: ("data/raw/sgis/bnd_dong_2025/bnd_dong_00_2025_2Q.shp", "utf-8",
         "ADM_CD", "ADM_NM"),
}
MIN_SHARE = 0.02        # 이 이상이 다른 선거구에 걸치면 가로지르는 것으로 본다
_RD: dict = {}


def ukey(sgg_code: str, dong: str) -> str:
    """동의 키 — 시군구를 반드시 붙인다. 이름만으로는 전국에서 223종이 충돌한다."""
    return f"{sgg_code}:{dong}"


def _read(rnd: int):
    if rnd not in _RD:
        import shapefile
        p, enc, cdf, nmf = SHP[rnd]
        sf = shapefile.Reader(str(ROOT / p), encoding=enc)
        f = [x[0] for x in sf.fields[1:]]
        ic, inm = f.index(cdf), f.index(nmf)
        _RD[rnd] = (sf, ic, inm, [(str(r[ic]), str(r[inm])) for r in sf.records()])
    return _RD[rnd]


def _sgg_prefix(recs: list, names: set[str]) -> str | None:
    """한 시군구의 동 이름 집합 → SGIS 코드 접두. 그 범위 안에서만 이름을 믿는다."""
    sc: collections.Counter = collections.Counter()
    for c, n in recs:
        if n in names:
            sc[c[:4]] += 1
    return sc.most_common(1)[0][0] if sc else None


def dong_codes(rnd: int, blocks: list[dict]) -> dict[str, str]:
    """{시군구코드:동이름 → SGIS 행정동코드}. 시군구별로 좁혀 찾는다."""
    _, _, _, recs = _read(rnd)
    by_pfx: dict = collections.defaultdict(dict)
    for c, n in recs:
        by_pfx[c[:4]].setdefault(n, c)
    out: dict[str, str] = {}
    for b in blocks:
        names = {r["dong"] for r in b["rows"] if r["dong"]}
        pfx = _sgg_prefix(recs, names)
        if not pfx:
            continue
        for n in names:
            c = by_pfx[pfx].get(n)
            if c:
                out[ukey(b["sgg_code"], n)] = c
    return out


def _polys(rnd: int, codes: set[str]) -> dict:
    """SGIS 코드 → 폴리곤. 같은 코드가 여러 조각이면 합친다."""
    from shapely.geometry import shape
    from shapely.ops import unary_union
    sf, ic, _, _ = _read(rnd)
    out: dict = {}
    for sr in sf.shapeRecords():
        c = str(sr.record[ic])
        if c not in codes:
            continue
        g = shape(sr.shape.__geo_interface__)
        out[c] = unary_union([out[c], g]) if c in out else g
    return out


def membership(cur: int, prev: int, fixture: str, cur_blocks: list[dict],
               prev_blocks: list[dict], cur_dmap: dict[str, str]) -> dict:
    """과거 동(시군구코드:이름) → {현 선거구: 면적비}. 캐시가 있으면 그대로 쓴다."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{cur}__{prev}_{fixture or 'all'}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))

    cur_code = dong_codes(cur, cur_blocks)
    prev_code = dong_codes(prev, prev_blocks)
    code_to_d = {c: cur_dmap[k] for k, c in cur_code.items() if k in cur_dmap}
    cur_g = _polys(cur, set(code_to_d))
    prev_g = _polys(prev, set(prev_code.values()))

    # 전국이면 양쪽 3,500개씩이라 전수 교차(1,200만 회)는 못 끝낸다. 공간 색인으로
    # 후보를 좁힌다 — 판정 결과는 같고 속도만 다르다.
    from shapely.strtree import STRtree
    codes = list(cur_g)
    tree = STRtree([cur_g[c] for c in codes])

    out: dict = {}
    for k, pc in prev_code.items():
        g = prev_g.get(pc)
        if g is None or g.area <= 0:
            continue
        sh: dict = {}
        for i in tree.query(g):
            c = codes[i]
            h = cur_g[c]
            if not g.intersects(h):
                continue
            r = g.intersection(h).area / g.area
            if r > 0.005:
                d = code_to_d[c]
                sh[d] = round(sh.get(d, 0) + r, 4)
        out[k] = sh
    res = {
        "_note": ("과거 동이 현 선거구에 걸치는 면적비. 표를 이 비율로 나누는 데 쓰지 "
                  "않는다 — 가로지르는지 판정하는 데만 쓴다. 면적비 배분은 추정이다. "
                  "동 키는 '시군구코드:동이름' — 이름만으로는 전국 223종이 충돌한다."),
        "current": cur, "previous": prev, "fixture": fixture,
        "membership": out,
        "crossing": sorted(k for k, sh in out.items()
                           if len([1 for v in sh.values() if v > MIN_SHARE]) > 1),
    }
    f.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def resolve(cur: int, prev: int, fixture: str, cur_blocks: list[dict],
            prev_blocks: list[dict],
            cur_dmap: dict[str, str]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """과거 동 → 현 선거구(단일). 가로지르는 동은 **닿는 선거구 목록과 함께** 돌려준다.

    가로지르는 동 하나 때문에 그 시군구 전체를 막지 않는다. 고양시는 흥도동만
    갑·병에 걸치는데 을·정까지 막으면 멀쩡한 비교를 버리는 것이다.
    """
    m = membership(cur, prev, fixture, cur_blocks, prev_blocks, cur_dmap)
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
