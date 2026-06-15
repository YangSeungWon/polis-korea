#!/usr/bin/env python3
"""HGIS 옛 대선 시군구 경계 위생 정리 — 시/군 도넛 중첩 + 면적0 찌꺼기.

옛 도농분리 시절 군(郡) 폴리곤이 그 안의 시(市)를 도려내지 않아 시가 군에
100% 파묻혀 영역이 겹친다(예: 금릉군⊃김천시, 청원군⊃청주시). 화면엔 시가
위에 그려져 멀쩡하지만 토폴로지상 중첩이라, 군에서 시를 difference로 도려내
군을 도넛(ring)으로 만든다. 둘 다 실제 개표 데이터가 있어 카브(둘 다 유지)는
안전하다.

추가로 boolean/디지타이즈 잔여인 면적 < 1e-8 deg²(~100 m²) 미세 조각을 제거한다.
실제 섬(>100 m²)·본체는 보존. 멱등.

손대지 않는 것(별도 판단 필요 — 둘 다 race 보유, 화면엔 draw-order로 정상):
  - ratio≥0.7 개명·동지역 중복(경주군/월성군, 양산시/양산군, 천안군/천원군)
  - 구/구 동일지오 오류(대구시북구/서구)
서울↔경기 cross-sido(광주군/성동구)는 clean_hgis_seoul_overlap.py가 처리.

재현: python scripts/build/clean_hgis_overlaps.py
"""
import glob
import json
import os
from pathlib import Path

from shapely.geometry import shape, mapping, MultiPolygon
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data" / "geo"
JUNK = 1e-8           # 면적 < 이 값(~100 m²)인 part/hole → 제거
CONTAIN = 0.5         # inter > min_area*이 비율 → 포함 관계로 판정
DOUGHNUT_MAX = 0.6    # 작은쪽/큰쪽 면적비 < 이 값 + 시⊂군 → 도넛 카브


def _parea(ring):
    return shape({"type": "Polygon", "coordinates": [ring]}).area


def drop_junk(geom):
    """면적0 보조 조각·퇴화 hole 제거. feature는 절대 비우지 않음 — 최대 part는 항상 보존.
    반환 (geom, degenerate?) — 최대 part마저 <JUNK면 degenerate=True(데이터 결함, 보고용)."""
    def clean_holes(rings):
        ext = rings[0]
        holes = [r for r in rings[1:] if len(r) >= 4 and _parea(r) >= JUNK]
        return [ext] + holes
    t = geom.geom_type
    if t == "Polygon":
        m = mapping(geom)
        deg = _parea(m["coordinates"][0]) < JUNK
        return shape({"type": "Polygon", "coordinates": clean_holes(m["coordinates"])}), deg
    if t == "MultiPolygon":
        polys = sorted(mapping(geom)["coordinates"],
                       key=lambda p: _parea(p[0]), reverse=True)
        keep = [polys[0]] + [p for p in polys[1:] if _parea(p[0]) >= JUNK]  # 최대 part 항상 유지
        keep = [clean_holes(p) for p in keep]
        deg = _parea(polys[0][0]) < JUNK
        if len(keep) == 1:
            return shape({"type": "Polygon", "coordinates": keep[0]}), deg
        return shape({"type": "MultiPolygon", "coordinates": keep}), deg
    return geom, False


def round_geom(geom, nd=9):
    def r(x):
        if isinstance(x, (list, tuple)):
            if x and isinstance(x[0], (int, float)):
                return [round(float(v), nd) for v in x]
            return [r(v) for v in x]
        return x
    m = mapping(geom)
    m["coordinates"] = r(m["coordinates"])
    return m


def write_fc(path, d):
    lines = ['{"type":"FeatureCollection", "features": [']
    feats = d["features"]
    for i, f in enumerate(feats):
        sep = "," if i < len(feats) - 1 else ""
        lines.append(json.dumps(f, ensure_ascii=False, separators=(",", ":")) + sep)
    lines.append("]}")
    path.write_text("\n".join(lines) + "\n")


def clean_file(path):
    d = json.loads(path.read_text())
    feats = d["features"]
    geoms = []
    for f in feats:
        try:
            geoms.append(shape(f["geometry"]).buffer(0))
        except Exception:
            geoms.append(None)
    changed = set()

    # --- 1) 시/군 도넛 카브 ---
    valid = [(i, g) for i, g in enumerate(geoms) if g is not None and not g.is_empty]
    tree = STRtree([g for _, g in valid])
    idxmap = [i for i, _ in valid]
    seen = set()
    for ii, gi in valid:
        for loc in tree.query(gi):
            j = idxmap[loc]
            if j <= ii or (ii, j) in seen:
                continue
            seen.add((ii, j))
            gj = geoms[j]
            inter = gi.intersection(gj).area
            if inter < 1e-6 or inter < CONTAIN * min(gi.area, gj.area):
                continue
            si, bi = (ii, j) if gi.area <= gj.area else (j, ii)
            sn = feats[si]["properties"].get("name", "")
            bn = feats[bi]["properties"].get("name", "")
            ratio = geoms[si].area / geoms[bi].area
            sido = feats[si]["properties"].get("sido")
            if ratio < DOUGHNUT_MAX and sn.endswith("시") and bn.endswith("군"):
                geoms[bi] = geoms[bi].difference(geoms[si]).buffer(0)
                changed.add(bi)
                print(f"  carve {sido} {bn} ⊖ {sn} (ratio {ratio:.2f}) → {bn} 도넛")
            else:
                print(f"  skip  {sido} {bn} ⊃ {sn} (ratio {ratio:.2f}) — 별도판단(개명중복/구·구)")

    # --- 2) 면적0 찌꺼기 제거 (feature는 비우지 않음) ---
    junk_n = 0
    for k, f in enumerate(feats):
        g = geoms[k]
        if g is None:
            continue
        before = g
        cleaned, deg = drop_junk(g)
        if deg:
            print(f"  WARN 퇴화 지오메트리(최대 part<100m²): {f['properties'].get('sido')} {f['properties'].get('name')} — 보존(원지오 결함, 수동확인)")
        if k in changed or cleaned.geom_type != before.geom_type or abs(cleaned.area - before.area) > 1e-12:
            f["geometry"] = round_geom(cleaned)
            if k not in changed:
                junk_n += 1
    return d, len(changed), junk_n


def main():
    total_c = total_j = 0
    for path in sorted(GEO.glob("sigungu_hgis_*.json")):
        d, c, j = clean_file(path)
        if c or j:
            write_fc(path, d)
            print(f"{os.path.basename(path)}: 카브 {c}, 찌꺼기 정리 {j}\n")
        total_c += c
        total_j += j
    print(f"총 카브 {total_c}, 찌꺼기 정리 {total_j}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
