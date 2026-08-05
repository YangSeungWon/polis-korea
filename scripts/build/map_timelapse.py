"""지도 타임랩스 — **snapshot이 있다 ≠ 지금 polygon에 칠할 수 있다**.

세 층을 끝까지 분리한다.

    geography_at_date       그 시점의 실제 경계 (사건 날짜에 이산 전환)
    election_snapshot       고른 series의 선거 시점 결과
    political_projection  = resolve(election_snapshot, geography_at_date)

셋째가 이 파일의 전부다. 결과는 넷 중 하나다:

    direct        경계가 그대로다 — 그냥 칠한다
    aggregated    이전 여러 단위의 표를 **실제로 더해** 현재 footprint에 투영한다
    reaggregated  하위 단위 실측으로 다시 담는다 (capability가 허용한 것만)
    unavailable   칠할 수 없다 — polygon은 그리되 정치색을 만들지 않는다

## 판정을 여기서 새로 만들지 않는다

합산이 성립하는지는 events.json의 `comparison_capability`와 containment.json의
`exhaustive`가 이미 말한다. 이 파일은 **snapshot 단위 집합이 목표 footprint를 정확히
덮는가**만 기계적으로 확인하고, 덮으면 그 사건이 준 capability를 그대로 쓴다.
덮지 않으면 `unavailable`이다. 비율 배분은 하지 않는다.

## 이름이 아니라 id로 센다

1992년의 '포항시'와 1997년의 '포항시'는 **다른 entity**다. 이름으로 맞추면 도농통합이
없었던 것이 된다. 그래서 snapshot 단위도 (이름, 날짜) → entity id로 먼저 해소한다.

사용: python scripts/build/map_timelapse.py [지역 ...]
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/build"))
from party_canon import disambiguate_party  # noqa: E402
from region_timeline import composition, kind_of, series_id  # noqa: E402

RESULTS = ROOT / "data/results"
GEO = ROOT / "data/geo"
GEOG = ROOT / "data/geography"
AXES = ROOT / "data/parties/political_axes.json"
OUT = ROOT / "data/map_timelapse"

# 경계 파일이 가진 연도 스냅샷. **파일 연도 ≠ 행정 사건 날짜다** —
# 전환 시점은 events.json이 정하고, 이 목록은 그 시점에 쓸 그림을 고를 뿐이다.
BOUNDARY_YEARS = [1975, 1985, 1987, 1990, 1995, 2000, 2002, 2006, 2010, 2013, 2025, 2026]

# 첫 slice. seed에서 events/containment를 따라 entity 가족을 넓힌다.
REGIONS = {
    "포항": {"sido": "경상북도", "seed": ["포항시", "영일군"],
             "current": "admin_unit:경상북도:포항시"},
}

# 합산을 허용하는 territorial continuity. partial은 합산이 성립하지 않는다.
SUMMABLE = {"same", "same_total"}


# ── 지리 층 ────────────────────────────────────────────────────────────────
def _load(p: Path, key: str) -> list:
    return json.loads(p.read_text(encoding="utf-8"))[key] if p.exists() else []


class Geo:
    """entity·사건·포함관계·경계 파일을 한 곳에서 본다."""

    def __init__(self) -> None:
        self.ents = {e["id"]: e for e in _load(GEOG / "entities.json", "entities")}
        self.events = _load(GEOG / "events.json", "events")
        self.contains = _load(GEOG / "containment.json", "containments")
        self._geo_cache: dict = {}

    # entity ---------------------------------------------------------------
    def valid(self, eid: str, date: str) -> bool:
        e = self.ents.get(eid)
        if not e:
            return False
        f, t = e.get("valid_from") or "", e.get("valid_to") or "9999-12-31"
        return (not f or f <= date) and date < t

    def resolve(self, name: str, date: str, sido: str) -> dict:
        """(이름, 날짜) → entity id. 모호하면 id를 주지 않는다 — 추정하지 않는다."""
        hit = [e for e in self.ents.values()
               if e["kind"] == "admin_unit" and e["name"] == name
               and e.get("parent") == sido and self.valid(e["id"], date)]
        if len(hit) == 1:
            return {"id": hit[0]["id"], "resolution": "resolved"}
        if hit:
            return {"id": None, "resolution": "ambiguous",
                    "candidates": [e["id"] for e in hit]}
        return {"id": None, "resolution": "no_entity_recorded"}

    def family(self, spec: dict) -> set:
        """seed에서 사건·포함관계를 따라 닫은 entity 집합. 이 지역의 모든 시점 버전."""
        fam = {e["id"] for e in self.ents.values()
               if e["kind"] == "admin_unit" and e.get("parent") == spec["sido"]
               and any(s in e["name"] for s in spec["seed"])}
        for _ in range(6):
            grow = set(fam)
            for ev in self.events:
                ids = {x["id"] for x in (ev.get("from") or []) + (ev.get("to") or [])}
                if ids & fam:
                    grow |= {i for i in ids if i in self.ents}
            for c in self.contains:
                if {c["parent"], *c["children"]} & fam:
                    grow |= {c["parent"], *c["children"]}
            if grow == fam:
                break
            fam = grow
        return fam

    # 사건 -----------------------------------------------------------------
    def event_to(self, eid: str, after: str) -> dict | None:
        """`after` **이후에** eid를 만들어 낸 사건 — 그 전에는 from들이 있었다."""
        for ev in self.events:
            if ev.get("kind") != "admin_unit":
                continue
            if eid in {x["id"] for x in ev.get("to") or []} and ev["effective_date"] > after:
                return ev
        return None

    def containment(self, eid: str, date: str) -> dict | None:
        for c in self.contains:
            if c["parent"] == eid and c["effective_date"] <= date and c.get("exhaustive"):
                return c
        return None

    # 경계 -----------------------------------------------------------------
    def boundary_year(self, date: str) -> int:
        y = int(date[:4])
        return max(x for x in BOUNDARY_YEARS if x <= y)

    def features(self, year: int) -> list:
        if year not in self._geo_cache:
            d = json.loads((GEO / f"sigungu_{year}.json").read_text(encoding="utf-8"))
            self._geo_cache[year] = d.get("features") or d
        return self._geo_cache[year]


def _rings(g: dict) -> list:
    t, c = g["type"], g["coordinates"]
    if t == "Polygon":
        return c
    if t == "MultiPolygon":
        return [r for poly in c for r in poly]
    return []


def area_km2(g: dict) -> float:
    """대략 면적. **경계가 진짜로 바뀌었는지** 재는 용도다 — 이름만 갈아 끼우면
    같은 폴리곤이 새 entity 행세를 할 수 있는데, 면적은 그걸 잡아낸다."""
    import math as _m
    tot = 0.0
    for ring in _rings(g):
        lat = sum(y for _, y in ring) / len(ring)
        k = _m.cos(_m.radians(lat)) * 111.32
        s = sum(ring[i][0] * ring[i - 1][1] - ring[i - 1][0] * ring[i][1]
                for i in range(len(ring)))
        tot += abs(s) / 2 * k * 110.57
    return round(tot, 1)


def footprint(geo: Geo, eid: str, at: str) -> set:
    """eid가 `at` 시점에 **어떤 단위들로 이뤄져 있었나**.

    사건을 거꾸로 걸어 올라간다. 포항시(1995~)를 1992년으로 되돌리면
    {포항시(구), 영일군}이 된다. 이름이 같은 다른 entity라 id로만 센다.
    """
    cur, why = {eid}, []
    for _ in range(8):
        nxt, changed = set(), False
        for x in cur:
            ev = geo.event_to(x, at)
            if ev and ev.get("territorial_continuity") in SUMMABLE:
                nxt |= {f["id"] for f in ev["from"]}
                why.append(ev["id"])
                changed = True
            else:
                nxt.add(x)
        cur = nxt
        if not changed:
            break
    return cur, why


# ── 선거 층 ────────────────────────────────────────────────────────────────
def _races(doc: dict) -> list:
    return [r for r in (doc.get("district") or doc.get("races") or [])
            if isinstance(r, dict)]


def unit_of(race: dict) -> tuple:
    """결과 한 줄이 **어느 단위**의 집계인가. 행정구역과 선거구는 다른 namespace다."""
    scope = race.get("scope")
    if scope == "sigungu":
        return "admin_unit", race.get("sigungu") or ""
    if scope in ("district", None, ""):
        # 총선 결과는 scope='district' + `district` 키, 옛 파일은 `name` 키를 쓴다
        return "electoral_district", (race.get("district") or race.get("name") or "")
    return "other", race.get("sigungu") or race.get("sido") or ""


def snapshots(geo: Geo, spec: dict, fam: set) -> dict:
    """series → 날짜순 snapshot 목록. **series를 먼저 고르고** 섞지 않는다."""
    fam_names = {geo.ents[i]["name"] for i in fam}
    out: dict = collections.defaultdict(dict)
    for f in sorted(RESULTS.glob("*.json")):
        if ".sigungu" in f.name or f.name.startswith(
                ("local_", "national_assembly_", "presidential_")):
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        meta = doc.get("_meta") or {}
        date = meta.get("election_date") or meta.get("date") or ""
        if not date:
            continue
        kind = kind_of(meta.get("election_id") or f.stem)
        for race in _races(doc):
            if (race.get("sido") or "") != spec["sido"]:
                continue
            ns, name = unit_of(race)
            if ns == "other" or not name:
                continue
            if not (any(n in name for n in fam_names) or any(s in name for s in spec["seed"])):
                continue
            cands = [c for c in (race.get("candidates") or []) if isinstance(c, dict)]
            if not cands:
                continue
            sid = series_id(kind, race)
            s = out[sid].setdefault(date, {
                "election_id": meta.get("election_id") or f.stem,
                "label": meta.get("election") or f.stem,
                "date": date, "comparison_series_id": sid, "units": []})
            s["units"].append({"unit_namespace": ns, "name": name, "candidates": cands})
    return {k: [v[d] for d in sorted(v)] for k, v in out.items()}


def tally(units: list) -> list:
    """후보(이름·정당) 단위로 합산. 표를 만들지 않고 **더하기만** 한다."""
    acc: dict = collections.OrderedDict()
    for u in units:
        for c in u["candidates"]:
            v = c.get("votes")
            if not isinstance(v, (int, float)):
                continue
            k = (c.get("name"), c.get("party"))
            acc[k] = acc.get(k, 0) + v
    tot = sum(acc.values()) or 1
    return sorted(({"name": n, "party": p, "votes": v,
                    "pct": round(v / tot * 100, 2)} for (n, p), v in acc.items()),
                  key=lambda c: -c["votes"])


_FAM: dict = {}
FAMILIES = ("conservative", "democratic", "progressive", "regional", "other")


def fam_axes() -> dict:
    """strict 계보. historical(강제해산 넘기)은 별도 모드지 기본값이 아니다."""
    if not _FAM:
        _FAM.update(json.loads(AXES.read_text(encoding="utf-8"))["lineage_family"])
    return _FAM


def paint_of(comp: dict) -> dict:
    """색 = **1위 계열**, 강도 = 그 비율. 합성색을 만들지 않는다.

    `mixed`는 계열이 아니라 상태다 — 고유 hue를 주면 '중도'로 오해된다.
    `unknown`·`independent`도 각각 다른 상태이고, 이기면 그대로 그 상태를 칠한다.
    """
    if not comp:
        return {"state": "no_data"}
    share = comp["share"]
    top = max(share, key=lambda k: share[k]) if share else None
    if top in FAMILIES:
        return {"state": "family", "family": top, "share": share[top],
                "coverage": comp["single_family_coverage"]}
    return {"state": top or "no_data", "share": share.get(top, 0),
            "note": {"mixed": "복수 계보 — 계열 hue를 주지 않는다",
                     "unknown": "계보 미확인",
                     "independent": "무소속 — 정당 계보로 추정하지 않는다"}.get(top)}


# ── 투영 층 ────────────────────────────────────────────────────────────────
def tokenize_district(name: str, vocab: set) -> list | None:
    """선거구명 → 구성 행정구역. 못 쪼개면 **None** — 추측해서 채우지 않는다."""
    s = name
    if "(" in s and s.endswith(")"):
        s = s[s.index("(") + 1:-1]
    parts = [p.strip() for p in s.replace("・", "·").split("·") if p.strip()]
    out = []
    for p in parts:
        while p:
            hit = max((v for v in vocab if p.startswith(v)), key=len, default=None)
            if not hit:
                return None
            out.append(hit)
            p = p[len(hit):].strip()
    return out or None


def resolve_projection(geo: Geo, target: str, at: str, snap: dict, sido: str,
                       vocab: set) -> dict:
    """political_projection = resolve(election_snapshot, geography_at_date).

    **snapshot 단위 집합이 목표 footprint를 정확히 덮는가**만 본다. 덮으면 그 사건이
    이미 준 capability를 쓰고, 덮지 않으면 unavailable이다. 비율 배분은 없다.
    """
    fp, via = footprint(geo, target, snap["date"])
    if any(not geo.valid(x, snap["date"]) for x in fp):
        return {"method": "unavailable", "reason": "footprint_entity_not_valid_at_snapshot",
                "detail": sorted(fp)}

    # 결과가 지도 단위보다 **잘게** 나온 경우(1997 대선은 포항시남구·북구로 집계됨).
    # 남김없이 나누는 포함관계일 때만 그 층까지 인정한다 — 일부만 아는 포함관계는 안 된다.
    fine, cvia = set(), []
    for x in fp:
        c = geo.containment(x, snap["date"])
        if c:
            fine |= set(c["children"])
            cvia.append(c["id"])
        else:
            fine.add(x)
    accept = fp | fine

    # snapshot 단위 → entity id (선거구는 구성 행정구역으로 먼저 쪼갠다)
    src, foreign, unparsed = {}, [], []
    for u in snap["units"]:
        if u["unit_namespace"] == "admin_unit":
            names = [u["name"]]
        else:
            names = tokenize_district(u["name"], vocab)
            if names is None:
                unparsed.append(u["name"])
                continue
        ids = [geo.resolve(n, snap["date"], sido) for n in names]
        if any(r["id"] is None for r in ids):
            # 이 지역 밖 단위(울릉군 등)는 entity가 없다 — 그래도 '남의 땅'인 건 확실하다
            outside = [n for n, r in zip(names, ids) if r["id"] is None]
            if any(r["id"] in accept for r in ids):
                foreign.append({"unit": u["name"], "outside": outside})
            continue
        idset = {r["id"] for r in ids}
        if not idset & accept:
            continue                      # 이 폴리곤과 무관한 단위
        if idset - accept:
            foreign.append({"unit": u["name"],
                            "outside": sorted(geo.ents[i]["name"] for i in idset - accept)})
            continue
        for i in idset:
            src.setdefault(i, []).append(u)

    if foreign:
        return {"method": "unavailable",
                "reason": "snapshot_unit_extends_beyond_target",
                "detail": foreign,
                "why": ("집계 단위가 이 경계 밖까지 포함한다 — 빼낼 하위 실측이 없으면 "
                        "합산도 분할도 성립하지 않는다")}
    if unparsed:
        return {"method": "unavailable", "reason": "district_composition_unparsed",
                "detail": unparsed,
                "why": "선거구가 어떤 행정구역으로 이뤄졌는지 기록이 없다"}

    covered = set(src)
    if covered == fine and fine != fp:
        fp, via = fine, via + cvia          # 하위 단위로 남김없이 덮었다
    elif covered != fp:
        return {"method": "unavailable", "reason": "incomplete_cover",
                "detail": {"expected": sorted(fp), "also_accepted": sorted(fine),
                           "covered": sorted(covered)},
                "why": "목표 경계를 이루는 단위 중 일부의 결과가 없다"}

    units = [u for lst in src.values() for u in lst]
    units = list({id(u): u for u in units}.values())
    if len(units) == 1 and set(src) == {target}:
        method, why = "direct", "경계가 그대로다"
    else:
        method = "aggregated"
        why = (f"{len(units)}개 단위의 표를 실제로 더해 이 경계에 투영했다 — "
               "비율 배분이 아니다")
    cands = tally(units)
    comp = composition(cands, snap["date"], fam_axes())
    win = max(cands, key=lambda c: c["votes"]) if cands else {}
    return {"method": method, "why": why, "licensed_by": via,
            "source_units": sorted(u["name"] for u in units),
            "candidates": cands,
            # 승자와 계열 구성은 다른 층이다 — winner_family를 지역 구성의 대리값으로 쓰지 않는다
            "winner": {"name": win.get("name"), "party": win.get("party"),
                       "pct": win.get("pct")},
            "lineage_composition": comp,
            "paint": paint_of(comp)}


# ── 상태 조립 ──────────────────────────────────────────────────────────────
# 기본 series는 **집계 단위가 지도 단위와 같은 것**부터. coverage가 높아서가 아니다 —
# 대선은 시군구로 집계돼 투영 층이 그대로 보이고, 총선은 선거구라 한 겹이 더 있다.
_ORDER = ["president:national", "local:municipal_mayor", "local:metro_mayor",
          "general:district"]


def series_order(sid: str) -> tuple:
    return (_ORDER.index(sid) if sid in _ORDER else len(_ORDER), sid)


def last_snapshot(snaps: list, date: str) -> dict | None:
    prev = [s for s in snaps if s["date"] <= date]
    return prev[-1] if prev else None


def geography_at_date(geo: Geo, spec: dict, fam: set, date: str) -> dict:
    """그 시점의 경계. 모델(entity)과 그림(경계 파일)이 어긋나면 **빌드를 세운다**."""
    live = sorted(i for i in fam if geo.valid(i, date)
                  and not geo.ents[i].get("contained_in"))
    year = geo.boundary_year(date)
    names = {geo.ents[i]["name"] for i in live}
    child_of = {geo.ents[c]["name"]: geo.ents[p]["name"]
                for cs in geo.contains for p in [cs["parent"]] for c in cs["children"]
                if p in geo.ents and c in geo.ents}
    feats, drawn = [], collections.defaultdict(list)
    for f in geo.features(year):
        n = f["properties"].get("name") or ""
        model = n if n in names else child_of.get(n)
        if model not in names:
            continue
        drawn[model].append(n)
        feats.append({"model_unit": model, "boundary_name": n,
                      "code": f["properties"].get("code"),
                      "area_km2_approx": area_km2(f["geometry"]),
                      "geometry": f["geometry"]})
    areas: dict = collections.defaultdict(float)
    for f in feats:
        areas[f["model_unit"]] += f["area_km2_approx"]
    return {
        "boundary_source": f"sigungu_{year}",
        "entity_version_ids": live,
        "units": sorted(names),
        # 그림이 모델보다 잘게 나온 것은 행정 사건이 아니라 자료 해상도 차이다
        "boundary_granularity": {k: v for k, v in drawn.items() if len(v) > 1} or None,
        "topology_signature": "|".join(sorted(names)),
        # 면적은 근사다(구멍 있는 폴리곤은 과대). 절대값이 아니라 **사건 전후 보존**을 본다.
        "area_km2_approx": {k: round(v, 1) for k, v in sorted(areas.items())},
        "features": feats,
        "model_matches_boundary": sorted(drawn) == sorted(names),
    }


def states_for(geo: Geo, spec: dict, fam: set, sid: str, snaps: list,
               vocab: set) -> list:
    """다섯 상태 — 선거 직전 / 선거 / 사건 직전 / 사건 직후 / 다음 선거."""
    evs = sorted((e for e in geo.events
                  if e.get("kind") == "admin_unit"
                  and {x["id"] for x in (e.get("from") or []) + (e.get("to") or [])} & fam),
                 key=lambda e: e["effective_date"])
    if not evs or not snaps:
        return []
    ev = evs[-1]
    ed = ev["effective_date"]
    before = [s for s in snaps if s["date"] < ed]
    after = [s for s in snaps if s["date"] >= ed]
    if not before or not after:
        return []
    e0, e1 = before[-1], after[0]
    plan = [
        ("before_election", _shift(e0["date"], -1), "선거 직전"),
        ("election", e0["date"], "선거 시점"),
        ("before_geo_event", _shift(ed, -1), "행정구역 사건 직전"),
        ("after_geo_event", ed, "행정구역 사건 직후"),
        ("next_election", e1["date"], "다음 선거"),
    ]
    out = []
    for role, date, label in plan:
        g = geography_at_date(geo, spec, fam, date)
        snap = last_snapshot(snaps, date)
        proj = {"per_unit": {}, "summary": {}, "paintable_units": []}
        if snap:
            for eid in g["entity_version_ids"]:
                r = resolve_projection(geo, eid, date, snap, spec["sido"], vocab)
                proj["per_unit"][geo.ents[eid]["name"]] = r
                if r["method"] != "unavailable":
                    proj["paintable_units"].append(geo.ents[eid]["name"])
            proj["summary"] = dict(collections.Counter(
                r["method"] for r in proj["per_unit"].values()))
        out.append({
            "state_id": f"{sid}@{date}#{role}",
            "role": role, "role_label": label, "date": date,
            "geography_at_date": g,
            "election_snapshot": ({k: v for k, v in snap.items() if k != "units"}
                                  | {"unit_names": [u["name"] for u in snap["units"]],
                                     "unit_namespaces": sorted(
                                         {u["unit_namespace"] for u in snap["units"]})}
                                  if snap else None),
            "political_projection": proj,
            "displayable_claim": claim(snap, g, proj),
        })
    return out


def _shift(date: str, days: int) -> str:
    from datetime import date as D, timedelta
    y, m, d = map(int, date.split("-"))
    return (D(y, m, d) + timedelta(days=days)).isoformat()


def claim(snap: dict | None, g: dict, proj: dict) -> str:
    """화면이 말해도 되는 문장. 투영 방법이 문장을 정한다 — 반대가 아니다."""
    if not snap:
        return "이 시점 이전에 이 series의 선거 기록이 없습니다"
    ms = set(proj["summary"])
    when = snap["label"]
    if ms == {"direct"}:
        return f"{when} 결과 · 당시 경계"
    if ms <= {"direct", "aggregated"}:
        return f"{when} 결과 · {g['boundary_source'][-4:]}년 경계에 합산"
    if ms == {"unavailable"}:
        return f"{when} 결과는 이 경계로 표시할 수 없습니다"
    return f"{when} 결과 · 일부 경계만 표시 가능"


def main(regions: list[str]) -> int:
    geo = Geo()
    OUT.mkdir(parents=True, exist_ok=True)
    rc = 0
    for region in regions:
        spec = REGIONS.get(region)
        if not spec:
            print(f"  {region}: REGIONS에 없음")
            rc = 1
            continue
        fam = geo.family(spec)
        snaps = snapshots(geo, spec, fam)
        vocab = {f["properties"]["name"] for y in BOUNDARY_YEARS
                 for f in geo.features(y)} | {geo.ents[i]["name"] for i in fam}
        blocks = []
        for sid in sorted(snaps, key=series_order):
            st = states_for(geo, spec, fam, sid, snaps[sid], vocab)
            if not st:
                continue
            blocks.append({"comparison_series_id": sid, "states": st,
                           "n_snapshots": len(snaps[sid])})
        doc = {
            "_note": ("지도 타임랩스 상태. geography_at_date · election_snapshot · "
                      "political_projection을 분리한다. **snapshot이 있다 ≠ 지금 "
                      "polygon에 칠할 수 있다** — 투영 판정은 events/containment가 이미 "
                      "준 capability를 쓰고 여기서 새로 만들지 않는다."),
            "_rules": {
                "series": "한 지도에서 series를 섞지 않는다",
                "interpolation": "선거 사이를 보간하지 않는다 — discrete snapshot만",
                "topology": "사건 effective date에서 이산 전환한다 — 형태 보간 없음",
                "unavailable": "polygon은 그리되 정치색을 만들지 않는다",
            },
            "region": region, "namespace": "admin_unit",
            "entity_family": sorted(fam),
            "series_blocks": blocks,
        }
        (OUT / f"{region}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for b in blocks:
            ms = collections.Counter(m for s in b["states"]
                                     for m in s["political_projection"]["summary"])
            print(f"  {region} {b['comparison_series_id']:22} 상태 {len(b['states'])} "
                  f"· {dict(ms)}")
        bad = [s["state_id"] for b in blocks for s in b["states"]
               if not s["geography_at_date"]["model_matches_boundary"]]
        if bad:
            print(f"✗ 모델과 경계 파일이 어긋난 상태 {len(bad)}: {bad[:3]}")
            rc = 1
    print(f"\n→ {OUT.name}/")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["포항"]))
