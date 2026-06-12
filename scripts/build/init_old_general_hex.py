"""옛 총선(1~8대) 선거구 hex — 정확 경계 없이 시군/시도 centroid로 build_zone_hex T자 배치.

선거구 이름의 시군(예 '제1선거구(중구)')으로 centroid 추정. 이름에 시군 없으면(3·4·5대
'제N선거구'·6·7대 대도시 '제N지역구') 시도 중심 사용 → build_zone_hex가 선거구 번호순 패킹.
경계가 아니라 근사 카토그램이라 지역 정당 패턴(자유당 vs 민주당 등)은 그대로 드러남.

사용: python scripts/build/init_old_general_hex.py [1 2 3 4 5 6 7 8]
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"; RES = ROOT / "data/results"

def centroid(geom):
    xs, ys = [], []
    def walk(c):
        if isinstance(c[0], (int, float)): xs.append(c[0]); ys.append(c[1])
        else:
            for x in c: walk(x)
    walk(geom["coordinates"]); return (sum(xs)/len(xs), sum(ys)/len(ys))

def load_cen(path, key="name"):
    d = json.loads((GEO/path).read_text(encoding="utf-8"))
    feats = d.get("features", d) if isinstance(d, dict) else d
    return {f["properties"][key]: centroid(f["geometry"]) for f in feats}

SIDO_CEN = load_cen("sido_simple.json")
SGG_CEN = load_cen("sigungu_simple.json")
SIDO_ALIAS = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도",
              "제주도": "제주특별자치도", "강원도": "강원도", "전라북도": "전라북도"}
def sido_cen(sido):
    return SIDO_CEN.get(sido) or SIDO_CEN.get(SIDO_ALIAS.get(sido, ""))

def sggs_of(name):
    m = re.search(r"[(（](.+?)[)）]", name)
    if not m: return []
    out = []
    for s in re.split(r"[·∙•・,.]", m.group(1)):
        s = s.strip()
        s = re.sub(r"\s*[갑을병정무]\s*구?$", "", s)  # 갑/을 개표구
        if s: out.append(s)
    return out

def sgg_centroid(nm):
    if nm in SGG_CEN: return SGG_CEN[nm]
    base = nm[:2]
    for k, v in SGG_CEN.items():
        if k[:2] == base: return v
    return None

# 옛→현행 시도명 (geojson SIDO는 현행명. lookup·정식화 공용)
SIDO_CANON = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도", "제주도": "제주특별자치도"}


def load_geo_cen(n):
    """district_{n}_geojson.json 선거구 폴리곤 centroid (SGIS 1975 경계).
    {(SIDO, SGG): (lon,lat)} — 동명이의(고성군 강원/경남 등) 분리. SGG-only key도 보존(fallback)."""
    p = GEO / f"district_{n}_geojson.json"
    if not p.exists():
        return {}
    out = {}
    for f in json.loads(p.read_text(encoding="utf-8")).get("features", []):
        pr = f["properties"]
        c = centroid(f["geometry"])
        out[(pr.get("SIDO", ""), pr["SGG"])] = c
        out.setdefault(pr["SGG"], c)   # 동명이의 없을 때용 name-only fallback
    return out


def build(n):
    aid = {1:"1st-general-1948",2:"2nd-general-1950",3:"3rd-general-1954",4:"4th-general-1958",
           5:"5th-general-1960",6:"6th-general-1963",7:"7th-general-1967",8:"8th-general-1971"}[n]
    races = [r for r in json.loads((RES/f"national_assembly_{n}.json").read_text(encoding="utf-8"))["district"]]
    geo_cen = load_geo_cen(n)  # 실제 선거구 폴리곤 centroid 우선 (geo와 hex 위치 일치)
    cells, fallback = [], 0
    sido_idx = {}  # 시도 내 fallback 선거구 순번 (격자 분산용)
    for r in races:
        # 3·4·5대는 별표 통합으로 sigungu_area 보유 → 우선 사용(이름엔 괄호 없음)
        sido = r["sido"]; sggs = r.get("sigungu_area") or sggs_of(r["name"])
        # 1순위: 실제 선거구 경계 중심. (sido,name)으로 동명이의 분리(고성군 강원/경남) 후 name-only fallback.
        cen = geo_cen.get((SIDO_CANON.get(sido, sido), r["name"])) or geo_cen.get(r["name"])
        if cen:
            pass
        elif (cens := [c for c in (sgg_centroid(s) for s in sggs) if c]):
            cen = (sum(c[0] for c in cens)/len(cens), sum(c[1] for c in cens)/len(cens))
        else:
            base = sido_cen(sido)
            if not base: continue
            i = sido_idx.get(sido, 0); sido_idx[sido] = i + 1
            # 시도 중심 주변 격자로 분산 (build_zone_hex가 동일 centroid면 KeyError) — 번호순
            cen = (base[0] + (i % 6) * 0.04 - 0.1, base[1] - (i // 6) * 0.04 + 0.1)
            fallback += 1
        if not cen: continue
        # 동일 centroid 방지 미세 jitter (안정 정렬 보존)
        cen = (cen[0] + (len(cells) % 13) * 0.0008, cen[1] + (len(cells) % 7) * 0.0008)
        # 정식 시도명으로 통일(build_zone_hex 존 분류·기존 hex 규약 일치). 렌더는 canonSido로 매칭.
        sido = {"전라북도": "전북특별자치도", "강원도": "강원특별자치도",
                "제주도": "제주특별자치도"}.get(sido, sido)
        cells.append({"sido": sido, "name": r["name"], "sigungus": sggs,
                      "_cen": [round(cen[0],5), round(cen[1],5)], "c":0, "r":0})
    (GEO/f"district_hex_{n}.json").write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
    print(f"{n}대: {len(cells)}선거구 (시도중심 fallback {fallback})")

if __name__ == "__main__":
    for a in (sys.argv[1:] or [1,2,3,4,5,6,7,8]): build(int(a))
