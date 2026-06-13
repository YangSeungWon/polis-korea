"""옛 총선 HGIS geo의 인접 선거구 사이 '빈 금'(틈/크랙) 제거 — 평면분할 후처리.

build_old_general_geo --hgis 산출물은 HGIS 폴리곤을 개별수집해 인접 경계 미공유 → union에 틈.
이미 단순화된 출력 파일에 clean_partition(노딩→polygonize→면을 원선거구에 귀속)을 적용하면
빠르게(회차당 <1s) 틈 0·feature 보존. make_valid로 유효성 보장. sido 외곽선도 재dissolve.

재현: python scripts/build/clean_old_general_holes.py [n ...]   (기본 1~8)
"""
import json, sys
from pathlib import Path
from collections import defaultdict
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
sys.path.insert(0, str(ROOT / "scripts/fetch"))
import build_sigungu_hgis as _bsh   # clean_partition 재사용


def clean(n):
    p = GEO / f"district_{n}_geojson.json"
    if not p.exists():
        print(f"  {n}대 없음 — skip", file=sys.stderr); return
    d = json.loads(p.read_text(encoding="utf-8"))
    feats = _bsh.clean_partition(d["features"])   # 평면분할 위상정리
    for f in feats:                                # 유효성 보장
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
            if not g.is_valid or g.is_empty:
                g = make_valid(g)
        f["geometry"] = mapping(g)
    p.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False),
                 encoding="utf-8")
    # sido 외곽선 재dissolve (정리된 fill 기준)
    by = defaultdict(list)
    for f in feats:
        g = shape(f["geometry"])
        by[f["properties"].get("SIDO")].append(g if g.is_valid else make_valid(g))
    sfeats = [{"type": "Feature", "properties": {"SIDO": s}, "geometry": mapping(unary_union(sh))}
              for s, sh in by.items() if s]
    (GEO / f"district_{n}_sido.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": sfeats}, ensure_ascii=False), encoding="utf-8")
    # 검증
    u = unary_union([shape(f["geometry"]) for f in feats])
    polys = u.geoms if u.geom_type == "MultiPolygon" else [u]
    from shapely.geometry import Polygon
    holes = sum(1 for pp in polys for r in pp.interiors if Polygon(r).area > 1e-7)
    print(f"{n}대: feature {len(feats)} | 유의미 틈 {holes}", file=sys.stderr)


if __name__ == "__main__":
    rounds = [int(x) for x in sys.argv[1:]] or range(1, 9)
    for n in rounds:
        clean(n)
