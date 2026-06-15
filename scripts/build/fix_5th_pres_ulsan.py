#!/usr/bin/env python3
"""5대 대선(1963) 경남 '양산시' → '울산시' 정정 (결과 + 지오).

VCCP09 시군구 수집분에서 5대만 울산시(1962 승격)가 '양산시'로 잘못 라벨됨.
근거: 6·7대는 같은 소스에서 양산군 + 울산시 + 울주군으로 정상인데 5대만
양산군 + 양산시 + 울주군 (울산시 누락). 양산시는 1996 승격이라 1963 비존재.
유권자수도 양산군 ~2.7만(5·6·7대 일관) / 문제의 '양산시' 4.15만 = 울산시 규모.

정정:
- data/results/5th-pres-1963.json: sigungu '양산시' → '울산시' (득표는 울산시 실제값).
- data/geo/sigungu_hgis_5.json: feature '양산시'(양산군과 동일 area로 중첩) → '울산시',
  지오를 hgis_6 울산시 실제경계로 교체(울주군 ring 안 빈자리에 들어맞아 carve 불필요).
멱등. 재-fetch 시 동일 정정 필요(소스 라벨 오류).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "data" / "results" / "5th-pres-1963.json"
G5 = ROOT / "data" / "geo" / "sigungu_hgis_5.json"
G6 = ROOT / "data" / "geo" / "sigungu_hgis_6.json"


def fix_results():
    d = json.loads(RES.read_text())
    n = 0
    for r in d.get("races", []):
        if r.get("sido") == "경상남도" and r.get("sigungu") == "양산시":
            r["sigungu"] = "울산시"
            n += 1
    if n:
        RES.write_text(json.dumps(d, ensure_ascii=False))
    print(f"results: 양산시→울산시 {n}건")


def fix_geo():
    g6 = json.loads(G6.read_text())
    us6 = next((f["geometry"] for f in g6["features"] if f["properties"].get("name") == "울산시"), None)
    if us6 is None:
        print("geo: hgis_6 울산시 없음 — 중단"); return
    d = json.loads(G5.read_text())
    n = 0
    for f in d["features"]:
        if f["properties"].get("name") == "양산시" and f["properties"].get("sido") == "경상남도":
            f["properties"]["name"] = "울산시"
            f["geometry"] = us6           # hgis_6 울산시 실제경계
            n += 1
    if n:
        lines = ['{"type":"FeatureCollection", "features": [']
        fs = d["features"]
        for i, f in enumerate(fs):
            lines.append(json.dumps(f, ensure_ascii=False, separators=(",", ":")) + ("," if i < len(fs) - 1 else ""))
        lines.append("]}")
        G5.write_text("\n".join(lines) + "\n")
    print(f"geo hgis_5: 양산시→울산시 {n}건 (지오 ← hgis_6 울산시)")


if __name__ == "__main__":
    fix_results()
    fix_geo()
