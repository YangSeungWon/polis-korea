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
sys.path.insert(0, str(ROOT / "scripts/normalize"))
from reaggregate import SIDO_SHORT  # noqa: E402

RESULTS = ROOT / "data/results"
GEO = ROOT / "data/geo"
GEOG = ROOT / "data/geography"
AXES = ROOT / "data/parties/political_axes.json"
OUT = ROOT / "data/map_timelapse"

# 경계 파일이 가진 연도 스냅샷. **파일 연도 ≠ 행정 사건 날짜다** —
# 전환 시점은 events.json이 정하고, 이 목록은 그 시점에 쓸 그림을 고를 뿐이다.
BOUNDARY_YEARS = [1975, 1985, 1987, 1990, 1995, 2000, 2002, 2006, 2010, 2013, 2025, 2026]

# 대상 지역을 손으로 적지 않는다. **events.json이 아는 변화 지점 전부**가 대상이다 —
# 목록을 손으로 관리하면 새 사건을 넣고 여기 적는 걸 잊는 순간 조용히 빠진다.
#
# namespace는 섞지 않는다. 행정구역 지도와 선거구 지도는 다른 지도다 — 하남시갑은
# 하남시의 후신이 아니라 **선거구**이고, 같은 폴리곤 위에 겹쳐 그리면 두 ontology가
# 하나로 보인다. 그래서 연결 성분도 kind별로 따로 만든다.

# 짧은 시도명 → 결과 파일에 나오는 긴 이름들. 선거구 entity는 '경기', 결과는 '경기도'다.
# 강원·전북처럼 한 시도가 여러 표기를 갖는다 — 이름 하나로 맞추면 조용히 빠진다.
_SIDO_LONG: dict = collections.defaultdict(set)
for _long, _short in SIDO_SHORT.items():
    _SIDO_LONG[_short].add(_long)
    _SIDO_LONG[_long].add(_long)


def region_name(ent: dict) -> str:
    """지역 이름 — 연표(data/region_timeline)와 같은 문법으로 짓는다."""
    n = ent["name"]
    for suf in ("갑", "을", "병", "정", "무"):
        if n.endswith(suf) and len(n) > 2:
            n = n[:-1]
            break
    return n.removesuffix("(구)").removesuffix("시").removesuffix("군") or n


def auto_regions(geo: "Geo") -> dict:
    """events.json의 연결 성분 = 지도 타임랩스 대상. kind별로 따로 묶는다."""
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for ev in geo.events:
        ids = [x["id"] for x in (ev.get("from") or []) + (ev.get("to") or [])
               if x["id"] in geo.ents]
        for i in ids[1:]:
            union(ids[0], i)
    for c in geo.contains:                      # 포함관계도 같은 지역이다
        for ch in c["children"]:
            if c["parent"] in geo.ents and ch in geo.ents:
                union(c["parent"], ch)

    groups: dict = collections.defaultdict(set)
    for eid in list(parent):
        groups[find(eid)].add(eid)

    out: dict = {}
    for members in groups.values():
        kinds = {geo.ents[m]["kind"] for m in members}
        if len(kinds) != 1:                     # namespace가 섞인 성분은 만들지 않는다
            continue
        # 이름은 **가장 최근** 버전에서 딴다 — 없어진 이름으로 지역을 부르지 않는다.
        # 하위 단위(일반구)는 제외한다 — 포항을 '포항시북구'라고 부르면 안 된다.
        top = [m for m in members if not geo.ents[m].get("contained_in")] or list(members)
        newest = max(top, key=lambda m: (geo.ents[m].get("valid_from") or "",
                                         geo.ents[m]["id"]))
        name = region_name(geo.ents[newest])
        parents = {geo.ents[m].get("parent") or "" for m in members}
        out[name] = {
            "namespace": kinds.pop(),
            "entity_parents": parents,
            "sido": {x for p in parents for x in _SIDO_LONG.get(p, {p})},
            "members": set(members),
        }
    return dict(sorted(out.items()))

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
        self._rounds: list = []

    # entity ---------------------------------------------------------------
    def valid(self, eid: str, date: str) -> bool:
        e = self.ents.get(eid)
        if not e:
            return False
        f, t = e.get("valid_from") or "", e.get("valid_to") or "9999-12-31"
        return (not f or f <= date) and date < t

    def resolve(self, name: str, date: str, parents, kind: str = "admin_unit") -> dict:
        """(이름, 날짜) → entity id. 모호하면 id를 주지 않는다 — 추정하지 않는다.

        상위 행정구역은 **여럿일 수 있다**. 군위군은 2023년에 경상북도에서 대구광역시로
        옮겨갔고, 두 버전은 같은 지역의 다른 시점이다.
        """
        ps = {parents} if isinstance(parents, str) else set(parents)
        hit = [e for e in self.ents.values()
               if e["kind"] == kind and e["name"] == name
               and e.get("parent") in ps and self.valid(e["id"], date)]
        if len(hit) == 1:
            return {"id": hit[0]["id"], "resolution": "resolved"}
        if hit:
            return {"id": None, "resolution": "ambiguous",
                    "candidates": [e["id"] for e in hit]}
        return {"id": None, "resolution": "no_entity_recorded"}

    def family(self, spec: dict) -> set:
        """이 지역의 모든 시점 버전. 연결 성분이 이미 정했다."""
        return set(spec["members"])

    # 사건 -----------------------------------------------------------------
    def event_to(self, eid: str, after: str) -> dict | None:
        """`after` **이후에** eid를 만들어 낸 사건 — 그 전에는 from들이 있었다."""
        for ev in self.events:
            if eid in {x["id"] for x in ev.get("to") or []} and ev["effective_date"] > after:
                return ev
        return None

    def event_by_id_to(self, eid: str) -> dict | None:
        """이 entity를 만들어 낸 사건 (시점 무관)."""
        return next((e for e in self.events
                     if eid in {x["id"] for x in e.get("to") or []}), None)

    def event_by_id(self, eid: str) -> dict | None:
        return next((e for e in self.events if e["id"] == eid), None)

    def containment(self, eid: str, date: str) -> dict | None:
        for c in self.contains:
            if c["parent"] == eid and c["effective_date"] <= date and c.get("exhaustive"):
                return c
        return None

    # 경계 -----------------------------------------------------------------
    def boundary_year(self, date: str) -> int:
        y = int(date[:4])
        return max(x for x in BOUNDARY_YEARS if x <= y)

    def general_round(self, date: str) -> int:
        """그 시점에 유효한 **선거구 획정 회차**. 총선일에 이산 전환한다."""
        if not self._rounds:
            for f in RESULTS.glob("*-general-*.json"):
                n = f.stem.split("th-")[0].split("st-")[0].split("nd-")[0].split("rd-")[0]
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except Exception:                                # noqa: BLE001
                    continue
                dt = (d.get("_meta") or {}).get("election_date") or ""
                if dt and n.isdigit() and (GEO / f"district_{n}_geojson.json").exists():
                    self._rounds.append((dt, int(n)))
            self._rounds.sort()
        prev = [n for dt, n in self._rounds if dt <= date]
        return prev[-1] if prev else self._rounds[0][1]

    def boundary_key(self, spec: dict, date: str) -> str:
        return (f"district_{self.general_round(date)}"
                if spec["namespace"] == "electoral_district"
                else f"sigungu_{self.boundary_year(date)}")

    def features(self, key) -> list:
        """경계 파일 하나. 두 namespace가 키 이름도 속성 이름도 다르다."""
        key = key if isinstance(key, str) else f"sigungu_{key}"
        if key not in self._geo_cache:
            fp = GEO / (f"{key}_geojson.json" if key.startswith("district_")
                        else f"{key}.json")
            d = json.loads(fp.read_text(encoding="utf-8"))
            feats = d.get("features") or d
            for f in feats:
                pr = f["properties"]
                # 선거구 geojson은 SGG/SIDO를, 시군구는 name/code를 쓴다
                pr.setdefault("name", pr.get("SGG") or "")
                pr.setdefault("code", pr.get("SGG_Code") or "")
                pr.setdefault("parent", pr.get("SIDO") or "")
            self._geo_cache[key] = feats
        return self._geo_cache[key]


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


def footprint(geo: Geo, eid: str, at: str) -> tuple:
    """eid가 `at` 시점에 **어떤 단위들로 이뤄져 있었나**.

    사건을 거꾸로 걸어 올라간다. 포항시(1995~)를 1992년으로 되돌리면
    {포항시(구), 영일군}이 된다. 이름이 같은 다른 entity라 id로만 센다.

    되돌린 조상이 **여럿으로 갈라진** 것이면(분구) 그 조상의 표는 이 단위만의 것이
    아니다. 합치는 것과 쪼개는 것은 방향만 다른 게 아니라 **가능성이 다르다** —
    합은 그냥 더하면 되지만 쪼개기는 하위 실측이 없으면 성립하지 않는다.
    그래서 갈라지는 사건을 지나갔는지 따로 돌려준다.
    """
    cur, why, splits = {eid}, [], []
    for _ in range(8):
        nxt, changed = set(), False
        for x in cur:
            ev = geo.event_to(x, at)
            if ev and ev.get("territorial_continuity") in SUMMABLE:
                nxt |= {f["id"] for f in ev["from"]}
                why.append(ev["id"])
                if len(ev.get("to") or []) > 1:
                    splits.append(ev)
                changed = True
            else:
                nxt.add(x)
        cur = nxt
        if not changed:
            break
    return cur, why, splits


# ── 선거 층 ────────────────────────────────────────────────────────────────
def _races(doc: dict) -> list:
    return [r for r in (doc.get("district") or doc.get("races") or [])
            if isinstance(r, dict)]


def unit_of(race: dict) -> tuple:
    """결과 한 줄이 **어느 단위**의 집계인가. 행정구역과 선거구는 다른 namespace다."""
    scope = race.get("scope")
    if scope == "sigungu":
        return "admin_unit", race.get("sigungu") or ""
    if scope == "district_sigungu":
        # 총선 지역구 득표를 **시군구 단위로** 쪼개 놓은 실측(17대~). 선거구가 시군구를
        # 가로질러도 이건 그 시군구의 것이다. 한 시군구가 여러 선거구에 걸치면 여러 행이
        # 나오고, 그 합이 그 시군구 전체다 — 추정이 아니라 더하기다.
        return "admin_unit", race.get("sigungu") or ""
    if scope in ("district", None, ""):
        # 총선 결과는 scope='district' + `district` 키, 옛 파일은 `name` 키를 쓴다
        return "electoral_district", (race.get("district") or race.get("name") or "")
    return "other", race.get("sigungu") or race.get("sido") or ""


def snapshots(geo: Geo, spec: dict, fam: set) -> dict:
    """series → 날짜순 snapshot 목록. **series를 먼저 고르고** 섞지 않는다."""
    fam_names = {geo.ents[i]["name"] for i in fam}
    out: dict = collections.defaultdict(dict)
    seen: dict = {}
    # `.sigungu.json`을 빼면 안 된다. 16대 대선부터는 **시군구 집계가 거기에만 있다** —
    # 본 파일은 전국·시도 18줄뿐이다. 빼놓았더니 군위 대선 series가 통째로 사라졌다.
    # 대신 같은 (선거·series·단위)를 두 번 세지 않게 막는다.
    for f in sorted(RESULTS.glob("*.json")):
        if f.name.startswith(("local_", "national_assembly_", "presidential_")):
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
            if (race.get("sido") or "") not in spec["sido"]:
                continue
            ns, name = unit_of(race)
            if ns == "other" or not name:
                continue
            if not any(n in name or name in n for n in fam_names):
                continue
            cands = [c for c in (race.get("candidates") or []) if isinstance(c, dict)]
            if not cands:
                continue
            sid = series_id(kind, race)
            eid = meta.get("election_id") or f.stem
            key = (eid, sid, ns, name)
            # 같은 선거가 두 파일에 실린다(본 파일 / .sigungu). **먼저 준 파일만** 쓴다 —
            # 파일이 아니라 (선거·단위)로 막으면 한 시군구의 여러 선거구 행이 잘려 나간다.
            if seen.setdefault(key, f.name) != f.name:
                continue
            s = out[sid].setdefault(date, {
                "election_id": eid,
                "label": meta.get("election") or f.stem,
                "date": date, "comparison_series_id": sid, "units": []})
            hit = next((u for u in s["units"]
                        if u["unit_namespace"] == ns and u["name"] == name), None)
            if hit:
                # 한 시군구가 여러 선거구에 걸친다 — 그 시군구의 표는 이들의 합이다
                hit["candidates"] += cands
                hit["rows"] = hit.get("rows", 1) + 1
            else:
                s["units"].append({"unit_namespace": ns, "name": name,
                                   "candidates": cands})
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
def tokenize_district(name: str, vocab: set) -> tuple:
    """선거구명 → (구성 행정구역, 일부인가). 못 쪼개면 **None** — 추측해서 채우지 않는다.

    끝의 갑·을·병·정은 **그 자체가 정보다**: 이름에 든 행정구역을 여럿이 나눠 갖는다는
    뜻이라, 이 선거구는 그 구역 전체가 아니다. 22대 '동구군위군갑'을 군위군 폴리곤에
    칠하면 군위군이 통째로 갑에 들어간다고 주장하는 셈이 된다.
    """
    s = name
    if "(" in s and s.endswith(")"):
        s = s[s.index("(") + 1:-1]
    partial = False
    if len(s) > 2 and s[-1] in "갑을병정무":
        s, partial = s[:-1], True
    parts = [p.strip() for p in s.replace("・", "·").split("·") if p.strip()]
    out = []
    for p in parts:
        while p:
            hit = max((v for v in vocab if p.startswith(v)), key=len, default=None)
            if not hit:
                return None, partial
            out.append(hit)
            p = p[len(hit):].strip()
    return (out or None), partial


REAGG = ROOT / "data/reaggregated"


def _reagg_capability(target_name: str, parent: str) -> dict | None:
    """재집계 엔진이 이 선거구에 대해 이미 내린 판정. 여기서 새로 만들지 않는다."""
    for f in sorted(REAGG.glob("*__*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        v = (d.get("districts") or {}).get(f"{parent} {target_name}")
        if v:
            return {"pair": f.stem, **v}
    return None


def split_projection(geo: Geo, target: str, snap: dict, splits: list) -> dict:
    """분구 — **합산의 반대 방향은 그냥 나누기가 아니다**.

    이전 단위의 표를 면적·인구 비례로 쪼개는 것은 추정이지 재집계가 아니다. 하위
    단위(읍면동) 실측이 있어야 성립하고, 실측이 있어도 재집계 엔진이 `level` 추론을
    막았다면 **지도에는 칠할 수 없다**. 지도는 수준값을 칠하는 화면이기 때문이다.

    delta는 허용돼 있을 수 있다. 그건 다른 화면(비교 모드)의 몫이고, 여기서
    수준값 대신 슬쩍 쓰지 않는다.
    """
    ent = geo.ents[target]
    ev = splits[0]
    cap = _reagg_capability(ent["name"], ent.get("parent") or "")
    base = {"method": "unavailable", "split_event": ev["id"],
            "event_capability": ev.get("comparison_capability")}
    if not cap:
        return {**base, "reason": "split_without_subunit_measurement",
                "why": ("갈라지기 전 단위의 표를 이 경계로 나눌 하위 실측이 없다 — "
                        "면적·인구 비례 배분은 추정이지 재집계가 아니다")}
    inf = (cap.get("capability") or {}).get("inference_to_full_result") or {}
    dl = ((cap.get("capability") or {}).get("comparison") or {}).get("delta") or {}
    lvl = inf.get("level") or {}
    if not lvl.get("allowed"):
        # 재집계는 됐지만 수준값을 낼 수 없다. 지도는 수준값을 칠하는 화면이라 색이 없다.
        return {**base, "reason": "level_inference_not_allowed",
                "why": ("읍면동 실측으로 재집계는 되지만 전체 결과 수준값 추론이 "
                        f"막혀 있다({lvl.get('reason')}) — 지도는 수준값을 칠하므로 "
                        "이 경계에는 색을 주지 않는다"),
                "reaggregation": {
                    "pair": cap["pair"], "method": cap.get("method"),
                    "coverage": (cap.get("provenance") or {}).get("coverage"),
                    "measurement_scope": "attributable_only",
                    # 막힌 것과 열린 것을 같이 적는다 — 다른 화면이 쓸 수 있다
                    "delta_allowed": bool(dl.get("allowed")),
                    "delta_by_party": {k: v.get("allowed")
                                       for k, v in (dl.get("by_party") or {}).items()},
                }}
    return {"method": "reaggregated", "licensed_by": [ev["id"], cap["pair"]],
            "why": "하위 단위 실측으로 이 경계에 다시 담았다",
            "measurement_scope": "attributable_only"}


def resolve_projection(geo: Geo, target: str, at: str, snap: dict, spec: dict,
                       vocab: set) -> dict:
    """political_projection = resolve(election_snapshot, geography_at_date).

    **snapshot 단위 집합이 목표 footprint를 정확히 덮는가**만 본다. 덮으면 그 사건이
    이미 준 capability를 쓰고, 덮지 않으면 unavailable이다. 비율 배분은 없다.
    """
    fp, via, splits = footprint(geo, target, snap["date"])
    if splits:
        # 조상이 여럿으로 갈라졌다 — 그 조상의 표는 이 폴리곤만의 것이 아니다.
        # 판정은 재집계 엔진이 이미 했다. 여기서 다시 만들지 않는다.
        return split_projection(geo, target, snap, splits)
    if any(not geo.valid(x, snap["date"]) for x in fp):
        # 되짚기가 막힌 진짜 이유가 사건에 적혀 있으면 그걸 말한다.
        # 부천은 전신 전체가 후신에 들어오지 않아 `partial`이고, 그래서 합산이 성립하지
        # 않는다 — "entity가 유효하지 않다"보다 이쪽이 사실에 가깝다.
        blocker = next((geo.event_by_id_to(x) for x in sorted(fp)
                        if geo.event_by_id_to(x)), None)
        if blocker and blocker.get("territorial_continuity") not in SUMMABLE:
            return {"method": "unavailable",
                    "reason": "event_capability_blocks_projection",
                    "blocking_event": blocker["id"],
                    "event_capability": blocker.get("comparison_capability"),
                    "territorial_continuity": blocker.get("territorial_continuity"),
                    "why": blocker.get("capability_reason")
                    or "전신 전체가 후신에 들어오지 않아 단순 합산이 성립하지 않는다"}
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

    # snapshot 단위 → entity id.
    # 지도 namespace가 선거구면 집계 단위도 선거구 그대로다. 행정구역 지도일 때만
    # 선거구를 구성 행정구역으로 쪼갠다 — 두 ontology를 겹치지 않는다.
    ns, parent = spec["namespace"], spec["entity_parents"]
    src, foreign, unparsed, partial = {}, [], [], []
    for u in snap["units"]:
        if ns == "electoral_district":
            if u["unit_namespace"] != "electoral_district":
                continue
            names, kind = [u["name"]], "electoral_district"
        elif u["unit_namespace"] == "admin_unit":
            names, kind = [u["name"]], "admin_unit"
        else:
            names, part = tokenize_district(u["name"], vocab)
            kind = "admin_unit"
            if names is None:
                unparsed.append(u["name"])
                continue
            if part:
                # 갑·을로 나뉜 선거구다. 이름에 든 구역 전체가 아니다.
                partial.append({"unit": u["name"], "of": names})
                continue
        ids = [geo.resolve(n, snap["date"], parent, kind) for n in names]
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

    # **깨끗한 덮개가 있으면 그걸 쓴다.** 진단은 그다음이다.
    #
    # 순서를 뒤집으면 쓸 수 있는 자료를 두고 실패를 보고한다 — 22대 군위군은 선거구가
    # '동구군위군을'이라 밖으로 삐져나오지만, 같은 선거의 **시군구 단위 실측**이 따로
    # 있어서 그대로 칠할 수 있다. 그걸 먼저 보지 않으면 '표시 불가'가 나온다(실제로 나왔다).
    covered = set(src)
    if covered == fine and fine != fp:
        fp, via = fine, via + cvia          # 하위 단위로 남김없이 덮었다
    elif covered != fp:
        if foreign:
            return {"method": "unavailable",
                    "reason": "snapshot_unit_extends_beyond_target",
                    "detail": foreign,
                    "why": ("집계 단위가 이 경계 밖까지 포함한다 — 빼낼 하위 실측이 "
                            "없으면 합산도 분할도 성립하지 않는다")}
        if partial:
            return {"method": "unavailable", "reason": "snapshot_unit_is_partial",
                    "detail": partial,
                    "why": ("집계 단위가 이 구역의 일부(갑·을)다 — 전체 결과가 아니므로 "
                            "이 폴리곤에 칠할 수 없다")}
        if unparsed:
            return {"method": "unavailable", "reason": "district_composition_unparsed",
                    "detail": unparsed,
                    "why": "선거구가 어떤 행정구역으로 이뤄졌는지 기록이 없다"}
        return {"method": "unavailable", "reason": "incomplete_cover",
                "detail": {"expected": sorted(fp), "also_accepted": sorted(fine),
                           "covered": sorted(covered)},
                "why": "목표 경계를 이루는 단위 중 일부의 결과가 없다"}

    units = [u for lst in src.values() for u in lst]
    units = list({id(u): u for u in units}.values())
    caps = {e.get("comparison_capability") for e in
            (geo.event_by_id(x) for x in via) if e}
    if len(units) == 1 and set(src) == {target}:
        method, why = "direct", "경계가 그대로다"
    elif len(units) == 1 and caps == {"direct"}:
        # 이천군 → 이천시. 영역이 그대로고 이름·지위만 바뀌었다. 더한 게 없으므로
        # 합산이라고 부르면 안 된다 — 사건이 이미 `direct`라고 말했다.
        method = "direct"
        why = (f"영역이 그대로다 — 그때 이름은 '{geo.ents[list(src)[0]]['name']}'"
               f"이고 지금은 '{geo.ents[target]['name']}'이다")
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


# 지도 series에서 뺀다 — 재보궐은 같은 시점 전국을 덮지 않는다. 그 지역 한 곳만
# 색이 있고 나머지는 비는 지도가 되는데, 그건 '그 시점의 정치 지형'이 아니다.
SKIP_SERIES = {"byelection:unknown"}


def series_touches(geo: Geo, spec: dict, fam: set, snaps: list, vocab: set) -> bool:
    """이 series의 집계 단위가 이 지도의 entity와 **한 번이라도** 맞물리는가.

    투영이 성립하는지가 아니라 **애초에 같은 판인지**를 본다. '군위군선거구'(광역의원)는
    쪼개도 행정구역이 안 나오므로 행정구역 지도의 series가 아니고, '하남시제1선거구'는
    국회의원 선거구 지도의 단위가 아니다. 맞물리기는 하는데 못 칠하는 것(포항 총선)과
    아예 다른 판인 것은 다르다 — 앞은 남겨서 배우고, 뒤는 뺀다.
    """
    for sn in snaps:
        for u in sn["units"]:
            if spec["namespace"] == "electoral_district":
                if u["unit_namespace"] != "electoral_district":
                    continue
                names, kind = [u["name"]], "electoral_district"
            elif u["unit_namespace"] == "admin_unit":
                names, kind = [u["name"]], "admin_unit"
            else:
                names, _ = tokenize_district(u["name"], vocab)
                kind = "admin_unit"
                if not names:
                    continue
            if any(geo.resolve(n, sn["date"], spec["entity_parents"], kind)["id"] in fam
                   for n in names):
                return True
    return False


def series_order(sid: str) -> tuple:
    return (_ORDER.index(sid) if sid in _ORDER else len(_ORDER), sid)


def last_snapshot(snaps: list, date: str) -> dict | None:
    prev = [s for s in snaps if s["date"] <= date]
    return prev[-1] if prev else None


def geography_at_date(geo: Geo, spec: dict, fam: set, date: str) -> dict:
    """그 시점의 경계.

    경계 파일은 몇 해치 스냅샷뿐이라 모델이 아는 이름이 그림에 없을 수 있다.
    그때 셋을 구분한다 — **없는 그림을 지어내지 않고, 다른 땅을 갖다 쓰지도 않는다**:

        exact                       그 이름의 폴리곤이 그대로 있다
        predecessor_same_territory  파일 시점 이름으로는 있다. territorial_continuity가
                                    `same`(승격 등 영역 그대로)일 때만 이어 붙인다
        unavailable                 그릴 그림이 없다 — 폴리곤도 정치색도 내지 않는다

    1996년 이천시는 1995년 경계 파일에 '이천군'으로 있다. 같은 땅이고 지위만 바뀌었다는
    것을 events.json이 말해 주므로 이어 붙일 수 있다. 반대로 21대 부천시갑은 20대
    선거구 그림 어디에도 대응이 없다 — 그건 unavailable이다.
    """
    live = sorted(i for i in fam if geo.valid(i, date)
                  and not geo.ents[i].get("contained_in"))
    key = geo.boundary_key(spec, date)
    names = {geo.ents[i]["name"] for i in live}
    child_of = {geo.ents[c]["name"]: geo.ents[p]["name"]
                for cs in geo.contains for p in [cs["parent"]] for c in cs["children"]
                if p in geo.ents and c in geo.ents}
    # 이 파일이 그리는 시점 — 이름을 되짚을 때 기준이 된다
    vintage = f"{key.split('_')[1]}-12-31" if key.startswith("sigungu_") else date
    # 모델 이름 → 파일에서 찾을 이름. 영역이 그대로일 때만 옛 이름을 쓴다.
    alias, why_alias = {}, {}
    for i in live:
        nm = geo.ents[i]["name"]
        alias.setdefault(nm, nm)
        ev = geo.event_to(i, vintage)
        if ev and ev.get("territorial_continuity") == "same" and len(ev.get("from") or []) == 1:
            alias[nm] = ev["from"][0]["name"]
            why_alias[nm] = ev["id"]
    want = {v: k for k, v in alias.items()}          # 파일 이름 → 모델 이름

    feats, drawn = [], collections.defaultdict(list)
    for f in geo.features(key):
        pr = f["properties"]
        n = pr.get("name") or ""
        model = want.get(n) or (child_of.get(n) if child_of.get(n) in names else None)
        if model not in names:
            continue
        if pr.get("parent") and pr["parent"] not in spec["entity_parents"]:
            continue                      # 동명이 있다 — 시도까지 봐야 한다
        drawn[model].append(n)
        feats.append({"model_unit": model, "boundary_name": n,
                      "code": pr.get("code"),
                      "area_km2_approx": area_km2(f["geometry"]),
                      "geometry": f["geometry"]})
    missing = sorted(names - set(drawn))
    areas: dict = collections.defaultdict(float)
    for f in feats:
        areas[f["model_unit"]] += f["area_km2_approx"]
    res = ("unavailable" if missing else
           "predecessor_same_territory" if why_alias else "exact")
    return {
        "boundary_source": key,
        "boundary_resolution": res,
        "boundary_missing_units": missing or None,
        "boundary_alias": {k: v for k, v in alias.items() if k != v} or None,
        "boundary_alias_licensed_by": why_alias or None,
        "entity_version_ids": live,
        "units": sorted(names),
        # 그림이 모델보다 잘게 나온 것은 행정 사건이 아니라 자료 해상도 차이다
        "boundary_granularity": {k: v for k, v in drawn.items() if len(v) > 1} or None,
        "topology_signature": "|".join(sorted(names)),
        # 면적은 근사다(구멍 있는 폴리곤은 과대). 절대값이 아니라 **사건 전후 보존**을 본다.
        "area_km2_approx": {k: round(v, 1) for k, v in sorted(areas.items())},
        "features": feats,
        # 그린 폴리곤이 전부 이 시점의 유효한 모델 단위인가 — 이게 깨지면 빌드를 세운다
        "drawn_units_valid": set(drawn) <= names,
    }


def pivot_event(geo: Geo, spec: dict, fam: set) -> dict | None:
    """여섯 상태의 기준이 되는 사건. **영역이 그대로인 사건도 사건이다** —
    이천군→이천시는 폴리곤이 바뀌지 않는 게 맞다(`territorial_continuity: same`).
    그걸 모르면 '경계가 바뀌어야 한다'고 잘못 검사하게 된다."""
    evs = sorted((e for e in geo.events
                  if e.get("kind") == spec["namespace"]
                  and {x["id"] for x in (e.get("from") or []) + (e.get("to") or [])} & fam),
                 key=lambda e: e["effective_date"])
    if not evs:
        return None
    e = evs[-1]
    return {"event_id": e["id"], "type": e.get("type"),
            "effective_date": e["effective_date"], "label": e.get("label"),
            "territorial_continuity": e.get("territorial_continuity"),
            "comparison_capability": e.get("comparison_capability"),
            # 영역이 그대로면 폴리곤도 그대로여야 한다
            "expect_topology_change": e.get("territorial_continuity") != "same"}


def states_for(geo: Geo, spec: dict, fam: set, sid: str, snaps: list,
               vocab: set) -> list:
    """다섯 상태 — 선거 직전 / 선거 / 사건 직전 / 사건 직후 / 다음 선거."""
    evs = sorted((e for e in geo.events
                  if e.get("kind") == spec["namespace"]
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
    # 여섯째 상태 — **경계는 새것, 결과는 그 이전**.
    #
    # 선거구는 획정이 선거일에 발효돼서 '사건 직후'가 곧 새 선거다. 그래서 다섯 상태
    # 만으로는 분구의 투영 가능성이 한 번도 시험되지 않는다(하남이 전부 direct로 나왔다).
    # 이 조합에서만 "이전 결과를 새 경계로 볼 수 있는가"가 드러난다 — 설계 문서가
    # 말한 비교 모드가 이것이다. 기본 보기가 아니라 별도 상태로 둔다.
    plan = [
        ("before_election", _shift(e0["date"], -1), "선거 직전", None),
        ("election", e0["date"], "선거 시점", None),
        ("before_geo_event", _shift(ed, -1), "경계 사건 직전", None),
        ("after_geo_event", ed, "경계 사건 직후", None),
        ("previous_on_new_boundary", ed, "새 경계 · 이전 선거 결과", e0),
        ("next_election", e1["date"], "다음 선거", None),
    ]
    out = []
    for role, date, label, forced in plan:
        g = geography_at_date(geo, spec, fam, date)
        snap = forced or last_snapshot(snaps, date)
        proj = {"per_unit": {}, "summary": {}, "paintable_units": []}
        if g["boundary_resolution"] == "unavailable":
            # 그릴 그림이 없으면 투영도 없다. 없는 경계에 색을 상상하지 않는다.
            proj["boundary_blocked"] = g["boundary_missing_units"]
        elif snap:
            for eid in g["entity_version_ids"]:
                r = resolve_projection(geo, eid, date, snap, spec, vocab)
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


def boundary_label(g: dict) -> str:
    src = g["boundary_source"]
    return (f"{src.split('_')[1]}대 선거구 경계" if src.startswith("district_")
            else f"{src.split('_')[1]}년 경계")


def claim(snap: dict | None, g: dict, proj: dict) -> str:
    """화면이 말해도 되는 문장. 투영 방법이 문장을 정한다 — 반대가 아니다."""
    if g["boundary_resolution"] == "unavailable":
        # 막힌 이유를 **가장 앞의 것**으로 말한다. 경계 그림이 없으면 선거 기록 얘기를
        # 꺼낼 차례가 아니다.
        return ("이 시점 경계 그림이 없습니다 — "
                + " · ".join(g["boundary_missing_units"]))
    if not snap:
        return "이 시점 이전에 이 series의 선거 기록이 없습니다"
    ms = set(proj["summary"])
    when = snap["label"]
    if ms == {"direct"}:
        return f"{when} 결과 · 당시 경계"
    if ms <= {"direct", "aggregated"}:
        return f"{when} 결과 · {boundary_label(g)}에 합산"
    if ms <= {"direct", "reaggregated"}:
        return f"{when} 결과 · 읍면동 실측으로 이 경계에 재집계"
    if ms == {"unavailable"}:
        rs = {p.get("reason") for p in proj["per_unit"].values()}
        if rs == {"level_inference_not_allowed"}:
            # 막힌 것만 말하고 끝내지 않는다. 무엇이 가능한지는 모델이 이미 알고 있다.
            dl = any((p.get("reaggregation") or {}).get("delta_allowed")
                     for p in proj["per_unit"].values())
            return (f"{when} 결과 · 이 경계 기준 수준값은 낼 수 없습니다"
                    + (" (정당별 변화량은 별도 비교에서 가능)" if dl else ""))
        return f"{when} 결과는 이 경계로 표시할 수 없습니다"
    return f"{when} 결과 · 일부 경계만 표시 가능"


def main(regions: list[str]) -> int:
    geo = Geo()
    auto = auto_regions(geo)
    OUT.mkdir(parents=True, exist_ok=True)
    rc = 0
    skipped = []
    for region in (regions or sorted(auto)):
        spec = auto.get(region)
        if not spec:
            print(f"  {region}: events.json에 이 지역의 변화 사건이 없다")
            rc = 1
            continue
        fam = geo.family(spec)
        snaps = snapshots(geo, spec, fam)
        # 선거구명을 행정구역으로 쪼갤 때 쓰는 어휘.
        vocab = ({f["properties"]["name"] for y in BOUNDARY_YEARS
                  for f in geo.features(y)} | {geo.ents[i]["name"] for i in fam})
        blocks, excluded = [], []
        for sid in sorted((k for k in snaps if k not in SKIP_SERIES),
                          key=series_order):
            # **이 지도의 단위와 한 번도 맞물리지 않는 series는 이 지도의 series가 아니다.**
            #
            # 행정구역 지도에는 선거구 결과를 올려 볼 수 있다 — 선거구가 그 시군을 정확히
            # 덮으면 성립하고, 아니면 unavailable로 그 사실을 배운다(포항 총선이 그렇다).
            # 반대는 안 된다. 시군구 결과나 지방의원 선거구('하남시제1선거구')를 국회의원
            # 선거구 폴리곤에 올리려면 하위 실측이 있어야 하는데 없다.
            #
            # 그런 series는 6칸 전부 '표시 불가'인 블록이 될 뿐이라 아예 뺀다. 다만
            # **왜 없는지는 남긴다** — 조용히 사라지면 자료가 없는 것처럼 보인다.
            if not series_touches(geo, spec, fam, snaps[sid], vocab):
                excluded.append({"comparison_series_id": sid,
                                 "reason": "units_never_resolve_to_this_map",
                                 "example_units": sorted({u["name"] for sn in snaps[sid]
                                                          for u in sn["units"]})[:4],
                                 "why": ("집계 단위가 이 지도의 경계 단위와 맞물리지 "
                                         "않는다 — 올리려면 하위 실측이 필요하다")})
                continue
            st = states_for(geo, spec, fam, sid, snaps[sid], vocab)
            if not st:
                continue
            blocks.append({"comparison_series_id": sid, "states": st,
                           "n_snapshots": len(snaps[sid]),
                           # 어떤 사건을 기준으로 여섯 상태를 잡았는지 — 화면과 검사가
                           # '경계가 바뀌어야 하는가'를 이걸 보고 판단한다
                           "pivot_event": pivot_event(geo, spec, fam)})
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
            "region": region, "namespace": spec["namespace"],
            # 뺀 series를 조용히 사라지게 하지 않는다 — 왜 없는지가 정보다
            "excluded_series": excluded,
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
               if not s["geography_at_date"]["drawn_units_valid"]]
        if bad:
            # 그린 폴리곤이 모델 단위가 아니면 **다른 땅을 그 이름으로 칠한 것**이다
            print(f"✗ 모델에 없는 폴리곤을 그렸다 {len(bad)}: {bad[:3]}")
            rc = 1
        nb = [s["state_id"] for b in blocks for s in b["states"]
              if s["geography_at_date"]["boundary_resolution"] == "unavailable"]
        if nb:
            # 실패는 아니지만 조용히 넘기지도 않는다 — 경계 자료가 없는 시점이다
            skipped.append((region, len(nb), nb[0]))
    live = {f"{r}.json" for r in (regions or sorted(auto))}
    for f in OUT.glob("*.json"):
        if f.name not in live:
            # 지역 이름 규칙이 바뀌면 옛 파일이 남는다. 남으면 렌더러가 그걸 계속 그린다.
            f.unlink()
            print(f"  (지운 옛 산출물) {f.name}")
    if skipped:
        print("\n[경계 그림 없음] 모델은 아는데 그 시점 경계 파일이 없다 "
              "— 폴리곤도 정치색도 내지 않는다")
        for r, n, ex in skipped:
            print(f"  {r:10} {n}개 상태  예: {ex}")
    print(f"\n→ {OUT.name}/")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
