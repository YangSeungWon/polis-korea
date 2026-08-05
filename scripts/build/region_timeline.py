"""지역 정치사 타임라인 — 시간축은 합치고 **수치 비교는 series 안에서만**.

## 두 가지를 섞지 않는다

    timeline continuity  ≠  metric comparability
    same election family ≠  same metric series

2017 대선 30% → 2018 시장선거 45% → 2020 총선 48%을 한 선으로 이으면 시각적으로는
자연스럽지만 정치적으로는 같은 측정량이 아니다. 직위도 후보 구도도 다르다.

`election_type`으로 가르는 것도 아직 넓다. 지방선거 하나에 광역단체장·기초단체장·
광역의원·기초의원·비례가 다 들어 있고 서로 이을 수 없다. 그래서 명시적으로:

    comparison_series_id = president:national
                           general:district
                           local:metro_mayor / local:municipal_mayor
                           local:metro_council_district / ...

renderer는 **같은 series 안에서만** delta를 잇는다.

## 화면이 새 주장을 만들지 않는다

비교 가능 판정은 comparison engine이 이미 했다(direct/aggregated/reaggregated/
context_only + measurement/inference capability). 여기서 다시 만들지 않고 그대로
실어 나른다. level inference가 금지된 곳(하남시갑)은 과거 재집계 수준값을 headline으로
쓰지 않고 허용된 delta만 낸다.

## 이름을 조용히 덮어쓰지 않는다

1995년은 '이천군'이고 1998년은 '이천시'다. 현재 이름으로 소급해 칠하지 않는다.
각 datum이 **그 시점의 geography entity/version**을 직접 참조한다.

사용: python scripts/build/region_timeline.py [지역명 ...]
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/build"))
from party_canon import disambiguate_party  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts/normalize"))
from reaggregate import dkey  # noqa: E402  (선거구 키는 '경기 하남시갑' — 시도 필수)

RESULTS = ROOT / "data/results"
AXES = ROOT / "data/parties/political_axes.json"
REAGG = ROOT / "data/reaggregated"
OUT = ROOT / "data/region_timeline"

FAMILIES = ("conservative", "democratic", "progressive", "regional", "other")

# 선거 종류 → 비교 series. 같은 지방선거라도 직위가 다르면 잇지 않는다.
# NEC sg_typecode가 직위를 가른다. 같은 지방선거라도 시도지사와 시군구청장은
# 다른 시계열이다 — 직위도 유권자 구성도 다르다.
LOCAL_OFFICE = {
    "11": "metro_mayor",            # 시도지사
    "3": "education_superintendent",  # 교육감
    "4": "municipal_mayor",         # 시군구청장
    "5": "metro_council_district",  # 시도의원
    "6": "municipal_council_district",  # 시군구의원
    "8": "metro_council_pr",        # 시도의원 비례
    "9": "municipal_council_pr",    # 시군구의원 비례
}


def kind_of(eid: str) -> str:
    """election_id에서 선거 종류. _meta에 type이 없는 파일이 많다."""
    for k, v in (("-pres-", "pres"), ("-general-", "general"), ("-local-", "local")):
        if k in eid:
            return v
    return "byelection" if "byelection" in eid or "재·보궐" in eid else "unknown"


def series_id(kind: str, race: dict) -> str:
    """수치를 이어도 되는 단위. **election_type보다 좁다.**"""
    if kind == "pres":
        return "president:national"
    if kind == "general":
        return "general:pr" if "비례" in str(race.get("name") or "") else "general:district"
    if kind == "local":
        return "local:" + LOCAL_OFFICE.get(str(race.get("sg_typecode")), "unknown")
    return f"{kind}:unknown"


def composition(cands: list, date: str, fam: dict) -> dict:
    """계열 구성. 분모는 **전체 유효표**다 — mixed·unknown·무소속을 빼거나 재정규화하지 않는다.

    `unknown 4%`와 `무소속 12%`는 전혀 다른 정보다. 무소속은 분류 실패가 아니라
    애초에 정당 계보가 없는 후보 유형이다.
    """
    acc: dict = collections.Counter()
    mixed_of: dict = {}
    for c in cands:
        v, p = c.get("votes"), c.get("party")
        if not isinstance(v, (int, float)) or not v:
            continue
        if not p or p == "무소속":
            acc["independent"] += v
            continue
        canon = disambiguate_party(p, date)
        e = fam.get(canon) or {}
        f = e.get("family", "unknown")
        acc[f if f in FAMILIES or f == "mixed" else "unknown"] += v
        if f == "mixed":
            mixed_of[canon] = e.get("families") or []
    total = sum(acc.values())
    if not total:
        return {}
    pct = lambda v: round(v / total * 100, 2)      # noqa: E731
    single = sum(acc.get(f, 0) for f in FAMILIES)
    return {
        "share": {k: pct(v) for k, v in sorted(acc.items())},
        "single_family_coverage": pct(single),
        "lineage_resolved_coverage": pct(single + acc.get("mixed", 0)),
        "mixed_share": pct(acc.get("mixed", 0)),
        "unknown_share": pct(acc.get("unknown", 0)),
        "independent_share": pct(acc.get("independent", 0)),
        # mixed가 어느 계열들의 합인지 — '중도'로 오해되지 않게
        "mixed_constituents": {k: v for k, v in sorted(mixed_of.items())},
        "total_votes": total,
    }


def _reagg_for(district: str) -> dict | None:
    """comparison engine이 허용한 주장만 가져온다. 여기서 새로 판정하지 않는다."""
    f = REAGG / "22__21.json"
    if not f.exists():
        return None
    v = json.loads(f.read_text(encoding="utf-8"))["districts"].get(district)
    if not v:
        return None
    cap = v.get("capability") or {}
    inf = cap.get("inference_to_full_result") or {}
    dl = (cap.get("comparison") or {}).get("delta") or {}
    return {
        "method": v["method"],
        "measurement_scope": ("attributable_only" if v["method"] == "reaggregated"
                              else "official_full"),
        # 화면이 쓸 수 있는 주장 — backend가 정한 것이다
        "may_show_level": bool(inf.get("level", {}).get("allowed")),
        "may_show_winner": bool(inf.get("winner", {}).get("allowed")),
        "may_show_delta": bool(dl.get("allowed")),
        "delta": v.get("swing_attributable_basis"),
        "delta_blocked": {k: x["reason"] for k, x in (dl.get("by_party") or {}).items()
                          if not x["allowed"]},
        "coverage": v["provenance"]["coverage"],
        "note": v["provenance"]["denominator"],
    }


def main(regions: list[str]) -> int:
    ax = json.loads(AXES.read_text(encoding="utf-8"))
    fam = ax["lineage_family"]
    # strict가 기본. historical은 근거 있는 bridge로 제도적 단절을 건넌 값 —
    # 화면에서 토글로 고를 수 있게 둘 다 싣는다. 섞지 않는다.
    fam_h = ax["lineage_family_historical"]
    OUT.mkdir(parents=True, exist_ok=True)
    built = 0
    for region in regions:
        points = []
        for f in sorted(RESULTS.glob("*.json")):
            if ".sigungu" in f.name or f.name.startswith(
                    ("local_", "national_assembly_", "presidential_")):
                continue
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except Exception:                                   # noqa: BLE001
                continue
            meta = doc.get("_meta") or {}
            date = meta.get("election_date") or meta.get("date") or ""
            kind = kind_of(meta.get("election_id") or f.stem)
            if not date:
                continue
            for race in (doc.get("district") or doc.get("races") or []):
                if not isinstance(race, dict):
                    continue
                nm = (race.get("name") or race.get("district")
                      or race.get("sigungu") or race.get("sido") or "")
                if region not in nm:
                    continue
                cands = [c for c in (race.get("candidates") or []) if isinstance(c, dict)]
                if not cands:
                    continue
                comp = composition(cands, date, fam)
                comp_h = composition(cands, date, fam_h)
                win = max(cands, key=lambda c: c.get("votes") or 0)
                sid = series_id(kind, race)
                key = dkey(race.get("sido") or "", nm)
                points.append({
                    "election_id": meta.get("election_id") or f.stem,
                    "election_type": kind,
                    "election_date": date,
                    "label": meta.get("election") or f.stem,
                    # 같은 series 안에서만 수치를 잇는다
                    "comparison_series_id": sid,
                    # 그 시점의 지리 entity — 현재 이름으로 소급하지 않는다
                    "geography_entity_id": f"electoral_district:{nm}",
                    "boundary_valid_at": date,
                    "unit_name_at_the_time": nm,
                    # 실제 선거 결과 (위)
                    "winner": {"name": win.get("name"), "party": win.get("party"),
                               "pct": win.get("pct")},
                    # 계보 구성 (아래) — winner와 섞지 않는다
                    "lineage_composition": comp,
                    "lineage_composition_historical": comp_h,
                    "comparison": _reagg_for(key),
                })
        if not points:
            print(f"  {region}: 결과 없음")
            continue
        points.sort(key=lambda p: p["election_date"])
        doc = {
            "_note": ("지역 정치사 타임라인. 시간축은 합치되 수치 비교는 "
                      "comparison_series_id가 같은 점 사이에서만 한다. "
                      "winner와 계보 구성은 별도 층이다 — winner_family를 지역 전체 "
                      "정치구성의 대리값으로 쓰지 않는다."),
            "region": region,
            "series": sorted({p["comparison_series_id"] for p in points}),
            "points": points,
        }
        (OUT / f"{region}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        built += 1
        ser = collections.Counter(p["comparison_series_id"] for p in points)
        print(f"  {region}: {len(points)}개 · series {dict(ser)}")
    print(f"\n→ {OUT.name}/ {built}개 지역")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:] or ["하남", "부천", "군위", "이천", "종로"]
    sys.exit(main(args))
