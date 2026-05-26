"""hex 격자 공용 헬퍼 — offset 좌표·이웃·폴리곤 centroid.

build_sigungu_hex / build_district_hex_v2 / build_district_hex_22 / eval_sigungu_hex
/ fill_holes 가 공유 (이전엔 각 파일에 복붙).
pointy-top, odd-r offset (홀수 row 오른쪽 +0.5).
"""
from __future__ import annotations
import math


def offset_neighbors(c: int, r: int) -> list[tuple[int, int]]:
    """odd-r offset pointy-top hex 이웃 6칸."""
    if r % 2 == 0:
        deltas = [(-1, -1), (0, -1), (-1, 0), (1, 0), (-1, 1), (0, 1)]
    else:
        deltas = [(0, -1), (1, -1), (-1, 0), (1, 0), (0, 1), (1, 1)]
    return [(c + dc, r + dr) for dc, dr in deltas]


def offset_to_pixel(c: int, r: int) -> tuple[float, float]:
    """offset (col,row) → pixel-like (x,y). 북이 작은 y."""
    return c + (0.5 if r % 2 else 0.0), r * (math.sqrt(3) / 2)


def polygon_centroid(geometry: dict) -> tuple[float, float]:
    """GeoJSON Polygon/MultiPolygon → 가장 큰 외곽링 꼭짓점 평균 (lon, lat)."""
    coords = geometry["coordinates"]
    if geometry["type"] == "MultiPolygon":
        ring = max(coords, key=lambda poly: len(poly[0]))[0]
    elif geometry["type"] == "Polygon":
        ring = coords[0]
    else:
        raise ValueError(geometry["type"])
    n = len(ring)
    return sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n
