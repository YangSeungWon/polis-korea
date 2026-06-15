#!/usr/bin/env python3
"""HGIS 옛 대선 시군구 경계의 서울↔경기 중첩 정리.

1963-01-01 서울 대확장으로 경기도 광주군·시흥군·김포군 등 일부가 서울에 편입됐는데,
HGIS의 해당 군(郡) 폴리곤이 편입 전(前) 범위 그대로라 그 위에 그려지는 서울 구(區)와
영역이 겹친다(예: 5~7대 대선 지도에서 성동구가 광주군 폴리곤에 100% 파묻힘).

선거일(1963-10-15 등) 시점엔 그 땅이 서울이므로 서울 구가 맞다. 따라서 서울이 아닌
feature에서 '서울 union과 유의미하게 겹치는' 부분을 빼(difference) 중첩을 없앤다.
경계만 맞닿은 슬리버(면적 거의 0)는 건드리지 않도록 임계값을 둔다. 멱등(idempotent).

직접 편집이 아닌 재빌드 안전망 — build_sigungu_hgis.py 산출물에 사후 적용.
"""
import json
import sys
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data" / "geo"
# 유의미 중첩 임계 — feature 면적의 0.5% 초과만 클립(좌표 노이즈성 슬리버 보호)
MIN_FRAC = 0.005


def round_geom(geom, nd=9):
    """좌표를 소수 nd자리로 반올림한 mapping 반환 — 원본 정밀도와 맞춤."""
    def r(x):
        if isinstance(x, (list, tuple)):
            if x and isinstance(x[0], (int, float)):
                return [round(float(v), nd) for v in x]
            return [r(v) for v in x]
        return x
    m = mapping(geom)
    m["coordinates"] = r(m["coordinates"])
    return m


def clean_file(path: Path) -> int:
    d = json.loads(path.read_text())
    feats = d["features"]
    geoms = []
    for f in feats:
        try:
            geoms.append(shape(f["geometry"]).buffer(0))
        except Exception:
            geoms.append(None)
    seoul_idx = [i for i, f in enumerate(feats) if f["properties"].get("sido") == "서울특별시"]
    if not seoul_idx:
        return 0
    seoul_union = unary_union([geoms[i] for i in seoul_idx if geoms[i] is not None])

    changed = 0
    for i, f in enumerate(feats):
        if f["properties"].get("sido") == "서울특별시" or geoms[i] is None:
            continue
        g = geoms[i]
        inter = g.intersection(seoul_union)
        if inter.is_empty or inter.area <= MIN_FRAC * g.area:
            continue
        new = g.difference(seoul_union).buffer(0)
        if new.is_empty:
            continue
        f["geometry"] = round_geom(new)
        p = f["properties"]
        print(f"  clip {p.get('sido')} {p.get('name')}({p.get('code')}): "
              f"-{100*inter.area/g.area:.0f}% (서울 편입분 제거)")
        changed += 1

    if changed:
        write_fc(path, d)
    return changed


def write_fc(path: Path, d: dict):
    """기존 포맷 보존 — feature 한 줄씩(line-delimited), compact separators."""
    lines = ['{"type":"FeatureCollection", "features": [']
    feats = d["features"]
    for i, f in enumerate(feats):
        sep = "," if i < len(feats) - 1 else ""
        lines.append(json.dumps(f, ensure_ascii=False, separators=(",", ":")) + sep)
    lines.append("]}")
    path.write_text("\n".join(lines) + "\n")


def main():
    files = sorted(GEO.glob("sigungu_hgis_*.json"))
    total = 0
    for fp in files:
        n = clean_file(fp)
        if n:
            print(f"{fp.name}: {n} feature(s) clipped")
        total += n
    print(f"\n총 {total}개 feature 정리" + ("" if total else " (변경 없음)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
