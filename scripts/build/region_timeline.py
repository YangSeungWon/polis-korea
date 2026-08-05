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
GEO_ENT = ROOT / "data/geography/entities.json"
GEO_EV = ROOT / "data/geography/events.json"

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
        # 이름으로 가르면 **이름 없는 행**을 놓친다. 시군구별 집계 파일의 비례 행에는
        # name이 없어서 지역구로 분류됐다(군위군 비례 38정당이 지역구 series에 섞였다).
        # sg_typecode가 직위를 가르는 정본이다 — 7이 비례다.
        tc = str(race.get("sg_typecode") or "")
        if tc == "7" or "비례" in str(race.get("name") or ""):
            return "general:pr"
        return "general:district"
    if kind == "local":
        return "local:" + LOCAL_OFFICE.get(str(race.get("sg_typecode")), "unknown")
    return f"{kind}:unknown"


def _entities() -> list:
    if not GEO_ENT.exists():
        return []
    return json.loads(GEO_ENT.read_text(encoding="utf-8"))["entities"]


def resolve_version(name: str, date: str, ents: list) -> dict:
    """그 **시점에 유효한** geography version. 현재 이름으로 fallback하지 않는다.

        같은 이름 ≠ 같은 장소의 같은 시점 버전

    1995년은 '이천군'이고 1998년은 '이천시'다. 최신 version으로 소급해 칠하면
    election point의 의미 자체가 달라진다. 그래서 셋을 구분한다:

        resolved            그 시점 version이 정확히 하나
        ambiguous           둘 이상 — **빌드를 실패시킨다**
        no_entity_recorded  entity를 아직 기록하지 않았다 (placeholder가 아니라 공백)
    """
    hit = []
    for e in ents:
        if e.get("kind") != "admin_unit":
            continue
        # 하위 단위(일반구)는 이 지역의 **시점 버전**이 아니다. 포항시남구·북구를 후보로
        # 세면 '포항'이 늘 셋과 맞물려 모호해진다(실제로 77건이 모호로 잡혔다).
        if e.get("contained_in"):
            continue
        if e["name"] not in name and name not in e["name"]:
            continue
        f, t = e.get("valid_from") or "", e.get("valid_to") or "9999-12-31"
        if (not f or f <= date) and date < t:
            hit.append(e)
    if len(hit) == 1:
        return {"geography_version_id": hit[0]["id"], "resolution": "resolved",
                "name_at_the_time": hit[0]["name"]}
    if len(hit) > 1:
        return {"geography_version_id": None, "resolution": "ambiguous",
                "candidates": [e["id"] for e in hit]}
    return {"geography_version_id": None, "resolution": "no_entity_recorded"}


def geo_events(region: str) -> list:
    """행정구역 사건과 선거구 사건 — 같은 시간축에 올리되 **namespace를 나눈다**.

    행정구역 승격과 총선 선거구 분구는 다른 ontology다. 특히 선거구 변화는
    **관련 series에만** 영향을 준다 — 총선 선거구가 바뀌었다고 같은 지역의 대선
    시계열까지 끊으면 안 된다.
    """
    if not GEO_EV.exists():
        return []
    out = []
    for e in json.loads(GEO_EV.read_text(encoding="utf-8"))["events"]:
        names = [x.get("name") or x["id"].split(":")[-1]
                 for x in (e.get("from") or []) + (e.get("to") or [])]
        if not any(region in n for n in names):
            continue
        admin = e.get("kind") == "admin_unit"
        out.append({
            "event_id": e["id"],
            "namespace": "administrative_geography" if admin else "electoral_district",
            "effective_date": e.get("effective_date") or e.get("date"),
            "type": e.get("type"),
            "label": e.get("label") or e.get("id"),
            "from": [x["id"] for x in e.get("from") or []],
            "to": [x["id"] for x in e.get("to") or []],
            # 선거구 사건은 총선 series만 건드린다
            "affects_series": (["*"] if admin else ["general:district"]),
            "comparison_capability": e.get("comparison_capability"),
        })
    return sorted(out, key=lambda x: x["effective_date"] or "")


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


def comparison_edges(points: list) -> list:
    """점과 **따로** 만든다. 비교 불가는 점을 지우는 게 아니라 선만 끊는 것이다.

        비교 불가 ≠ 역사에서 사라짐

    부천은 광역동이 선거구를 가로질러 2020↔2024 delta를 못 낸다. 그렇다고 2020년
    선거가 없었던 게 아니다. 점은 둘 다 남고 그 사이 선만 없다.
    같은 comparison_series_id 안에서만 잇는다.
    """
    out = []
    by: dict = {}
    for p in points:
        by.setdefault(p["comparison_series_id"], []).append(p)
    for sid, ps in by.items():
        ps = sorted(ps, key=lambda x: x["election_date"])
        for a, b in zip(ps, ps[1:]):
            cm = b.get("comparison") or {}
            allowed = bool(cm.get("may_show_delta")) if cm else None
            out.append({
                "series": sid, "from": a["election_id"], "to": b["election_id"],
                "from_date": a["election_date"], "to_date": b["election_date"],
                # None = 비교 판정 자체가 없다(총선 외). False = 판정했고 막혔다.
                "delta_allowed": allowed,
                "method": cm.get("method"),
                "blocked_reason": (None if allowed is not False else
                                   ("가로지르는 동" if cm.get("method") == "context_only"
                                    else "구도 변화·편향 불안정")),
                "delta": cm.get("delta") if allowed else None,
                "measurement_scope": cm.get("measurement_scope"),
            })
    return sorted(out, key=lambda e: (e["series"], e["to_date"]))


def bridge_dependency(points: list) -> dict:
    """historical이 얼마나 **역사적 연속성 해석에 기대고 있나**.

    coverage 하나로 기본 모드를 정하면 안 된다. strict와 historical은 완성도 차이가
    아니라 다른 질문이다. historical resolved 96%인데 그중 58%가 bridge를 거친 것이면,
    읽기는 좋아도 상당 부분이 '강제해산 너머의 정치적 전통' 해석에 의존한다.
    그 사실을 알고 기본값을 정해야 한다.
    """
    tot = dep = 0.0
    for p in points:
        a, b = p.get("lineage_composition") or {}, p.get("lineage_composition_historical") or {}
        if not a or not b:
            continue
        v = b.get("total_votes") or 0
        tot += v * b.get("lineage_resolved_coverage", 0) / 100
        # historical에서만 분류된 표 = bridge 덕에 풀린 표
        dep += v * max(0.0, b.get("lineage_resolved_coverage", 0)
                       - a.get("lineage_resolved_coverage", 0)) / 100
    return {"historical_resolved_votes": round(tot),
            "bridge_dependent_votes": round(dep),
            "bridge_dependent_share_of_resolved":
                round(dep / tot * 100, 2) if tot else None}


def main(regions: list[str]) -> int:
    ax = json.loads(AXES.read_text(encoding="utf-8"))
    fam = ax["lineage_family"]
    # strict가 기본. historical은 근거 있는 bridge로 제도적 단절을 건넌 값 —
    # 화면에서 토글로 고를 수 있게 둘 다 싣는다. 섞지 않는다.
    fam_h = ax["lineage_family_historical"]
    ents = _entities()
    ambiguous: list = []
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
                    **resolve_version(region, date, ents),
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
        ambiguous += [(region, p["election_id"]) for p in points
                      if p["resolution"] == "ambiguous"]
        doc = {
            "_note": ("지역 정치사 타임라인. 시간축은 합치되 수치 비교는 "
                      "comparison_series_id가 같은 점 사이에서만 한다. "
                      "winner와 계보 구성은 별도 층이다 — winner_family를 지역 전체 "
                      "정치구성의 대리값으로 쓰지 않는다."),
            "region": region,
            "series": sorted({p["comparison_series_id"] for p in points}),
            "events": geo_events(region),
            # 점 · 비교선 · 사건을 따로 둔다 — renderer가 셋을 섞지 않게
            "comparison_edges": comparison_edges(points),
            "bridge_dependency": bridge_dependency(points),
            "points": points,
        }
        (OUT / f"{region}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        built += 1
        ser = collections.Counter(p["comparison_series_id"] for p in points)
        print(f"  {region}: {len(points)}개 · series {dict(ser)}")
    if ambiguous:
        # 모호한 건 조용히 넘기지 않는다 — 어느 version인지 모르면 그 점의 의미가 없다
        print(f"\n✗ geography version이 모호한 점 {len(ambiguous)}건: {ambiguous[:5]}")
        return 1
    # stress fixture를 감으로 고르지 않는다 — 데이터가 있으니 밀도를 잰다.
    # 모델 fixture(한 특성만 검증)와 UI stress fixture(여러 lane·사건이 겹침)는 다르다.
    dens = []
    for f in sorted(OUT.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pts, evs = d["points"], d.get("events") or []
        hard = sum(1 for p in pts if (p.get("comparison") or {}).get("method")
                   in ("reaggregated", "context_only"))
        mixed = sum(1 for p in pts
                    if (p["lineage_composition"] or {}).get("mixed_share", 0) > 20)
        score = (len(d["series"]) * 3 + len(pts) * 0.1 + len(evs) * 5
                 + hard * 2 + mixed * 0.2)
        dens.append((round(score, 1), d["region"], len(d["series"]), len(pts),
                     len(evs), hard, mixed))
    dens.sort(reverse=True)
    print("\n[밀도] series·점·사건·재집계·mixed가 겹치는 정도")
    print(f"  {'점수':>6} {'지역':8} {'series':>6} {'점':>4} {'사건':>4} {'재집계':>5} {'mixed':>5}")
    for row in dens:
        print(f"  {row[0]:6} {row[1]:8} {row[2]:6} {row[3]:4} {row[4]:4} "
              f"{row[5]:5} {row[6]:5}")
    print(f"\n→ {OUT.name}/ {built}개 지역")
    return 0


if __name__ == "__main__":
    # 인자가 없으면 **이미 만들어 둔 지역 전부**를 다시 만든다. 기본 목록만 돌리면
    # 나머지가 옛 생성기 결과로 남아 regen_check가 못 잡는다.
    args = sys.argv[1:] or sorted(
        {f.stem for f in OUT.glob("*.json")}
        | {"하남", "부천", "군위", "이천", "종로"})
    sys.exit(main(args))
