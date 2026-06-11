"""역대 선거 timeline 데이터 사전 가공.

모든 회차(대선·총선·지선)의 결과를 읽어 시도별 1위 정당을 추출,
client는 한 파일만 fetch하면 timeline 전체 시각화 가능.

산출: data/timeline.json
스키마:
  {
    "rounds": [
      {
        "kind": "presidential" | "national_assembly" | "local",
        "n": 13,
        "date": "1987-12-16",
        "label": "13대 대선",
        "winner": "노태우",
        "winner_party": "민주정의당",
        "turnout": 89.2,
        "sidoWinners": {
          "서울특별시": { "party": "민주정의당", "pct": 30.0 },
          ...
        }
      }
    ]
  }

사용:
  python3 scripts/build/build_timeline.py
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"

KIND_LABEL = {
    "presidential": "대선",
    "national_assembly": "총선",
    "local": "지선",
}
# 회차 단위 — 대선·총선은 사람·기관 연속성('대'), 지선은 반복 행사('회').
KIND_UNIT = {"presidential": "대", "national_assembly": "대", "local": "회"}

# 새 schema 파일 path (Nth-{kind}-YYYY.json) 우선, 옛 schema fallback.
NEW_PATHS = {
    # presidential — 1·8~12 간선(전국만), 2·3·5·6·7 직선(시도), 13~15 위키 nation, 16~ NEC
    (1, "presidential"): "1st-pres-1948.json",
    (2, "presidential"): "2nd-pres-1952.json",
    (3, "presidential"): "3rd-pres-1956.json",
    (5, "presidential"): "5th-pres-1963.json",
    (6, "presidential"): "6th-pres-1967.json",
    (7, "presidential"): "7th-pres-1971.json",
    (8, "presidential"): "8th-pres-1972.json",
    (9, "presidential"): "9th-pres-1978.json",
    (10, "presidential"): "10th-pres-1979.json",
    (11, "presidential"): "11th-pres-1980.json",
    (12, "presidential"): "12th-pres-1981.json",
    (13, "presidential"): "13th-pres-1987.json",
    (14, "presidential"): "14th-pres-1992.json",
    (15, "presidential"): "15th-pres-1997.json",
    (16, "presidential"): "16th-pres-2002.json",
    (17, "presidential"): "17th-pres-2007.json",
    (18, "presidential"): "18th-pres-2012.json",
    (19, "presidential"): "19th-pres-2017.json",
    (20, "presidential"): "20th-pres-2022.json",
    (21, "presidential"): "21st-pres-2025.json",
    # national_assembly — 9~12 중선거구(LOD 지역구), 13~16 위키 정당 합산, 17~ NEC + 지역구
    (9, "national_assembly"): "9th-general-1973.json",
    (10, "national_assembly"): "10th-general-1978.json",
    (11, "national_assembly"): "11th-general-1981.json",
    (12, "national_assembly"): "12th-general-1985.json",
    (13, "national_assembly"): "13th-general-1988.json",
    (14, "national_assembly"): "14th-general-1992.json",
    (15, "national_assembly"): "15th-general-1996.json",
    (16, "national_assembly"): "16th-general-2000.json",
    (17, "national_assembly"): "17th-general-2004.json",
    (18, "national_assembly"): "18th-general-2008.json",
    (19, "national_assembly"): "19th-general-2012.json",
    (20, "national_assembly"): "20th-general-2016.json",
    (21, "national_assembly"): "21st-general-2020.json",
    (22, "national_assembly"): "22nd-general-2024.json",
    # local — 1~4 위키, 5~ NEC
    (1, "local"): "1st-local-1995.json",
    (2, "local"): "2nd-local-1998.json",
    (3, "local"): "3rd-local-2002.json",
    (4, "local"): "4th-local-2006.json",
    (5, "local"): "5th-local-2010.json",
    (6, "local"): "6th-local-2014.json",
    (7, "local"): "7th-local-2018.json",
    (8, "local"): "8th-local-2022.json",
    (9, "local"): "9th-local-2026.json",
}


def canon_sido(s: str) -> str:
    return {"강원도": "강원특별자치도", "전라북도": "전북특별자치도", "제주도": "제주특별자치도"}.get(s, s)


def pres_candidates_top(races: list[dict]) -> list[dict]:
    """대선 회차의 nation race 후보 list (votes desc)."""
    nat = next((r for r in races if r.get("scope") == "nation" and r.get("sg_typecode") == "1"), None)
    if not nat:
        return []
    cands = list(nat.get("candidates") or [])
    cands.sort(key=lambda c: c.get("votes", 0) or 0, reverse=True)
    return [{
        "name": c.get("name"),
        "party": c.get("party"),
        "votes": c.get("votes", 0),
        "pct": c.get("pct", 0),
    } for c in cands]


def sido_winners_from_new_schema(races: list[dict], kind: str) -> dict:
    """새 schema races → 시도별 1위 정당.
    - presidential: scope=sido tc=1
    - national_assembly: 지역구 district 합산 → 시도별 의석 수 최다 정당
    - local: scope=sido tc=3 (광역단체장)
    """
    out = {}
    if kind == "presidential":
        for r in races:
            if r.get("scope") != "sido" or r.get("sg_typecode") != "1":
                continue
            sido = canon_sido(r.get("sido", ""))
            cands = r.get("candidates") or []
            if not cands:
                continue
            top = max(cands, key=lambda c: c.get("votes", 0) or 0)
            total = sum(c.get("votes", 0) or 0 for c in cands)
            pct = (top.get("votes", 0) / total * 100) if total else 0
            out[sido] = {"party": top.get("party", ""), "pct": round(pct, 1)}
    elif kind == "national_assembly":
        # 지역구 wins by sido — 정당별 의석 카운트 → 1위
        from collections import Counter
        sido_party_seats = {}
        for r in races:
            if r.get("scope") != "district" or r.get("sg_typecode") != "2":
                continue
            sido = canon_sido(r.get("sido", ""))
            cands = r.get("candidates") or []
            if not cands:
                continue
            won = next((c for c in cands if c.get("rank") == 1 or c.get("won")), None) or cands[0]
            party = won.get("party", "")
            d = sido_party_seats.setdefault(sido, Counter())
            d[party] += 1
        for sido, ctr in sido_party_seats.items():
            party, seats = ctr.most_common(1)[0]
            total = sum(ctr.values())
            pct = seats / total * 100 if total else 0
            out[sido] = {"party": party, "pct": round(pct, 1), "seats": seats, "total": total}
    elif kind == "local":
        for r in races:
            if r.get("scope") != "sido" or r.get("sg_typecode") != "3":
                continue
            sido = canon_sido(r.get("sido", ""))
            cands = r.get("candidates") or []
            if not cands:
                continue
            top = max(cands, key=lambda c: c.get("votes", 0) or 0)
            total = sum(c.get("votes", 0) or 0 for c in cands)
            pct = (top.get("votes", 0) / total * 100) if total else 0
            out[sido] = {"party": top.get("party", ""), "pct": round(pct, 1)}
    return out


# 위성정당 → 본정당 매핑 — data/parties/satellites.json 단일 출처.
# JS 측은 scripts/build/sync_satellites_js.py가 assets/parties.js에 sync.
SATELLITE_TO_MAIN = json.loads(
    (ROOT / "data/parties/satellites.json").read_text(encoding="utf-8")
)["satellite_to_main"]


def mayor_party_counts(races):
    """지선 기초단체장(tc=4) 정당별 당선 수."""
    return _count_winners_by_tc(races, "4")


def council_party_counts(races, tc):
    """지선 광역의원(tc=5)·기초의원(tc=6) 지역구 당선자 정당 카운트."""
    return _count_winners_by_tc(races, tc)


def proportional_party_counts(races, tc):
    """비례(tc=8 광역·tc=9 기초) — candidate.seats 합계 by party."""
    from collections import Counter
    ctr = Counter()
    for r in races:
        if r.get("sg_typecode") != tc:
            continue
        for c in r.get("candidates") or []:
            s = c.get("seats") or 0
            if s:
                ctr[c.get("party") or "무소속"] += s
    return [[p, c] for p, c in ctr.most_common()]


def _count_winners_by_tc(races, tc):
    # tc=4 (기초장) → scope=sigungu만 (sigungu_part는 시군구 내 구 breakdown)
    # tc=5/6 (의원 지역구) → scope=district winner count.
    # 위키 inject로 scope='sido_summary'/'sigungu_summary' 있으면 우선 (candidates[].seats 합산).
    SCOPE_FOR = {"4": "sigungu", "5": "district", "6": "district"}
    SUMMARY_FOR = {"5": "sido_summary", "6": "sigungu_summary"}
    want_scope = SCOPE_FOR.get(tc)
    summary_scope = SUMMARY_FOR.get(tc)
    from collections import Counter
    # 1차: summary scope 데이터 있으면 그쪽으로 — seats 합산
    if summary_scope and any(r.get("sg_typecode") == tc and r.get("scope") == summary_scope for r in races):
        ctr = Counter()
        for r in races:
            if r.get("sg_typecode") != tc or r.get("scope") != summary_scope:
                continue
            for c in r.get("candidates") or []:
                s = c.get("seats") or 0
                if s:
                    ctr[c.get("party") or "무소속"] += s
        return [[p, c] for p, c in ctr.most_common()]
    # 2차: winner count fallback
    ctr = Counter()
    for r in races:
        if r.get("sg_typecode") != tc:
            continue
        if want_scope and r.get("scope") != want_scope:
            continue
        cands = r.get("candidates") or []
        if not cands:
            continue
        won = [c for c in cands if c.get("won")]
        if won:
            # 중선거구(기초의원 지역구 tc=6 등) — 1선거구 다수 당선. won 전원이 의석.
            for c in won:
                ctr[c.get("party") or "무소속"] += 1
        else:
            # won 플래그 없는 옛 데이터 — 1선거구 1위만(단선거구 가정).
            top = max(cands, key=lambda c: c.get("votes", 0) or 0)
            ctr[top.get("party") or "무소속"] += 1
    return [[p, c] for p, c in ctr.most_common()]


def load_chunked(path: Path):
    """main + .sigungu.json chunk 합쳐 races 반환."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    races = list(raw.get("races") or [])
    if raw.get("_meta", {}).get("chunked"):
        sub = path.with_suffix("").with_suffix(".sigungu.json")
        if sub.exists():
            races += json.loads(sub.read_text(encoding="utf-8")).get("races") or []
    return raw, races


def compute_turnout(races, kind):
    """elections.json에 turnout 없는 회차용 — results race 합산으로 자동 계산.
    대선/지선 광역장: scope=sido tc=1 또는 3. 총선: scope=district tc=2.
    nation race 우선(있으면 더 정확 — 재외·관외 포함)."""
    SCOPE_TC = {
        "presidential": [("nation", "1"), ("sido", "1")],
        "national_assembly": [("nation", "2"), ("district", "2")],
        "local": [("sido", "3")],
    }
    for scope, tc in SCOPE_TC.get(kind, []):
        ts = [r for r in races if r.get("scope") == scope and r.get("sg_typecode") == tc]
        e = sum(r.get("electors", 0) or 0 for r in ts)
        v = sum(r.get("voters", 0) or 0 for r in ts)
        if e > 0 and v > 0:
            return round(v / e * 100, 2)
    return None


def party_total_seats(races, kind, n):
    """총선 회차의 정당별 총 의석 (지역구 + 비례, 위성정당 → 본정당 합산)."""
    if kind != "national_assembly":
        return []
    from collections import Counter
    counter = Counter()
    # 지역구 race(scope=district, tc=2)에서 winner 카운트 — 중선거구(9~12대 1구 2인)는 당선자 전원.
    for r in races:
        if r.get("scope") != "district" or r.get("sg_typecode") != "2":
            continue
        cands = r.get("candidates") or []
        won_list = [c for c in cands if c.get("won")]
        if not won_list and cands:
            won_list = [cands[0]]   # won 플래그 없는 옛 데이터 — 1위만(단선거구 가정)
        for c in won_list:
            p = SATELLITE_TO_MAIN.get(c.get("party", ""), c.get("party", ""))
            counter[p] += 1
    # 비례 의석은 옛 schema에서 (national_assembly_N.json)
    old_path = ROOT / f"data/results/national_assembly_{n}.json"
    if old_path.exists():
        try:
            old = json.loads(old_path.read_text(encoding="utf-8"))
            for ps in (old.get("national", {}).get("proportional_seats") or []):
                p = SATELLITE_TO_MAIN.get(ps.get("party", ""), ps.get("party", ""))
                counter[p] += ps.get("seats", 0)
        except Exception:
            pass
    return [[p, c] for p, c in counter.most_common()]


def main():
    elections = json.loads((ROOT / "data/elections.json").read_text(encoding="utf-8"))
    out_rounds = []
    for kind in ("presidential", "national_assembly", "local"):
        kdata = elections.get(kind, {})
        for e in kdata.get("elections", []):
            n = e["n"]
            path_name = NEW_PATHS.get((n, kind))
            sido_winners = {}
            party_seats = []
            pres_cands = []
            mayor_counts = []
            metro_council_counts = []
            local_council_counts = []
            metro_proportional_counts = []
            local_proportional_counts = []
            computed_turnout = None
            if path_name:
                p = RESULTS / path_name
                if p.exists():
                    raw, races = load_chunked(p)
                    sido_winners = sido_winners_from_new_schema(races, kind)
                    party_seats = party_total_seats(races, kind, n)
                    pres_cands = pres_candidates_top(races) if kind == "presidential" else []
                    if kind == "local":
                        mayor_counts = mayor_party_counts(races)
                        metro_council_counts = council_party_counts(races, "5")
                        local_council_counts = council_party_counts(races, "6")
                        metro_proportional_counts = proportional_party_counts(races, "8")
                        local_proportional_counts = proportional_party_counts(races, "9")
                    computed_turnout = compute_turnout(races, kind)
            label_short = KIND_LABEL[kind]
            entry = {
                "kind": kind,
                "n": n,
                "date": e.get("date", ""),
                "label": f"{n}{KIND_UNIT[kind]} {label_short}",
                "winner": e.get("winner"),
                "winner_party": e.get("winner_party"),
                "turnout": e.get("turnout") if e.get("turnout") not in (None, 0) else computed_turnout,
                "sidoWinners": sido_winners,
            }
            if e.get("indirect"):
                entry["indirect"] = True   # 간선(국회·통대·선거인단) — 직선 아님
            if party_seats:
                entry["partySeats"] = party_seats
            if pres_cands:
                entry["presCandidates"] = pres_cands
            if mayor_counts:
                entry["mayorPartyCounts"] = mayor_counts
            if metro_council_counts:
                entry["metroCouncilPartyCounts"] = metro_council_counts
            if local_council_counts:
                entry["localCouncilPartyCounts"] = local_council_counts
            if metro_proportional_counts:
                entry["metroProportionalPartyCounts"] = metro_proportional_counts
            if local_proportional_counts:
                entry["localProportionalPartyCounts"] = local_proportional_counts
            out_rounds.append(entry)

    # 향후 예정 선거 (data/elections/index.json active + 주기 기반 예측 ~10년).
    # 데이터 없는 상태로 추가 — UI에서 "예정" 표시.
    future = []
    # active 선거 (메타 파일 읽기)
    try:
        idx = json.loads((ROOT / "data/elections/index.json").read_text(encoding="utf-8"))
        for active_id in idx.get("active", []):
            meta_path = ROOT / f"data/elections/{active_id}.json"
            if not meta_path.exists():
                continue
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            kind = meta.get("type")
            if kind not in KIND_LABEL:
                continue
            # 이미 추가된 회차 있는지
            n = int(active_id.split("-")[0].rstrip("nrdsth"))
            if any(r["kind"] == kind and r["n"] == n for r in out_rounds):
                continue
            future.append({
                "kind": kind,
                "n": n,
                "date": meta.get("date", ""),
                "label": f"{n}{KIND_UNIT[kind]} {KIND_LABEL[kind]}",
                "winner": None, "winner_party": None, "turnout": None,
                "sidoWinners": {},
                "upcoming": True,
            })
    except Exception:
        pass

    # 주기 기반 예측 — 공직선거법 §34에 따라 임기만료일 N일 전 이후 첫 수요일.
    # 대선 70일·총선 50일·지선 30일. 마지막 회차의 임기만료일에서 시작.
    # 홈 타임라인 strip이 미래 위치 표시에 사용. 역대 list는 consumer에서 필터.
    from datetime import date as _date, timedelta as _td

    # (cycle_years, days_before_term_end_for_election)
    CYCLE_RULE = {
        "presidential": (5, 70),
        "national_assembly": (4, 50),
        "local": (4, 30),
    }
    # 마지막 회차의 임기만료일 — 다음 회차 추정 anchor.
    #   대선 21대(이재명, 2025-06-04 보궐 취임) → 2030-06-03 만료
    #   총선 22대 임기 2024-05-30~2028-05-29
    #   지선 9회 임기 2026-07-01~2030-06-30
    LAST_TERM_END = {
        "presidential": _date(2030, 6, 3),
        "national_assembly": _date(2028, 5, 29),
        "local": _date(2030, 6, 30),
    }
    HORIZON_YEARS = 10
    today = _date(2026, 6, 3)
    horizon = today.replace(year=today.year + HORIZON_YEARS)

    def first_wed_on_or_after(dt: _date) -> _date:
        return dt + _td(days=(2 - dt.weekday()) % 7)

    for kind, (cycle, before_days) in CYCLE_RULE.items():
        elist = elections.get(kind, {}).get("elections", [])
        if not elist:
            continue
        cur_n = elist[-1]["n"]
        cur_term_end = LAST_TERM_END.get(kind)
        if not cur_term_end:
            continue
        while True:
            cur_n += 1
            # 현재 회차 임기만료 기준 N일 전 첫 수요일 = 다음 회차 선거일
            elec_date = first_wed_on_or_after(cur_term_end - _td(days=before_days))
            if elec_date > horizon:
                break
            # 다음 사이클: 임기 만료 = (당선 후 임기 시작) + cycle년 − 1일
            # 단순화: 현 만료 + cycle년 (월·일 동일).
            cur_term_end = cur_term_end.replace(year=cur_term_end.year + cycle)
            if any(r["kind"] == kind and r["n"] == cur_n for r in out_rounds + future):
                continue
            future.append({
                "kind": kind,
                "n": cur_n,
                "date": elec_date.isoformat(),
                "label": f"{cur_n}{KIND_UNIT[kind]} {KIND_LABEL[kind]}",
                "winner": None, "winner_party": None, "turnout": None,
                "sidoWinners": {},
                "upcoming": True,
                "predicted": True,
            })

    out_rounds.extend(future)
    # 시간순 정렬
    out_rounds.sort(key=lambda r: r["date"])
    out = {"rounds": out_rounds}
    out_path = ROOT / "data/timeline.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {out_path.name}: {len(out_rounds)} rounds")
    # 통계
    has_sido = sum(1 for r in out_rounds if r["sidoWinners"])
    print(f"  sidoWinners 데이터 있음: {has_sido}/{len(out_rounds)}")


if __name__ == "__main__":
    main()
