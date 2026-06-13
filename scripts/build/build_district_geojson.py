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
import csv, json, os, re, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

import shapefile  # pyshp
from shapely.geometry import shape, mapping, MultiPolygon
from shapely.ops import unary_union, transform as shp_transform
from pyproj import Transformer

# 단순화: build는 raw union을 내보내고 mapshaper(node_modules/.bin/mapshaper)가 위상 보존
# -simplify 2% -clean으로 후처리 → 인접 선거구 틈 0 + 용량 ~400KB. 빌드 끝에서 자동 호출.

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
    8: dict(mode="sgg_union", year=1975,
            shp=ROOT / "data/raw/sgis/bnd_sigungu_1975/bnd_sigungu_00_1975_4Q.shp",
            results=ROOT / "data/results/national_assembly_8.json"),
    9: dict(mode="nec_emd", year=1975,
            emd=ROOT / "data/raw/nec/district_emd_9.json",
            shp=ROOT / "data/raw/sgis/bnd_dong_1975/bnd_dong_00_1975_4Q.shp",
            # NEC 투표구별 공백 선거구(연천권·의령권 등 통째 군) → 시군구 경계 union 폴백
            sgg_fallback=ROOT / "data/raw/sgis/bnd_sigungu_1975/bnd_sigungu_00_1975_4Q.shp",
            results=ROOT / "data/results/national_assembly_9.json"),
    10: dict(mode="nec_emd", year=1980,
             emd=ROOT / "data/raw/nec/district_emd_10.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_1980/bnd_dong_00_1980_4Q.shp",
             results=ROOT / "data/results/national_assembly_10.json"),
    11: dict(mode="nec_emd", year=1980,
             emd=ROOT / "data/raw/nec/district_emd_11.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_1980/bnd_dong_00_1980_4Q.shp",
             sgg_fallback=ROOT / "data/raw/sgis/bnd_sigungu_1980/bnd_sigungu_00_1980_4Q.shp",  # 부산북구 등 공백
             results=ROOT / "data/results/national_assembly_11.json"),
    12: dict(mode="nec_emd", year=1985,
             emd=ROOT / "data/raw/nec/district_emd_12.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_1985/bnd_dong_00_1985_4Q.shp",
             results=ROOT / "data/results/national_assembly_12.json"),
    13: dict(mode="nec_emd", year=1990,
             emd=ROOT / "data/raw/nec/district_emd_13.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_1990/bnd_dong_00_1990_4Q.shp",
             # 대전 직할시 승격(1989)이 SGIS 1990과 엇갈림 — 대전시 선거구 동은 SGIS 대전(25)
             sido_override={"대전시": "25"},
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
    21: dict(mode="nec_emd", year=2020,   # OhmyNews 대조용 (내 복원 vs 권위본)
             emd=ROOT / "data/raw/nec/district_emd_21.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_2020/bnd_dong_00_2020_4Q.shp",
             results=ROOT / "data/results/national_assembly_21.json"),
    22: dict(mode="nec_emd", year=2025,   # OhmyNews 대조용. SGIS 2025-2Q = 부천 일반구 부활(2024-01) 반영
             emd=ROOT / "data/raw/nec/district_emd_22.json",
             shp=ROOT / "data/raw/sgis/bnd_dong_2025/bnd_dong_00_2025_2Q.shp",
             results=ROOT / "data/results/national_assembly_22.json"),
}

CANON = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도"}
# NEC 행정표준 시도코드 → SGIS 통계청 시도코드 (앞 2자리). nec_emd 조인용.
NEC2SGIS = {"11": "11", "26": "21", "27": "22", "28": "23", "29": "24", "30": "25",
            "31": "26", "51": "29", "41": "31", "42": "32", "43": "33", "44": "34",
            "45": "35", "46": "36", "47": "37", "48": "38", "49": "39",
            "52": "32", "53": "35"}  # 22대 특별자치도 새 코드: 강원52·전북53 → SGIS 32·35
# SGIS 시도2 권역(family) — 광역시는 모도(母道)에서 승격(경기↔인천, 경북↔대구, 경남↔부산·울산,
# 전남↔광주, 충남↔대전·세종). 시도무관 동매칭 fallback을 이 권역 안으로만 제한해, DMZ·경계시차로
# 자기 시도 SGIS에 없는 동이 먼 시도 동음이의(파주 진동면津東面→경남 마산 진동면鎭東面)로 잘못
# 매칭되는 것을 차단. 시군구 이동(군위 경북37→대구22 2023)은 권역 내라 유지.
SGIS_FAM = {}
for _grp in [{"11"}, {"21", "26", "38"}, {"22", "37"}, {"23", "31"}, {"24", "36"},
             {"25", "29", "34"}, {"32"}, {"33"}, {"35"}, {"39"}]:
    for _s in _grp:
        SGIS_FAM[_s] = _grp
# 시도 풀네임 → SGIS 통계청 시도2 (시군구 union 모드: SGIS sigungu_cd[:2] 매칭)
SIDO_SGIS2 = {"서울특별시": "11", "부산광역시": "21", "대구광역시": "22", "인천광역시": "23",
              "광주광역시": "24", "대전광역시": "25", "울산광역시": "26", "세종특별자치시": "29",
              "경기도": "31", "강원도": "32", "강원특별자치도": "32", "충청북도": "33",
              "충청남도": "34", "전라북도": "35", "전북특별자치도": "35", "전라남도": "36",
              "경상북도": "37", "경상남도": "38", "제주특별자치도": "39", "제주도": "39"}
SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
}


def _nsgg(s):
    """시군구명 정규화(sgg_union) — 공백 제거 + 구 앞 시접두 제거.
    '인천시 동구'→'동구', '대구시중구'→'중구', '강릉시'→'강릉시'(유지), '종로구'→'종로구'."""
    s = s.replace(" ", "")
    return re.sub(r"^[가-힣]+시(?=[가-힣]+구$)", "", s)


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
    _fl = {f.lower(): f for f in fields}  # 대소문자 무관 필드명 (연도별 ADM_DR_CD/adm_dr_cd/ADM_CD 혼재)
    is_sgg = "sigungu_cd" in _fl  # 시군구 경계 파일(sgg_union 모드)
    def _fld(*cands):
        for c in cands:
            if c.lower() in _fl: return _fl[c.lower()]
        raise KeyError(f"필드 없음 {cands} / 실제 {fields}")
    CD = _fld("sigungu_cd") if is_sgg else _fld("adm_cd", "adm_dr_cd")
    NM = _fld("sigungu_nm") if is_sgg else _fld("adm_nm", "adm_dr_nm")
    geom_by_cd = {}
    sido_dong_idx = defaultdict(list)  # (SGIS시도2, 동명변형) → [adm_cd] (nec_emd)
    dong_global = defaultdict(list)    # 동명변형 → [adm_cd] (시도 무관 — 이동 시군구 fallback)
    sido_names = defaultdict(list)     # SGIS시도2 → [(adm_cd, 정규화동명)] (퍼지)
    sgg_idx = {}                       # (SGIS시도2, 시군구명) → sigungu_cd (sgg_union)
    for sr in sf.iterShapeRecords():
        cd = str(sr.record[CD]).strip()
        g = shape(sr.shape.__geo_interface__)
        if not g.is_valid:
            g = g.buffer(0)
        geom_by_cd[cd] = g
        nm = str(sr.record[NM]).strip()
        if is_sgg:
            sgg_idx[(cd[:2], _nsgg(nm))] = cd
        else:
            sido_dong_idx[(cd[:2], nm)].append(cd)
            dong_global[nm].append(cd)
            if _ndong(nm) != nm:
                sido_dong_idx[(cd[:2], _ndong(nm))].append(cd)
                dong_global[_ndong(nm)].append(cd)
            sido_names[cd[:2]].append((cd, _ndong(nm)))
    print(f"SGIS {'시군구' if is_sgg else '동'}: {len(geom_by_cd)}개 (필드 {CD}/{NM})", file=sys.stderr)

    def reproj(geom):
        return shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)

    # 3) 선거구 → {adm_cd/sigungu_cd} (모드별)
    district_cds = defaultdict(set)
    miss_dong = total_dong = 0
    if cfg["mode"] == "sgg_union":  # 옛 총선(5~8대): 선거구 = 시군구 조합 union
        ext = {}  # 위키 매핑(5/6/7): (시도약칭, 선거구명) → [시군구]
        if cfg.get("sgg_map") and cfg["sgg_map"].exists():
            for r in json.loads(cfg["sgg_map"].read_text(encoding="utf-8")):
                ext[(SIDO_SHORT.get(r["sido"], r["sido"]), r["name"])] = r.get("sigungu", [])
        for (skey, name), race in by_key.items():
            s2 = SIDO_SGIS2.get(race["sido"])
            m = re.search(r"\((.+)\)", name)  # 8대 '제1선거구(춘천시·춘성군)'
            sggs = re.split(r"[·∙•・,]", m.group(1)) if m else ext.get((skey, name), [])
            for sgg in sggs:
                sgg = sgg.strip()
                if not sgg:
                    continue
                total_dong += 1
                cd = sgg_idx.get((s2, _nsgg(sgg)))
                if cd:
                    district_cds[(skey, name)].add(cd)
                else:
                    miss_dong += 1
    elif cfg["mode"] == "wwolf":
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
        # 1차: match표(admdongkor). 실패분은 SGIS 직접매칭 폴백(match표 누락 시군구 = 밀양 등).
        wf_fail = []                                  # 폴백 후보: (sido_short, sgn, s2, sgg, emd, cands)
        wf_sgg_vote = defaultdict(Counter)            # (시도2, 시군구명) → {시군구코드: n} — 유일매칭 학습
        with cfg["wwolf"].open(encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                sido = (row.get("광역") or "").strip(); sgg = (row.get("시군구") or "").strip()
                emd = (row.get("읍면동") or "").strip(); sgn = (row.get("선거구") or "").strip()
                if not sgn or not emd or emd in {"합계", "계"} or "투표" in emd:
                    continue
                total_dong += 1
                cds = dong_to_cd.get(f"{sido} {sgg} {emd}")
                if cds:
                    district_cds[(SIDO_SHORT.get(sido, sido), sgn)].update(cds)
                    continue
                # 폴백: SGIS 동 직접매칭 (시도2, 동명). 시군구 모호는 학습으로 해소.
                s2 = SIDO_SGIS2.get(sido)
                cands = sido_dong_idx.get((s2, emd)) or sido_dong_idx.get((s2, _ndong(emd))) or []
                if not cands:
                    miss_dong += 1; continue
                sgg5 = {c[:5] for c in cands}
                if len(sgg5) == 1:
                    wf_sgg_vote[(s2, sgg)][next(iter(sgg5))] += 1   # 유일 → 그 시군구 코드 학습
                wf_fail.append((SIDO_SHORT.get(sido, sido), sgn, s2, sgg, emd, cands))
        # 2차: 학습된 시군구 코드로 폴백 확정(모호 동은 같은 시군구 코드만 채택)
        wf_learned = {k: v.most_common(1)[0][0] for k, v in wf_sgg_vote.items()}
        wf_filled = 0
        for sido_short, sgn, s2, sgg, emd, cands in wf_fail:
            learned = wf_learned.get((s2, sgg))
            chosen = [c for c in cands if c[:5] == learned] if learned else cands
            if chosen:
                district_cds[(sido_short, sgn)].update(chosen); wf_filled += 1
            else:
                miss_dong += 1
        if wf_filled:
            print(f"wwolf SGIS 직접매칭 폴백: {wf_filled}개 동 (match표 누락 시군구)", file=sys.stderr)
    else:  # nec_emd: NEC 투표구별. 하드코딩 conv 대신 데이터로 NEC구→SGIS구 학습 + 기하 소거.
        recs = json.loads(cfg["emd"].read_text(encoding="utf-8"))
        sido_ov = cfg.get("sido_override", {})  # 시도승격 보정: 선거구명 substr → SGIS 시도2
        def _s2(sgg_code, name):
            for pre, ov in sido_ov.items():
                if pre in name:
                    return ov
            return NEC2SGIS.get(sgg_code[:2], sgg_code[:2])
        # Pass 1: NEC sgg_code → SGIS 구코드(4자리). 권위적: rec의 sgg_name(영월군 등)을 SGIS 시군명에
        # 직접 매칭(bnd_sigungu). 일반 면명(남·북·동면)만 가진 선거구가 같은 시도 동음이의(춘성·홍천
        # 남면)로 오매칭되던 것 차단. 시군명 소스 없으면 고유 동매칭 학습으로 폴백.
        sgg_name_map = {}   # (시도2, 정규화시군명) → SGIS 4자리코드
        _sggshp = cfg.get("sgg_fallback") or (ROOT / f"data/raw/sgis/bnd_sigungu_{cfg.get('year')}/bnd_sigungu_00_{cfg.get('year')}_4Q.shp")
        if _sggshp and Path(_sggshp).exists():
            _rdr = shapefile.Reader(str(_sggshp), encoding="cp949")
            _fn = {f[0].lower(): f[0] for f in _rdr.fields[1:]}  # 필드명 대소문자 무관(1985~95는 대문자)
            _cf, _nf = _fn.get("sigungu_cd"), _fn.get("sigungu_nm")
            if _cf and _nf:
                for sr in _rdr.iterRecords():
                    scd = str(sr[_cf]).strip()
                    sgg_name_map[(scd[:2], _nsgg(str(sr[_nf]).strip()))] = scd[:4]
        gu_vote = defaultdict(Counter)
        for r in recs:
            s2 = _s2(str(r["sgg_code"]), r["district"])
            for dong in r["dongs"]:
                d = re.sub(r"^[가-힣]+[시군구] ", "", dong)
                cands = sido_dong_idx.get((s2, d)) or sido_dong_idx.get((s2, _ndong(d))) or []
                if len(cands) == 1:
                    gu_vote[str(r["sgg_code"])][cands[0][:4]] += 1
        gu_map = {sgg: cnt.most_common(1)[0][0] for sgg, cnt in gu_vote.items()}
        # 권위적 앵커로 덮어쓰기 (sgg_name 직접 매칭이 있으면 우선)
        for r in recs:
            s2 = _s2(str(r["sgg_code"]), r["district"])
            auth = sgg_name_map.get((s2, _nsgg(r.get("sgg_name", ""))))
            if auth:
                gu_map[str(r["sgg_code"])] = auth
        # 시군 코드(4자리) → 그 시군을 명시한 선거구 집합. 이동시군구 fallback·Pass4.5 권위배정 공용 가드.
        sgg2district = defaultdict(set)
        for r in recs:
            c4 = sgg_name_map.get((_s2(str(r["sgg_code"]), r["district"]), _nsgg(r.get("sgg_name", ""))))
            if c4:
                sgg2district[c4].add((SIDO_SHORT.get(r["sido"], r["sido"]), r["district"]))

        # Pass 2: 학습된 구로 매칭(충돌 tiebreak·퍼지 제한). 미매칭 추적.
        unmatched = defaultdict(list)  # key → [(SGIS구, dong)]
        for r in recs:
            sido_short = SIDO_SHORT.get(r["sido"], r["sido"])
            key = (sido_short, r["district"])
            nec_sgg = str(r["sgg_code"])
            s2 = _s2(nec_sgg, r["district"])
            gu = gu_map.get(nec_sgg)
            for dong in r["dongs"]:
                total_dong += 1
                dong = re.sub(r"^[가-힣]+[시군구] ", "", dong)  # '연기군 부용면' 접두 제거
                alias = DONG_ALIAS.get((sido_short, dong))
                if alias:  # 개명·분동 — 지정 SGIS 동(들)
                    got = [c for t in alias for c in sido_dong_idx.get((s2, t), [])]
                else:
                    cands = sido_dong_idx.get((s2, dong)) or sido_dong_idx.get((s2, _ndong(dong))) or []
                    if gu:
                        # 학습 구(권위 앵커)로 한정 — 동명충돌 tiebreak 겸, 유일하지만 타시군인 동음이의
                        # (정선군 '사북면'이 SGIS엔 춘성 사북면뿐 → 춘성 오배정) 차단. 빈 결과는 퍼지/Pass5 위임.
                        cands = [c for c in cands if c[:4] == gu]
                    elif len(cands) > 1:  # 구 미학습 + 동명 충돌 → cands[0] 난수배정 금지(춘천 stray 원인)
                        cands = []        # 미매칭으로 두고 Pass3 기하 인접해결에 위임.
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
                if not got:  # 이동 시군구(군위 2023 경북→대구 등 — SGIS연도 시도≠선거시점) — 전국 유일 동명이면 시도무관 매칭.
                    # 단 같은 권역(모도↔승격광역시)으로 제한 — 동음이의(파주 진동면→경남 마산) 차단.
                    g2 = set(dong_global.get(dong, [])) | set(dong_global.get(_ndong(dong), []))
                    fam = SGIS_FAM.get(s2, {s2})
                    g2 = {c for c in g2 if c[:2] in fam}
                    # 다른 선거구가 명시한 시군은 차용 금지 — 용인 외서면(SGIS 1985 부재)이 권역 유일
                    # 가평 외서면을 잡아 제7→가평 stray 만들던 것 차단(가평은 제10 소유). 무소속 코드는 허용.
                    g2 = {c for c in g2 if not (sgg2district.get(c[:4]) and key not in sgg2district[c[:4]])}
                    if len(g2) == 1:
                        got = [next(iter(g2))]
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

        # Pass 4: NEC 투표구별 공백 선거구 — SGIS 시군구 경계 union 폴백(통째 군/구)
        if cfg.get("sgg_fallback") and cfg["sgg_fallback"].exists():
            ssf = shapefile.Reader(str(cfg["sgg_fallback"]), encoding="cp949")
            sgg_g = {}
            for sr in ssf.iterShapeRecords():
                scd = str(sr.record["sigungu_cd"]).strip()
                g = shape(sr.shape.__geo_interface__)
                geom_by_cd[scd] = g if g.is_valid else g.buffer(0)
                sgg_g[(scd[:2], _nsgg(str(sr.record["sigungu_nm"]).strip()))] = scd
            nfb = 0
            for (skey, name), race in by_key.items():
                if district_cds.get((skey, name)):
                    continue
                s2 = SIDO_SGIS2.get(race["sido"])
                m = re.search(r"\((.+)\)", name)
                sggs = re.split(r"[·∙•・,]", m.group(1)) if m else [re.sub(r"[갑을병정]$", "", name)]
                for sgg in sggs:
                    scd = sgg_g.get((s2, _nsgg(sgg.strip())))
                    if scd:
                        district_cds[(skey, name)].add(scd)
                if district_cds.get((skey, name)):
                    nfb += 1
            if nfb:
                print(f"시군구 폴백 복원: {nfb}개 선거구", file=sys.stderr)

        # Pass 4.5: 시군 코드 권위배정 — 미배정 SGIS 동을, 그 시군(code[:4])을 단독 보유한
        # 선거구로 먼저 귀속(이름매칭 실패한 화천 등 → 그 시군 명시한 선거구). 기하흡수(Pass5)가
        # 작은 동들을 교차-시군 누적 흡수해 큰 쪼가리(영월 제5에 화천조각) 만들던 것 차단.
        assigned = set().union(*district_cds.values()) if district_cds else set()
        auth_n = 0
        for c in geom_by_cd:
            if c in assigned:
                continue
            ds = sgg2district.get(c[:4])
            if ds and len(ds) == 1:
                district_cds[next(iter(ds))].add(c); auth_n += 1
        if auth_n:
            print(f"시군 권위배정 고아: {auth_n}개", file=sys.stderr)

        # Pass 5: 잔여 미배정 SGIS 동 → 기하 인접 선거구 흡수.
        # NEC 투표구별(VCCP08)이 SGIS 동보다 적은 회차(18·19대 등)는 매칭 안 된 SGIS 동이
        # 흰 구멍으로 남음. 각 미배정 동을, 경계를 가장 길게 공유하는 인접 배정-동의 선거구로
        # 흡수(선거구는 연속이라 내부 미배정 동은 둘러싼 선거구 1개로 귀속). 여러 라운드 반복.
        from shapely.strtree import STRtree
        cd_to_key = {}
        for k, cds in district_cds.items():
            for c in cds:
                cd_to_key[c] = k
        unassigned = [c for c in geom_by_cd if c not in cd_to_key]
        infilled = cross_sgg = 0
        for _rnd in range(8):
            if not unassigned:
                break
            a_cds = [c for c in cd_to_key if c in geom_by_cd]
            a_geoms = [geom_by_cd[c] for c in a_cds]
            tree = STRtree(a_geoms)
            newly, still = {}, []
            for c in unassigned:
                g = geom_by_cd[c]
                sgg = c[:4]
                # 같은 시군구(code[:4]) 선거구 우선 — 교차 시군구로 번지는 오배정 차단.
                # 같은 시군구 후보가 없을 때만 인접 시군구로(드묾·통째 미매칭 군). 둘 다 공유경계 최장.
                same = (None, 0.0); other = (None, 0.0)
                for j in tree.query(g.buffer(1)):
                    ac = a_cds[int(j)]
                    inter = g.boundary.intersection(a_geoms[int(j)].boundary)
                    ln = 0.0 if inter.is_empty else inter.length
                    if ln <= 0:
                        continue
                    if ac[:4] == sgg:
                        if ln > same[1]: same = (cd_to_key[ac], ln)
                    elif ln > other[1]:
                        other = (cd_to_key[ac], ln)
                if same[0]:
                    newly[c] = same[0]
                elif other[0] and g.area < 0.002:        # 교차-시군구는 작은 슬리버만(큰 orphan을 인접
                    newly[c] = other[0]; cross_sgg += 1   # 타시군 선거구에 흡수해 생기던 큰 쪼가리 방지)
                else:
                    still.append(c)
            if not newly:
                break
            for c, k in newly.items():
                district_cds[k].add(c)
                cd_to_key[c] = k
            infilled += len(newly)
            unassigned = still
        if infilled:
            print(f"기하 인접 흡수: {infilled}개 동 (같은시군구 {infilled-cross_sgg}·교차 {cross_sgg}·잔여 {len(unassigned)})", file=sys.stderr)

        # Pass 5b: 잔여(경계 정점 불일치로 공유길이 0) — 버퍼(≈10m) 면적 겹침으로 인접 선거구 흡수.
        # 내부 구멍(전주 효자2동·인천 계양동·양산 상북동 등 둘러싼 선거구와 미세 틈) 메움.
        if unassigned:
            eps = 1e-4  # ≈10m
            a_cds = [c for c in cd_to_key if c in geom_by_cd]
            a_geoms = [geom_by_cd[c] for c in a_cds]
            tree = STRtree(a_geoms)
            b_filled = 0
            for c in list(unassigned):
                g = geom_by_cd[c].buffer(eps)
                best = (None, 0.0)
                for j in tree.query(g):
                    ov = g.intersection(a_geoms[int(j)].buffer(eps)).area
                    if ov > best[1]:
                        best = (cd_to_key[a_cds[int(j)]], ov)
                if best[0]:
                    district_cds[best[0]].add(c)
                    cd_to_key[c] = best[0]
                    b_filled += 1
            if b_filled:
                print(f"버퍼 인접 흡수(Pass5b): {b_filled}개 동", file=sys.stderr)

    # 4) 선거구별 union → 전체 topology 공유 arc 단순화
    features = []
    name_to_code = {}
    incomplete = []
    # 4a) 풀해상도 선거구 폴리곤 수집 (5179 union → 도서 제거 → WGS84)
    raw = []  # (skey, name, race, geom_wgs)
    for (skey, name), race in sorted(by_key.items()):
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
        raw.append((skey, name, race, reproj(u)))
    # 4b) 단순화 — 모드별 분기.
    #   nec_emd: raw 그대로 내보내고 mapshaper(위상 보존)가 공유 arc를 함께 줄여 인접 선거구 틈 0.
    #            (동이 SGIS 한 소스라 edge 정확히 공유 → mapshaper가 깨끗이 처리.)
    #   wwolf(20대)/sgg_union(8대): SGIS+admdongkor 혼합·동 매칭실패로 구조적 구멍이 있어 mapshaper가
    #            무익(틈 못 메우고 용량만 ↑). per-polygon DP로 빠르게 축소(원래 방식 유지).
    # 매칭을 근본 보강(wwolf SGIS 폴백 등)해 커버리지를 완전히 한 뒤로는 전 모드 mapshaper 적용.
    use_mapshaper = True
    simp_geoms = [r[3].buffer(0) for r in raw]
    # 4c) feature 작성
    for i, ((skey, name, race, _), u) in enumerate(zip(raw, simp_geoms)):
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
    # nec_emd만 mapshaper 위상 보존 단순화 — raw union(공유 동 edge)을 함께 줄여 인접 선거구 틈 0 + 용량↓.
    # (per-polygon은 공유 경계 어긋나 틈 생김, topojson은 일부 회차 OOM → mapshaper 채택.)
    if use_mapshaper:
        raw_kb = out_geo.stat().st_size // 1024
        _ms = ROOT / "node_modules/.bin/mapshaper"
        try:
            # snap: 근접 정점 병합(슬리버 → 공유 arc 인식) → -clean이 틈 제거.
            # nec_emd는 동이 SGIS 단일소스라 2%로 ~400KB. wwolf(20대)는 admdongkor 혼합·고해상이라
            # raw 정점이 훨씬 많아 같은 2%면 1.5MB → 더 공격적으로(0.6%) 줄여 용량 맞춤(위상은 보존).
            pct = "2%" if cfg["mode"] == "nec_emd" else "0.2%"
            subprocess.run([str(_ms), str(out_geo), "snap", "-simplify", pct, "keep-shapes",
                            "-clean", "gap-fill-area=2km2", "-o", str(out_geo), "force"],
                           check=True, capture_output=True, timeout=300)
        except Exception as e:
            print(f"  ⚠ mapshaper 실패(raw {raw_kb}KB 유지): {e}", file=sys.stderr)
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
