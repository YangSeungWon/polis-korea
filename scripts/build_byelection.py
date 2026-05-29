"""재보궐(VT039) → data/polls/byelection.json.

국회의원 보궐선거 후보지지 표(election_office='국회의원후보')만 추출,
선거구(district) 단위로 group. 지선과 별개 파일.

선거구 정규화: "부산광역시 북구 갑 선거구" / "북구갑선거구" / "북구 북구갑 선거구 지역"
→ canonical "부산 북구갑".
"""
from __future__ import annotations
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from parse_pdf import _is_noise_name  # noqa: E402
META_CSV = ROOT / "data" / "raw" / "nesdc_byelection.csv"
PARSED_DIR = ROOT / "data" / "raw" / "parsed"
OUT = ROOT / "data" / "polls" / "byelection.json"

# VT039 카테고리(재보궐) 내에서 parse_pdf가 "국회의원후보"로 못 잡은 표 구제.
# title에 "국회의원" + 메트릭(지지/적합/선호/후보), 또는 "보궐/재보궐/재선거" + "국회의원".
# 예: "차기 북구 갑 국회의원 지지도", "지방선거 및 국회의원 재보궐 선거 여론조사".
BYELECT_TITLE_FALLBACK = re.compile(
    r"국회의원.{0,40}?(지지[도율]?|적합도?|선호도?|후보)"
    r"|(?:보궐|재보궐|재선거).{0,30}?국회의원"
)

SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "제주도": "제주",
}

# 선거구 대략 좌표 (지도 마커용) — 시군구 centroid 근사. 키는 canon_district 출력과 일치.
DISTRICT_LATLNG = {
    "부산 북구갑": [35.197, 128.990],
    "경기 평택시을": [36.992, 127.112],
    "경기 하남시갑": [37.539, 127.215],
    "인천 연수구갑": [37.410, 126.678],
    "제주 서귀포시": [33.254, 126.560],
    "충남 공주부여청양": [36.395, 126.880],
    "울산 남구갑": [35.544, 129.330],
    "경기 안산시갑": [37.300, 126.840],
    "대구 달성군": [35.774, 128.431],
    "충남 아산시을": [36.790, 127.002],
    "인천 계양구을": [37.537, 126.738],
    "전북 군산김제부안갑": [35.967, 126.737],
}


def canon_district(region: str) -> str:
    r = region.replace("선거구", " ").replace("지역", " ").strip()
    r = re.sub(r"\s+", " ", r)
    for full, short in SIDO_SHORT.items():
        r = r.replace(full, short)
    toks = list(dict.fromkeys(r.split()))  # dedup, 순서 유지
    if not toks:
        return ""
    sido = toks[0] if toks[0] in SIDO_SHORT.values() else ""
    rest = [t for t in toks if t != sido]
    marker = ""
    m = re.search(r"(갑|을|병|정)", r)
    if m:
        marker = m.group(1)
    # 합구 (공주부여청양 등) — 시군구 여러 개
    base_parts = []
    for t in rest:
        tt = re.sub(r"(갑|을|병|정)$", "", t)
        if re.search(r"(시|군|구)$", tt) and tt not in base_parts:
            base_parts.append(tt)
    if not base_parts and rest:
        base_parts = [re.sub(r"(갑|을|병|정)$", "", rest[0])]
    base = "".join(p[:-1] if p[-1] in "시군구" and len(base_parts) > 1 else p for p in base_parts) \
        if len(base_parts) > 1 else (base_parts[0] if base_parts else "")
    label = f"{sido} {base}{marker}".strip()
    return label


def main():
    rows = list(csv.DictReader(open(META_CSV, encoding="utf-8")))
    by_district: dict[str, list] = {}
    n_polls = 0
    for m in rows:
        nid = m["ntt_id"]
        district = canon_district(m.get("region", ""))
        if not district or district == "전국":
            continue
        # parsed JSON
        cands_tables = []
        for path in PARSED_DIR.glob(f"{nid}_*.json"):
            try:
                d = json.load(open(path, encoding="utf-8"))
            except Exception:
                continue
            for q in d.get("questions", []):
                ttl = (q.get("title", "") or "")
                qt = (q.get("question_text", "") or "") + " " + ttl
                # election_office가 "국회의원후보"면 통과.
                # "기타"여도 title에 국회의원 + 메트릭이면 통과 (parse_pdf 분류 누락 구제).
                # "정당지지"·"투표의향" 등 다른 office는 제외 (정당지지 표가 후보로 오인되지 않게).
                eo = q.get("election_office", "")
                if eo != "국회의원후보":
                    if eo != "기타" or not BYELECT_TITLE_FALLBACK.search(ttl):
                        continue
                # 단일정당 경선("더불어민주당 후보로 누가 적합") 제외 — 정당 간 본선 맞대결만.
                if re.search(r"(더불어민주당|국민의힘|조국혁신당|개혁신당|진보당|민주당)\s*후보(로|\s*중)", qt):
                    continue
                # 진짜 후보 = 이름(non-noise) + 정당 둘 다.
                # "후보 선택 기준"(소속정당/도덕성 등)·"투표 의향" 표 자동 배제.
                real = [c for c in q["candidates"]
                        if c.get("pct") is not None and c["party"]
                        and c["name"] and not _is_noise_name(c["name"])]
                # 정당 간 본선이면 서로 다른 정당 ≥2 (단일정당 적합도·경선 표 추가 배제)
                if len(real) >= 2 and len({c["party"] for c in real}) >= 2:
                    cands_tables.append((q, real))
        if not cands_tables:
            continue
        # 가장 후보 많은 표
        q, cs = max(cands_tables, key=lambda x: len(x[1]))
        rec = {
            "ntt_id": nid,
            "source_url": m.get("source_url", ""),
            "agency": m.get("agency", ""),
            "requester": m.get("requester", ""),
            "method": m.get("method", ""),
            "sample_size": m.get("sample_size", ""),
            "response_rate": m.get("response_rate", ""),
            "contact_rate": m.get("contact_rate", ""),
            "sample_error": m.get("sample_error", ""),
            "period_start": m.get("survey_start", ""),
            "period_end": m.get("survey_end", ""),
            "district": district,
            "table_title": q.get("title", ""),
            "candidates": [{"name": c["name"], "party": c["party"], "pct": c["pct"]} for c in cs],
        }
        by_district.setdefault(district, []).append(rec)
        n_polls += 1

    # 선거구별 최신순 정렬 + 중복 등록 제거
    # (같은 기관·기간·후보·수치 = NESDC 중복 등록. 서귀포 18638/18636 등)
    out_districts = []
    n_polls = 0
    for d, polls in sorted(by_district.items()):
        polls.sort(key=lambda p: p.get("period_end", ""), reverse=True)
        seen, uniq = set(), []
        for p in polls:
            sig = (p["agency"], p["period_start"], p["period_end"],
                   tuple((c["name"], c["pct"]) for c in p["candidates"]))
            if sig in seen:
                continue
            seen.add(sig)
            uniq.append(p)
        n_polls += len(uniq)
        out_districts.append({
            "district": d,
            "latlng": DISTRICT_LATLNG.get(d),
            "n_polls": len(uniq),
            "polls": uniq,
        })

    out = {
        "_meta": {
            "election": "2026년 재·보궐선거 (국회의원)",
            "source": "NESDC 등록현황 VT039",
            "election_date": "2026-06-03",
        },
        "districts": out_districts,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"재보궐: {len(out_districts)} 선거구, {n_polls} polls → {OUT.relative_to(ROOT)}")
    for d in out_districts:
        latest = d["polls"][0]
        top = max(latest["candidates"], key=lambda c: c["pct"]) if latest["candidates"] else None
        print(f"  {d['district']:18s} {d['n_polls']:2d}건 최신{latest['period_end']} "
              f"1위 {top['name'] if top else ''}({top['party'][:4] if top else ''}) {top['pct'] if top else ''}")


if __name__ == "__main__":
    main()
