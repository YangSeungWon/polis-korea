"""선거구 경계 GeoJSON 복원 — 읍면동 경계(SGIS) union.

흐름:
  WWolf TSV (읍면동→선거구) + admdongkor 매칭표(선관위동→통계청 adm_cd)
  + SGIS 읍면동 경계 SHP(adm_cd→폴리곤, UTM-K 5179)
  → 선거구별 읍면동 union → 선거구 GeoJSON (21·22대와 동일 포맷)
     + name_to_sgg_code 맵 (history/archive 렌더러 호환)

출처: 통계청 SGIS 행정동 경계 + vuski/admdongkor 매칭표. 자유 이용·출처표시.
사용(venv): /tmp/geoenv/bin/python scripts/build/build_district_geojson.py 20
"""
from __future__ import annotations
import csv, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

import shapefile  # pyshp
from shapely.geometry import shape, mapping, MultiPolygon
from shapely.ops import unary_union, transform as shp_transform
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]

# 회차별 입력
CFG = {
    20: dict(mode="wwolf", year=2016,
             wwolf=ROOT / "data/raw/wwolf/2016general_cand_full.tsv",
             match=ROOT / "data/raw/admdongkor/match_20.csv",
             shp=ROOT / "data/raw/sgis/bnd_dong_2016/bnd_dong_00_2016_4Q.shp",
             # 선거시점(2016-02) 경계 — SGIS 2016-4Q가 재코딩한 동(부천 구폐지) fallback
             fallback=ROOT / "data/raw/admdongkor/hangjeongdong_20160201.geojson",
             results=ROOT / "data/results/national_assembly_20.json"),
    13: dict(mode="nec_emd", year=1990,
             emd=ROOT / "data/raw/nec/district_emd_13.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_1990/bnd_dong_00_1990_4Q.shp",
             results=ROOT / "data/results/national_assembly_13.json"),
    14: dict(mode="nec_emd", year=1990,
             emd=ROOT / "data/raw/nec/district_emd_14.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_1990/bnd_dong_00_1990_4Q.shp",
             results=ROOT / "data/results/national_assembly_14.json"),
    15: dict(mode="nec_emd", year=1995,
             emd=ROOT / "data/raw/nec/district_emd_15.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_1995/bnd_dong_00_1995_4Q.shp",
             results=ROOT / "data/results/national_assembly_15.json"),
    16: dict(mode="nec_emd", year=2000,
             emd=ROOT / "data/raw/nec/district_emd_16.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_2000/bnd_dong_00_2000.shp",
             results=ROOT / "data/results/national_assembly_16.json"),
    17: dict(mode="nec_emd", year=2004,
             emd=ROOT / "data/raw/nec/district_emd_17.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_2004/bnd_dong_00_2004.shp",
             results=ROOT / "data/results/national_assembly_17.json"),
    19: dict(mode="nec_emd", year=2012,
             emd=ROOT / "data/raw/nec/district_emd_19.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_2012/bnd_dong_00_2012.shp",
             results=ROOT / "data/results/national_assembly_19.json"),
    18: dict(mode="nec_emd", year=2008,
             emd=ROOT / "data/raw/nec/district_emd_18.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_2008/bnd_dong_00_2008.shp",
             results=ROOT / "data/results/national_assembly_18.json"),
}

CANON = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도"}
# NEC 행정표준 시도코드 → SGIS 통계청 시도코드 (앞 2자리). nec_emd 조인용.
NEC2SGIS = {"11": "11", "26": "21", "27": "22", "28": "23", "29": "24", "30": "25",
            "31": "26", "51": "29", "41": "31", "42": "32", "43": "33", "44": "34",
            "45": "35", "46": "36", "47": "37", "48": "38", "49": "39"}
SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
}


def _ndong(s):
    """동명 정규화 — 제N동('창신제1동'→'창신1동'), 구분자(·ㆍ/→,), 구시군 접두('연기군 부용면'→'부용면')."""
    s = re.sub(r"^[가-힣]+[시군구] ", "", s)  # NEC '연기군 부용면' 접두 제거
    s = re.sub(r"제(\d)", r"\1", s)
    s = re.sub(r"[·ㆍ.,/]", "", s)            # 구분자 제거: 용담·명암·산성동 ↔ 용담명암산성동, 두류1·2동↔두류1,2동
    s = s.replace("릉", "능")                 # 정릉↔정능 등 능/릉(陵) 표기 변종
    return s


# NEC 투표구 동명 → SGIS 행정동명 (개명·분동·표기변형). [목록]=1:다.
# 세종: 2012-04(연기군)→2012-07(세종) 면 개명. 인천 청라동→분동. 경남 벌용동→SGIS 벌룡동.
DONG_ALIAS = {
    ("세종", "남면"): ["연기면"], ("세종", "동면"): ["연동면"], ("세종", "서면"): ["연서면"],
    ("세종", "부용면"): ["부강면"], ("세종", "장기면"): ["장군면"],
    ("인천", "청라동"): ["청라1동", "청라2동"],
    ("경남", "벌용동"): ["벌룡동"],
}


def round_coords(geom, ndigits):
    """GeoJSON geometry dict 좌표를 ndigits로 반올림 (용량 축소)."""
    def rnd(x):
        if isinstance(x, (list, tuple)):
            return [rnd(v) for v in x]
        return round(x, ndigits)
    geom["coordinates"] = rnd(geom["coordinates"])
    return geom


def main(n: int):
    cfg = CFG[n]
    transformer = Transformer.from_crs(5179, 4326, always_xy=True)

    # 1) 결과의 선거구 (권위): (시도약칭, name) → race. 선거구명은 전국 고유 아님
    #    (부산 남구갑 vs 울산 남구갑) → 시도로 disambiguate.
    results = json.loads(cfg["results"].read_text(encoding="utf-8"))
    districts = results.get("district") or []
    by_key = {}
    for r in districts:
        by_key[(SIDO_SHORT.get(r["sido"], r["sido"]), r["name"])] = r
    print(f"결과 선거구: {len(by_key)}개", file=sys.stderr)

    # 2) SGIS SHP: adm_cd → geom (5179). 필드명·인코딩 연도별 자동감지
    try:
        sf = shapefile.Reader(str(cfg["shp"]), encoding="cp949")
        sf.record(0)  # 인코딩 확인
    except UnicodeDecodeError:
        sf = shapefile.Reader(str(cfg["shp"]), encoding="utf-8")
    fields = [f[0] for f in sf.fields[1:]]
    CD = "ADM_CD" if "ADM_CD" in fields else "adm_dr_cd"
    NM = "ADM_NM" if "ADM_NM" in fields else "adm_dr_nm"
    geom_by_cd = {}
    sido_dong_idx = defaultdict(list)  # (SGIS시도2, 동명변형) → [adm_cd] (nec_emd 조인용)
    sido_names = defaultdict(list)     # SGIS시도2 → [(adm_cd, 정규화동명)] (퍼지 fallback)
    for sr in sf.iterShapeRecords():
        cd = str(sr.record[CD]).strip()
        g = shape(sr.shape.__geo_interface__)
        if not g.is_valid:
            g = g.buffer(0)
        geom_by_cd[cd] = g
        nm = str(sr.record[NM]).strip()
        sido_dong_idx[(cd[:2], nm)].append(cd)
        if _ndong(nm) != nm:
            sido_dong_idx[(cd[:2], _ndong(nm))].append(cd)
        sido_names[cd[:2]].append((cd, _ndong(nm)))
    print(f"SGIS 동: {len(geom_by_cd)}개 (필드 {CD}/{NM})", file=sys.stderr)

    def reproj(geom):
        return shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)

    # 3) 선거구 → {adm_cd} (모드별)
    district_cds = defaultdict(set)
    miss_dong = total_dong = 0
    if cfg["mode"] == "wwolf":
        dong_to_cd = defaultdict(list)
        with cfg["match"].open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                cd = (row.get("adm_cd") or "").strip()
                sm = (row.get("선거관리위원회 동이름") or "").strip()
                if cd and sm:
                    dong_to_cd[sm].append(cd)
        if cfg.get("fallback") and cfg["fallback"].exists():  # 재코딩 동(부천 구폐지) 보강
            to5179 = Transformer.from_crs(4326, 5179, always_xy=True)
            for ft in json.loads(cfg["fallback"].read_text(encoding="utf-8")).get("features", []):
                cd = str(ft["properties"].get("adm_cd", "")).strip()
                if not cd or cd in geom_by_cd:
                    continue
                g = shape(ft["geometry"])
                geom_by_cd[cd] = shp_transform(lambda x, y, z=None: to5179.transform(x, y),
                                               g if g.is_valid else g.buffer(0))
        with cfg["wwolf"].open(encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                sido = (row.get("광역") or "").strip(); sgg = (row.get("시군구") or "").strip()
                emd = (row.get("읍면동") or "").strip(); sgn = (row.get("선거구") or "").strip()
                if not sgn or not emd or emd in {"합계", "계"} or "투표" in emd:
                    continue
                total_dong += 1
                cds = dong_to_cd.get(f"{sido} {sgg} {emd}")
                if not cds:
                    miss_dong += 1; continue
                district_cds[(SIDO_SHORT.get(sido, sido), sgn)].update(cds)
    else:  # nec_emd: NEC 투표구별. 하드코딩 conv 대신 데이터로 NEC구→SGIS구 학습 + 기하 소거.
        recs = json.loads(cfg["emd"].read_text(encoding="utf-8"))
        # Pass 1: 고유(단일 후보) 동매칭으로 NEC sgg_code → SGIS 구코드 학습 (구 번호 불일치 대응)
        gu_vote = defaultdict(Counter)
        for r in recs:
            s2 = NEC2SGIS.get(str(r["sgg_code"])[:2], str(r["sgg_code"])[:2])
            for dong in r["dongs"]:
                d = re.sub(r"^[가-힣]+[시군구] ", "", dong)
                cands = sido_dong_idx.get((s2, d)) or sido_dong_idx.get((s2, _ndong(d))) or []
                if len(cands) == 1:
                    gu_vote[str(r["sgg_code"])][cands[0][:4]] += 1
        gu_map = {sgg: cnt.most_common(1)[0][0] for sgg, cnt in gu_vote.items()}

        # Pass 2: 학습된 구로 매칭(충돌 tiebreak·퍼지 제한). 미매칭 추적.
        unmatched = defaultdict(list)  # key → [(SGIS구, dong)]
        for r in recs:
            sido_short = SIDO_SHORT.get(r["sido"], r["sido"])
            key = (sido_short, r["district"])
            nec_sgg = str(r["sgg_code"])
            s2 = NEC2SGIS.get(nec_sgg[:2], nec_sgg[:2])
            gu = gu_map.get(nec_sgg)
            for dong in r["dongs"]:
                total_dong += 1
                dong = re.sub(r"^[가-힣]+[시군구] ", "", dong)  # '연기군 부용면' 접두 제거
                alias = DONG_ALIAS.get((sido_short, dong))
                if alias:  # 개명·분동 — 지정 SGIS 동(들)
                    got = [c for t in alias for c in sido_dong_idx.get((s2, t), [])]
                else:
                    cands = sido_dong_idx.get((s2, dong)) or sido_dong_idx.get((s2, _ndong(dong))) or []
                    if len(cands) > 1 and gu:  # 동명 충돌 → 학습된 구로 tiebreak (conv 가정 대신)
                        cands = [c for c in cands if c[:4] == gu] or cands
                    got = cands[:1]
                if not got and gu:  # 정방향 퍼지(학습 구 제한): 동통합 청운동→청운효자동
                    b = re.sub(r"(제?\d+)?가?(동|읍|면|리)$", "", _ndong(dong)) or _ndong(dong)
                    if len(b) >= 2:
                        got = [c for c, nm in sido_names.get(s2, []) if nm.startswith(b) and c[:4] == gu][:1]
                if not got and gu:  # 역방향 퍼지(학습 구 제한): 용담명암산성동 ⊇ 용담동+…
                    nn = _ndong(dong)
                    got = [c for c, nm in sido_names.get(s2, [])
                           if c[:4] == gu and len(re.sub(r"(제?\d+)?가?[동읍면리]$", "", nm)) >= 2
                           and re.sub(r"(제?\d+)?가?[동읍면리]$", "", nm) in nn]
                if not got:
                    miss_dong += 1
                    if gu:
                        unmatched[key].append((gu, dong))
                    continue
                district_cds[key].update(got)

        # Pass 3: 기하 소거 — 고아 SGIS 동(어느 선거구에도 미배정)을, 그 구에서 미매칭 선거구가
        # 하나뿐일 때 그 선거구로 강제(이름 추측 0·소거로 정답). count 가드로 과배정 방지.
        assigned = set().union(*district_cds.values()) if district_cds else set()
        all_in_gu = defaultdict(list)
        for c in geom_by_cd:
            all_in_gu[c[:4]].append(c)
        gu_unmatched_sgg = defaultdict(lambda: defaultdict(int))  # 구 → {선거구: 미매칭수}
        for k, lst in unmatched.items():
            for gu, d in lst:
                gu_unmatched_sgg[gu][k] += 1
        filled = 0
        for gu, sgg_cnt in gu_unmatched_sgg.items():
            if len(sgg_cnt) != 1:
                continue  # 두 선거구가 미매칭 → 애매, 건너뜀
            k, ucnt = next(iter(sgg_cnt.items()))
            orphans = [c for c in all_in_gu.get(gu, []) if c not in assigned]
            if orphans and len(orphans) <= ucnt:  # 과배정 방지(김천류 conv오염 차단)
                district_cds[k].update(orphans)
                filled += len(orphans)
        if filled:
            print(f"소거 확정 고아 동: {filled}개", file=sys.stderr)

    # 4) 선거구별 union
    features = []
    name_to_code = {}
    incomplete = []
    for i, ((skey, name), race) in enumerate(sorted(by_key.items())):
        cds = district_cds.get((skey, name))
        if not cds:
            incomplete.append((f"{skey} {name}", "매핑 없음"))
            continue
        geoms = [geom_by_cd[c] for c in cds if c in geom_by_cd]
        if not geoms:
            incomplete.append((name, "geom 0"))
            continue
        u = unary_union(geoms)  # 5179(미터) 상태 — 작은 섬 제거(면적 m²)
        if u.geom_type == "MultiPolygon":
            parts = [p for p in u.geoms if p.area > 200000]  # 0.2km² 미만 도서 제거
            if parts:
                u = parts[0] if len(parts) == 1 else MultiPolygon(parts)
        # preserve_topology=False: 슬리버 union에서도 점 대폭 축소(266배). buffer(0)로 유효성 복구.
        u = reproj(u).simplify(0.0035, preserve_topology=False).buffer(0)
        code = f"D{n}{i:04d}"
        sido_full = race["sido"]
        sido_short = SIDO_SHORT.get(sido_full, sido_full)
        features.append({
            "type": "Feature",
            "properties": {
                "SGG_Code": code,
                "SIDO_SGG": f"{sido_short} {name}",
                "SIDO": sido_short,
                "SGG": name,
            },
            "geometry": round_coords(mapping(u), 4),  # ~1m, 용량 축소
        })
        name_to_code[f"{CANON.get(sido_full, sido_full)}|{name}"] = code

    fc = {"type": "FeatureCollection", "features": features}
    out_geo = ROOT / f"data/geo/district_{n}_geojson.json"
    out_map = ROOT / f"data/geo/district_{n}_geojson_map.json"
    out_geo.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    out_map.write_text(json.dumps({
        "_meta": {
            "description": f"{n}대 선거구 경계 — SGIS {cfg['year']} 읍면동 union. key '{{canonSido}}|{{name}}' → SGG_Code.",
            "source": "통계청 SGIS 행정동 경계 + vuski/admdongkor 매칭표 + WWolf 읍면동→선거구",
            "matched": len(features), "total": len(by_key),
        },
        "name_to_sgg_code": name_to_code,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n선거구 폴리곤: {len(features)}/{len(by_key)}", file=sys.stderr)
    print(f"동 매칭 실패: {miss_dong}/{total_dong}", file=sys.stderr)
    if incomplete:
        print(f"미완성 {len(incomplete)}: {incomplete[:10]}", file=sys.stderr)
    print(f"→ {out_geo.name} ({out_geo.stat().st_size//1024}KB), {out_map.name}", file=sys.stderr)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
