"""전국(nation) race를 시도 합산으로 다시 세운다 — 출처가 갈린 회차 교정.

## 왜

옛 대선 몇 회차는 **nation과 sido의 출처가 다르다.** nation은 위키백과 infobox에서
왔고(주요 후보만 싣는다), sido는 선관위 개표현황(VCCP09)에서 왔다. 그래서 군소후보가
전국 집계에서만 사라진다.

실제로 13대 대선(1987)에서 **신정일(한주의통일한국당) 46,650표가 전국 race에만
없었다.** 시도 14곳에는 전부 있다. valid_votes도 그만큼 적게 적혀 있었다.

nation은 sido의 합이어야 한다 — 그건 유도지 추정이 아니다. 두 출처가 어긋나면
**더 완전한 쪽(선관위 시도별)을 기준으로** 다시 세운다.

## 안 하는 것

- sido가 불완전하면 손대지 않는다. 시도 수가 그 시점 행정구역과 맞아야 한다.
- turnout_pct·electors처럼 시도 합으로 유도되지 않는 값은 건드리지 않는다.
- nation이 이미 sido 합과 같으면 아무것도 안 한다(멱등).

## 총선 전국구(13~16대)도 같은 병이 있다

13~16대는 전국구를 **지역구 득표로 배분**했다. 그래서 nation tc7의 votes는 지역구
정당 득표와 같아야 하고, 실제로 13대는 네 정당 모두 **정확히** 일치한다. 그런데
valid_votes에는 그 네 정당 합만 적혀 있어서, pct(공식 정당득표율)와 어긋났다 —
민정당 34.0%인데 계산하면 36.66%가 나오는 식이다. 분모가 틀린 것이다.

`--from-district`는 그 분모를 **지역구 유효표 전체**로 바로잡는다. 후보 목록은
건드리지 않는다(그 표는 의석 배분 대상 정당만 담는 것이 원래 뜻이다) — 대신
covers·_note로 부분 집합임을 밝힌다.

## rank는 한 뜻이어야 한다

rank 있는 race 29,879개 중 **딱 하나**가 득표 순이 아니었다 — 13대 총선 nation tc7이
의석 순이었다(평민당 70석이 통일민주당 59석보다 앞인데 득표는 반대다). 같은 필드가
회차마다 다른 걸 재면 읽는 쪽이 알 길이 없다.

`--rerank`는 rank를 **득표 순**으로 다시 매기고, 원래 순서가 의석 순이었으면
`seat_rank`로 보존한다. 정보를 지우는 게 아니라 두 축을 갈라 놓는다.

사용:
  python3 scripts/normalize/rebuild_nation_from_sido.py 13th-pres-1987 [--write]
  python3 scripts/normalize/rebuild_nation_from_sido.py 14th-general-1992 --from-district [--write]
  python3 scripts/normalize/rebuild_nation_from_sido.py 13th-general-1988 --rerank [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"

# 그 시점 시도 수 — sido race가 이만큼 있어야 '완전하다'고 본다.
# (대전 1989 신설 · 울산 1997 승격 · 세종 2012 신설)
EXPECTED_SIDO = {"1987": 14, "1992": 15, "1997": 16}


def rebuild(eid: str, write: bool) -> int:
    fp = RESULTS / f"{eid}.json"
    d = json.loads(fp.read_text(encoding="utf-8"))
    races = d.get("races") or []
    nat = [r for r in races if r.get("scope") == "nation"]
    sido = [r for r in races if r.get("scope") == "sido"]
    if len(nat) != 1 or not sido:
        print(f"  {eid}: nation 1개·sido 필요 (nation {len(nat)} · sido {len(sido)})")
        return 1
    year = (d.get("_meta") or {}).get("election_date", "")[:4]
    want = EXPECTED_SIDO.get(year)
    if want and len(sido) != want:
        print(f"  {eid}: 시도 {len(sido)}곳 — {year}년 기준 {want}곳이라야 한다. 손대지 않는다.")
        return 1

    tot: Counter = Counter()
    meta: dict = {}
    for r in sido:
        for c in r.get("candidates") or []:
            k = (c.get("name"), c.get("party"))
            tot[k] += c.get("votes") or 0
            meta.setdefault(k, c)
    valid = sum(tot.values())
    old = nat[0]
    old_names = {(c.get("name"), c.get("party")) for c in old.get("candidates") or []}
    old_valid = sum(c.get("votes") or 0 for c in old.get("candidates") or [])
    if old_valid == valid and old_names == set(tot):
        print(f"  {eid}: 이미 일치 — 변경 없음")
        return 0

    cands = []
    for i, ((nm, pty), v) in enumerate(sorted(tot.items(), key=lambda x: -x[1])):
        src = meta[(nm, pty)]
        c = {"name": nm, "party": pty, "votes": v,
             "pct": round(v / valid * 100, 2) if valid else None,
             "rank": i + 1}
        if src.get("won") is not None or i == 0:
            c["won"] = (i == 0)
        cands.append(c)
    new = dict(old)
    new["candidates"] = cands
    new["valid_votes"] = valid
    # voters가 valid와 같게 박혀 있던 자리 — 시도 합으로 유도되면 그걸 쓰고,
    # 아니면 '모른다'로 비운다. 유효표를 투표수로 쓰면 무효표가 0이 된다.
    v_sum = sum(r.get("voters") or 0 for r in sido)
    inv_sum = sum(r.get("invalid_votes") or 0 for r in sido)
    all_have_voters = all(r.get("voters") for r in sido)
    new["voters"] = v_sum if all_have_voters else None
    # 무효표는 투표수 - 유효표다. 시도가 무효표를 안 주더라도 **투표수를 다 주면**
    # 뺄셈으로 나온다 — 유도지 추정이 아니다. 투표수가 하나라도 비면 비워 둔다.
    if inv_sum:
        new["invalid_votes"] = inv_sum
    elif all_have_voters and v_sum >= valid:
        new["invalid_votes"] = v_sum - valid
    else:
        new["invalid_votes"] = None
    races[races.index(old)] = new

    added = sorted(set(tot) - old_names)
    print(f"  {eid}: 유효표 {old_valid:,} → {valid:,} ({valid - old_valid:+,})"
          f" · 후보 {len(old_names)} → {len(tot)}")
    for nm, pty in added:
        print(f"      + {nm} ({pty}) {tot[(nm, pty)]:,}표")

    m = d.setdefault("_meta", {})
    m["nation_source"] = "시도 합산 (sido_source 기준)"
    m["_nation_note"] = (
        "nation은 시도 합으로 다시 세웠다. 원래는 위키백과 infobox에서 왔는데 그쪽이 "
        "주요 후보만 실어서 군소후보가 전국에서만 빠졌다 — 13대 신정일 46,650표가 그랬다. "
        "sido는 선관위 개표현황(VCCP09)이라 더 완전하다.")
    if write:
        fp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  → {fp.relative_to(ROOT)}")
    else:
        print("  (--write 없이 실행 — 저장하지 않음)")
    return 0


def fix_denominator(eid: str, write: bool) -> int:
    """nation tc7의 valid_votes를 지역구 유효표 전체로 바로잡는다(13~16대)."""
    fp = RESULTS / f"{eid}.json"
    d = json.loads(fp.read_text(encoding="utf-8"))
    races = d.get("races") or []
    nat = [r for r in races if r.get("scope") == "nation" and r.get("sg_typecode") == "7"]
    if len(nat) != 1:
        print(f"  {eid}: nation tc7 1개라야 한다 ({len(nat)})")
        return 1
    dvalid = sum(c.get("votes") or 0
                 for r in races if r.get("scope") == "district" and r.get("sg_typecode") == "2"
                 for c in r.get("candidates") or [])
    if not dvalid:
        print(f"  {eid}: 지역구 데이터가 없다")
        return 1
    r = nat[0]
    old = r.get("valid_votes")
    listed = sum(c.get("votes") or 0 for c in r.get("candidates") or [])
    if old == dvalid:
        print(f"  {eid}: 이미 일치 — 변경 없음")
        return 0
    worst_before = max((abs((c.get("pct") or 0) - round((c.get("votes") or 0) / old * 100, 2))
                        for c in r["candidates"] if old and c.get("pct") is not None), default=0)
    worst_after = max((abs((c.get("pct") or 0) - round((c.get("votes") or 0) / dvalid * 100, 2))
                       for c in r["candidates"] if c.get("pct") is not None), default=0)
    r["valid_votes"] = dvalid
    # voters·invalid에 유효표를 그대로 베껴 둔 자리 — 투표수를 모르면서 안다고 적으면
    # 무효표가 0이 된다. 모르는 채로 둔다.
    r["voters"] = None
    r["invalid_votes"] = None
    r["covers"] = "seat_winning_parties"
    r["_note"] = (f"이 표는 **전국구 의석을 배분받은 정당만** 담는다. valid_votes는 지역구 "
                  f"유효표 전체({dvalid:,})이므로 후보 행의 합({listed:,})과 다르다 — 빠진 것은 "
                  "의석 배분 대상이 아닌 정당·무소속 표다. 전에는 valid_votes에 실린 정당 합만 "
                  "적혀 있어 pct(공식 정당득표율)와 어긋났다. rank는 득표가 아니라 의석 순이다.")
    print(f"  {eid}: valid_votes {old:,} → {dvalid:,} · pct 최대오차 "
          f"{worst_before:.2f}%p → {worst_after:.2f}%p")
    if write:
        fp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  → {fp.relative_to(ROOT)}")
    else:
        print("  (--write 없이 실행 — 저장하지 않음)")
    return 0


def rerank(eid: str, write: bool) -> int:
    """rank를 득표 순으로 통일하고, 의석 순이던 것은 seat_rank로 보존한다."""
    fp = RESULTS / f"{eid}.json"
    d = json.loads(fp.read_text(encoding="utf-8"))
    changed = []
    for r in d.get("races") or []:
        cs = [c for c in (r.get("candidates") or []) if c.get("rank") is not None]
        if len(cs) < 2 or any(c.get("votes") is None for c in cs):
            continue
        by_rank = sorted(cs, key=lambda c: c["rank"])
        if [c["votes"] for c in by_rank] == sorted((c["votes"] for c in by_rank), reverse=True):
            continue                      # 이미 득표 순
        was_seat_order = (all(c.get("seats") is not None for c in by_rank)
                          and [c["seats"] for c in by_rank]
                          == sorted((c["seats"] for c in by_rank), reverse=True))
        for c in by_rank:
            if was_seat_order:
                c["seat_rank"] = c["rank"]
        for i, c in enumerate(sorted(cs, key=lambda c: -c["votes"])):
            c["rank"] = i + 1
        changed.append((r.get("scope"), r.get("sg_typecode"), was_seat_order,
                        [(c.get("party") or c.get("name"), c["rank"], c.get("seat_rank"))
                         for c in sorted(cs, key=lambda c: c["rank"])]))
    if not changed:
        print(f"  {eid}: 이미 득표 순 — 변경 없음")
        return 0
    for sc, tc, seat, rows in changed:
        print(f"  {eid} {sc} tc{tc}: {'의석 순 → seat_rank로 보존' if seat else '순서 불명'}")
        for nm, rk, sr in rows:
            print(f"      {nm:14} rank {rk}" + (f" · seat_rank {sr}" if sr else ""))
    if write:
        fp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  → {fp.relative_to(ROOT)}")
    else:
        print("  (--write 없이 실행 — 저장하지 않음)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("eids", nargs="+")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--from-district", action="store_true",
                    help="nation tc7의 분모를 지역구 유효표로 바로잡는다(13~16대 총선)")
    ap.add_argument("--rerank", action="store_true",
                    help="rank를 득표 순으로 통일하고 의석 순은 seat_rank로 보존")
    a = ap.parse_args()
    rc = 0
    for eid in a.eids:
        if a.rerank:
            rc |= rerank(eid, a.write)
        elif a.from_district:
            rc |= fix_denominator(eid, a.write)
        else:
            rc |= rebuild(eid, a.write)
    return rc


if __name__ == "__main__":
    sys.exit(main())
