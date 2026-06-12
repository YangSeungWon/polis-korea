"""회차별 시도 외곽선 — district_{n}_geojson을 SIDO로 dissolve → district_{n}_sido.json.

현대 sido_simple은 광역시(대구·인천1981·광주1986·대전1989·울산1997·세종2012)를 전부 분리해
옛 회차에 굵은 테두리가 시대착오. 각 회차 선거구의 SIDO(데이터는 승격시점 정합)를 dissolve하면
그 회차 당시 시도 경계(광역시도 당시 기준)가 나온다. 1~8대는 build_old_general_geo가 이미 생성.

재현: python scripts/build/build_sido_outlines.py [9 .. 22]
"""
import json, subprocess, sys
from pathlib import Path
from collections import defaultdict
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"


def simplify(path):
    ms = ROOT / "node_modules/.bin/mapshaper"
    if not ms.exists():
        return
    # 원본 선거구 geojson이 이미 단순화돼 있어 — dissolve 외곽선을 또 단순화하면 fill보다 거칠어져
    # 시도선이 선거구를 안 따라감(듬성듬성). snap+clean으로 위상만 정리하고 단순화는 생략.
    try:
        subprocess.run([str(ms), str(path), "snap", "-clean", "-o", str(path), "force"],
                       check=True, capture_output=True, timeout=300)
    except Exception as e:
        print(f"  ⚠ mapshaper 실패({path.name}): {e}", file=sys.stderr)


def build(n):
    p = GEO / f"district_{n}_geojson.json"
    if not p.exists():
        print(f"  {n}대 geojson 없음 — skip", file=sys.stderr)
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    by_sido = defaultdict(list)
    for f in d.get("features", []):
        ss = f["properties"].get("SIDO_SGG") or ""
        sido = f["properties"].get("SIDO") or (ss.split()[0] if ss else None)
        if sido and f.get("geometry"):
            g = shape(f["geometry"])
            by_sido[sido].append(g if g.is_valid else make_valid(g))
    if not by_sido:  # SIDO 속성 없는 회차(21·22대 등) — 현대 외곽선이 시대 정합이라 skip
        print(f"  {n}대: SIDO 속성 없음 — skip(현대 외곽선 사용)", file=sys.stderr)
        return
    feats = [{"type": "Feature", "properties": {"SIDO": s},
              "geometry": mapping(unary_union(sh))} for s, sh in by_sido.items()]
    out = GEO / f"district_{n}_sido.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                              ensure_ascii=False), encoding="utf-8")
    simplify(out)
    print(f"{n}대: 시도 {len(feats)} → {out.name}", file=sys.stderr)


if __name__ == "__main__":
    rounds = [int(x) for x in sys.argv[1:]] or list(range(9, 23))
    for n in rounds:
        try:
            build(n)
        except Exception as e:
            print(f"  ⚠ {n}대 실패: {type(e).__name__} {e}", file=sys.stderr)
