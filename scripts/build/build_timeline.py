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

# 새 schema 파일 path (Nth-{kind}-YYYY.json) 우선, 옛 schema fallback.
NEW_PATHS = {
    # presidential
    (13, "presidential"): None,
    (14, "presidential"): None,
    (15, "presidential"): None,
    (16, "presidential"): "16th-pres-2002.json",
    (17, "presidential"): "17th-pres-2007.json",
    (18, "presidential"): "18th-pres-2012.json",
    (19, "presidential"): "19th-pres-2017.json",
    (20, "presidential"): "20th-pres-2022.json",
    (21, "presidential"): "21st-pres-2025.json",
    # national_assembly
    (13, "national_assembly"): None,
    (14, "national_assembly"): None,
    (15, "national_assembly"): None,
    (16, "national_assembly"): None,
    (17, "national_assembly"): "17th-general-2004.json",
    (18, "national_assembly"): "18th-general-2008.json",
    (19, "national_assembly"): "19th-general-2012.json",
    (20, "national_assembly"): "20th-general-2016.json",
    (21, "national_assembly"): "21st-general-2020.json",
    (22, "national_assembly"): "22nd-general-2024.json",
    # local
    (5, "local"): "5th-local-2010.json",
    (6, "local"): "6th-local-2014.json",
    (7, "local"): "7th-local-2018.json",
    (8, "local"): "8th-local-2022.json",
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


# 위성정당 → 본정당 매핑 (총선 비례·지역구 합산용)
SATELLITE_TO_MAIN = {
    '국민의미래': '국민의힘',
    '더불어민주연합': '더불어민주당',
    '미래한국당': '미래통합당',
    '더불어시민당': '더불어민주당',
    '열린민주당': '더불어민주당',  # 21대 위성성
}


def party_total_seats(races, kind, n):
    """총선 회차의 정당별 총 의석 (지역구 + 비례, 위성정당 → 본정당 합산)."""
    if kind != "national_assembly":
        return []
    from collections import Counter
    counter = Counter()
    # 지역구 race(scope=district, tc=2)에서 winner 카운트
    for r in races:
        if r.get("scope") != "district" or r.get("sg_typecode") != "2":
            continue
        cands = r.get("candidates") or []
        won = next((c for c in cands if c.get("rank") == 1 or c.get("won")), None) or (cands[0] if cands else None)
        if won:
            p = SATELLITE_TO_MAIN.get(won.get("party", ""), won.get("party", ""))
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
            if path_name:
                p = RESULTS / path_name
                if p.exists():
                    raw = json.loads(p.read_text(encoding="utf-8"))
                    races = raw.get("races", [])
                    sido_winners = sido_winners_from_new_schema(races, kind)
                    party_seats = party_total_seats(races, kind, n)
                    pres_cands = pres_candidates_top(races) if kind == "presidential" else []
            label_short = KIND_LABEL[kind]
            entry = {
                "kind": kind,
                "n": n,
                "date": e.get("date", ""),
                "label": f"{n}대 {label_short}",
                "winner": e.get("winner"),
                "winner_party": e.get("winner_party"),
                "turnout": e.get("turnout"),
                "sidoWinners": sido_winners,
            }
            if party_seats:
                entry["partySeats"] = party_seats
            if pres_cands:
                entry["presCandidates"] = pres_cands
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
                "label": f"{n}대 {KIND_LABEL[kind]}",
                "winner": None, "winner_party": None, "turnout": None,
                "sidoWinners": {},
                "upcoming": True,
            })
    except Exception:
        pass

    # 주기 기반 예측 — 대선 5년, 총선 4년, 지선 4년. 마지막 회차 + 주기.
    CYCLE = {"presidential": 5, "national_assembly": 4, "local": 4}
    HORIZON_YEARS = 10  # 오늘부터 10년 앞까지
    from datetime import date as _date
    today = _date(2026, 6, 3)  # 빌드 시점 기준 (사이트 currentDate)
    horizon = today.replace(year=today.year + HORIZON_YEARS)
    for kind, cycle in CYCLE.items():
        kdata = elections.get(kind, {})
        elist = kdata.get("elections", [])
        if not elist:
            continue
        last = elist[-1]
        last_n = last["n"]
        last_date = last.get("date", "")
        if not last_date:
            continue
        y, m, d = map(int, last_date.split("-"))
        cur_n = last_n
        cur_date = _date(y, m, d)
        while True:
            cur_n += 1
            cur_date = cur_date.replace(year=cur_date.year + cycle)
            if cur_date > horizon:
                break
            # 이미 추가된 회차 있는지 (active와 중복)
            if any(r["kind"] == kind and r["n"] == cur_n for r in out_rounds + future):
                continue
            future.append({
                "kind": kind,
                "n": cur_n,
                "date": cur_date.isoformat(),
                "label": f"{cur_n}대 {KIND_LABEL[kind]}",
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
