#!/usr/bin/env python3
"""GeoJSON에서 점 4개 미만의 퇴화(degenerate) 링 제거.

sido_simple.json 등 단순화된 경계엔 작은 섬이 2~3개 점으로 뭉개진 링이 남아
유효한 linearring(>=4점) 조건을 어긴다(shapely가 'A linearring requires at least
4 coordinates'로 거부). Leaflet은 관대해 렌더는 되지만, 후속 geo 처리(shapely)는
깨지고 엄밀히는 invalid GeoJSON이다.

규칙:
- 외곽(첫) 링이 4점 미만 → 그 sub-polygon 통째로 제거.
- 구멍(나머지) 링이 4점 미만 → 그 링만 제거.
- 결과적으로 polygon이 비면 제거. feature가 비면 제거.
폴리곤의 '실면적' 형상은 보존(제거되는 건 면적 0인 슬리버 섬뿐). 멱등.

사용: python scripts/build/clean_degenerate_rings.py data/geo/sido_simple.json
"""
import json
import sys
from pathlib import Path


def clean_rings(rings):
    """polygon 하나(=링 리스트)에서 퇴화 링 정리. None이면 polygon 제거."""
    if not rings:
        return None
    ext = rings[0]
    if len(ext) < 4:
        return None  # 외곽 링이 퇴화 → polygon 제거
    holes = [r for r in rings[1:] if len(r) >= 4]
    return [ext] + holes


def clean_geometry(geom):
    t = geom.get("type")
    c = geom.get("coordinates")
    if t == "Polygon":
        cleaned = clean_rings(c)
        if cleaned is None:
            return None
        geom["coordinates"] = cleaned
        return geom
    if t == "MultiPolygon":
        polys = []
        for poly in c:
            cleaned = clean_rings(poly)
            if cleaned is not None:
                polys.append(cleaned)
        if not polys:
            return None
        # 단일 polygon만 남으면 Polygon으로 강등하지 않고 MultiPolygon 유지(스키마 안정)
        geom["coordinates"] = polys
        return geom
    return geom  # 그 외 타입은 손대지 않음


def main(path: Path) -> int:
    d = json.loads(path.read_text())
    feats = d.get("features", [])
    dropped_rings = 0
    out_feats = []

    def count_rings(geom):
        c = geom.get("coordinates", [])
        if geom.get("type") == "Polygon":
            return len(c)
        if geom.get("type") == "MultiPolygon":
            return sum(len(p) for p in c)
        return 0

    for f in feats:
        g = f.get("geometry")
        if not g:
            out_feats.append(f)
            continue
        before = count_rings(g)
        cleaned = clean_geometry(dict(g))
        if cleaned is None:
            print(f"  drop empty feature: {f.get('properties')}")
            continue
        after = count_rings(cleaned)
        if after != before:
            print(f"  {f['properties'].get('name','?')}: 링 {before}→{after} (퇴화 {before-after}개 제거)")
            dropped_rings += before - after
        f["geometry"] = cleaned
        out_feats.append(f)

    d["features"] = out_feats
    path.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    print(f"\n{path.name}: 퇴화 링 {dropped_rings}개 제거, feature {len(out_feats)}개")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: clean_degenerate_rings.py <geojson path>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
