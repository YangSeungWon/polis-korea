"""13대 대선(1987-12) 전용 시군구 경계 — 1985 base + 광주직할시 구 splice.

13대는 PRES_SGG_GEO_YEAR=1985를 썼으나 1985엔 광주가 '전남 광주시' 단일(광주직할시 승격 1986
전)이라, 데이터(광주광역시 동/북/서구)와 불일치 → 회색. 1990 경계엔 광주가 구별(code 24)로 있으나
1990은 대전직할시(1989)가 분리돼 1987(대전=충남)과 어긋남. → 1985 base에서 전남 광주시(36011)만
제거하고 1990의 광주 구(동24010·서24020·북24040)를 splice. 대전 등 나머지는 1985 그대로(1987 정합).
sido_1987(외곽선)도 dissolve 생성.

재현: python scripts/build/build_sigungu_1987.py
"""
import json
from pathlib import Path
from collections import defaultdict
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
GWANGJU_GU = {"24010", "24020", "24040"}   # 동·서·북구 (광산구 24050은 1988 신설, 13대 데이터 없음 → 제외)


def main():
    base = json.loads((GEO / "sigungu_1985.json").read_text(encoding="utf-8"))
    y1990 = json.loads((GEO / "sigungu_1990.json").read_text(encoding="utf-8"))
    feats = [f for f in base["features"] if f["properties"].get("code") != "36011"]  # 전남 광주시 제거
    gj = [f for f in y1990["features"] if str(f["properties"].get("code")) in GWANGJU_GU]
    for f in gj:
        feats.append({"type": "Feature",
                      "properties": {"code": f["properties"]["code"], "name": f["properties"]["name"]},
                      "geometry": f["geometry"]})
    out = {"type": "FeatureCollection", "features": feats}
    sp = GEO / "sigungu_1987.json"
    sp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"sigungu_1987: {len(feats)} feature (광주 구 {len(gj)}개 splice) → {sp.name}")

    # sido_1987 외곽선 — 시도2자리코드 dissolve
    by = defaultdict(list)
    for f in feats:
        s2 = str(f["properties"]["code"])[:2]
        g = shape(f["geometry"])
        by[s2].append(g if g.is_valid else make_valid(g))
    sfeats = [{"type": "Feature", "properties": {"code2": s2}, "geometry": mapping(unary_union(sh))}
              for s2, sh in sorted(by.items())]
    sop = GEO / "sido_1987.json"
    sop.write_text(json.dumps({"type": "FeatureCollection", "features": sfeats}, ensure_ascii=False),
                   encoding="utf-8")
    print(f"sido_1987: 시도 {len(sfeats)}개 → {sop.name}")


if __name__ == "__main__":
    main()
