"""회차 간 비교 모델 → data/comparisons/{current}__{previous}.json.

화면 하나를 만드는 게 아니라 **비교 결과를 데이터 레이어에서 표준화**한다. 그래야 지도·표·
인물 페이지·정당 페이지가 같은 계산을 다시 짜지 않고 재사용한다.

비교의 어려움은 계산이 아니라 **단위가 안 맞는 것**이다. 8회→9회만 해도:
  · 통합  광주광역시 + 전라남도 → 전남광주특별시
  · 개명  강원도 → 강원특별자치도 · 전라북도 → 전북특별자치도
  · 개편  인천 중구·동구 → 제물포구·영종구 / 서구 → 검단구 분리
  · 이관  경북 군위군 → 대구광역시 편입

개명은 같은 단위이므로 이어 붙이고, **통합·개편·이관은 비교하지 않고 not_compared에
따로 담는다.** 조용히 빼면 '민주당 -1'처럼 실제로 일어나지 않은 변화가 만들어진다.

지방의원(tc5·6)은 선거구 획정이 바뀌므로 단위 대조를 하지 않고 정당별 의석 합계만 낸다.

사용:
  python3 scripts/build/build_comparison.py --current 9th-local-2026 --previous 8th-local-2022
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"
OUT_DIR = ROOT / "data/comparisons"

# 이름만 바뀐 같은 단위 — 경계가 같으므로 이어 붙인다(match_type='renamed').
SIDO_RENAME = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도"}

# 매칭 유형. 정규화(이름 맞추기)와 비교 가능성 판정은 다른 문제다 — 이름을 맞췄다고
# 경계가 같은 게 아니다. 직접 delta를 낼 수 있는 건 exact·renamed뿐이다.
MATCH_DIRECT = ("exact", "renamed")

# 비교 불가 사유 — 문자열이 아니라 코드로 둔다. 나중에 '행정구역 개편'만 거르는 필터를
# 만들 수 있고, 문구가 바뀌어도 소비하는 쪽이 안 깨진다.
REASON = {
    "merged_into": "다른 단위와 통합",
    "sido_transferred": "상위 시도가 바뀜",
    "boundary_reorganized": "행정구역 개편",
    "new_unit": "지난 회차에 없던 단위",
    "abolished_unit": "이번 회차에 없는 단위",
}

# 결과 분류. '수성'을 정당 기준으로 못 박는다. 무소속→무소속은 서로 다른 사람인데
# party bucket만 같은 것이라 수성으로 부르면 정치적으로 틀린 말이 된다.
OUTCOME_INDEP = "independent_to_independent"

# 단독 선출직만 단위 대조가 가능하다(1위 정당이 곧 결과).
SINGLE_WINNER = {"3": ("sido", "광역단체장"), "4": ("sigungu", "기초단체장")}
# 의회는 선거구가 바뀌므로 합계만.
COUNCIL = {"5": "광역의원", "6": "기초의원", "8": "광역의원 비례", "9": "기초의원 비례"}


def load(eid: str) -> tuple[dict, list]:
    p = RESULTS / f"{eid}.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    races = list(doc.get("races") or [])
    if doc.get("_meta", {}).get("chunked"):
        cp = RESULTS / f"{eid}.sigungu.json"
        if cp.exists():
            races += json.loads(cp.read_text(encoding="utf-8")).get("races") or []
    return doc, races


def canon_sido(s: str) -> str:
    return SIDO_RENAME.get(s or "", s or "")


def winner_of(race: dict):
    cs = [c for c in (race.get("candidates") or []) if c.get("won")]
    if not cs:
        cs = sorted((race.get("candidates") or []), key=lambda c: -(c.get("votes") or 0))[:1]
    if not cs:
        return None
    top = cs[0]
    others = sorted((c for c in (race.get("candidates") or []) if c is not top),
                    key=lambda c: -(c.get("votes") or 0))
    margin = None
    if top.get("pct") is not None and others and others[0].get("pct") is not None:
        margin = round(top["pct"] - others[0]["pct"], 2)
    return {"party": top.get("party") or "무소속", "name": top.get("name"),
            "pct": top.get("pct"), "margin": margin,
            "raw_sido": race.get("sido")}


def unit_map(races, tc, scope, key_field):
    out = {}
    for r in races:
        if r.get("sg_typecode") != tc or r.get("scope") != scope:
            continue
        w = winner_of(r)
        if not w:
            continue
        sd = canon_sido(r.get("sido"))
        # 시도 단위(광역단체장)는 unit 키도 canon을 써야 한다. 원본을 쓰면 개명된 시도가
        # (강원특별자치도, 강원도) vs (강원특별자치도, 강원특별자치도)로 갈려 안 붙는다.
        unit = sd if key_field == "sido" else (r.get(key_field) or "")
        out[(sd, unit)] = w
    return out


def council_seats(races, tc):
    """정당별 의석 — 지역구는 당선자 수, 비례는 seats 필드."""
    seats = Counter()
    for r in races:
        if r.get("sg_typecode") != tc:
            continue
        if tc in ("5", "6") and r.get("scope") == "district":
            for c in r.get("candidates") or []:
                if c.get("won"):
                    seats[c.get("party") or "무소속"] += 1
        elif tc in ("8", "9") and r.get("scope", "").startswith("proportional"):
            for c in r.get("candidates") or []:
                if c.get("seats"):
                    seats[c["party"] or "무소속"] += c["seats"]
    return seats


def turnout(races):
    el = vo = 0
    for r in races:
        if r.get("sg_typecode") == "3" and r.get("scope") == "sido":
            el += r.get("electors") or 0
            vo += r.get("voters") or 0
    return round(vo / el * 100, 1) if el else None


def delta_counter(prev: Counter, cur: Counter) -> dict:
    keys = set(prev) | set(cur)
    return {k: cur.get(k, 0) - prev.get(k, 0) for k in sorted(keys)
            if cur.get(k, 0) - prev.get(k, 0) != 0}


def build(cur_id: str, prev_id: str) -> dict:
    cur_doc, cur_races = load(cur_id)
    prev_doc, prev_races = load(prev_id)

    merged_into = {}
    for mm in (json.loads((ROOT / f"data/elections/{cur_id}.json").read_text(encoding="utf-8"))
               .get("sido_merge") or []):
        for src in mm.get("merge_from") or []:
            merged_into[canon_sido(src)] = mm.get("canonical")

    offices = {}
    for tc, (scope, label) in SINGLE_WINNER.items():
        key_field = "sido" if scope == "sido" else "sigungu"
        pm = unit_map(prev_races, tc, scope, key_field)
        cm = unit_map(cur_races, tc, scope, key_field)
        both = set(pm) & set(cm)

        units, not_compared = [], []
        outcome_n = Counter()
        for k in sorted(both):
            p, c = pm[k], cm[k]
            # 이름이 바뀐 시도는 renamed — 경계는 같다.
            mt = "renamed" if (scope == "sido" and p.get("raw_sido") != c.get("raw_sido")) else "exact"
            if p["party"] == "무소속" and c["party"] == "무소속":
                outcome = OUTCOME_INDEP          # 같은 정당이 아니라 정당이 없는 것
            elif p["party"] == c["party"]:
                outcome = "party_hold"
            else:
                outcome = "party_flip"
            outcome_n[outcome] += 1
            units.append({
                "sido": k[0], "unit": k[1] or k[0], "match_type": mt, "outcome": outcome,
                "prev_party": p["party"], "cur_party": c["party"],
                "prev_pct": p["pct"], "cur_pct": c["pct"],
                "prev_margin": p["margin"], "cur_margin": c["margin"],
                "margin_delta": (round(c["margin"] - p["margin"], 2)
                                 if p["margin"] is not None and c["margin"] is not None else None),
            })

        cur_names = {k[1] for k in cm}
        prev_names = {k[1] for k in pm}

        def excluded(k, side):
            other_names = cur_names if side == "previous" else prev_names
            if side == "previous" and k[0] in merged_into:
                return "merged", "merged_into", f"{merged_into[k[0]]}로 통합"
            if side == "current" and k[0] in set(merged_into.values()):
                return "merged", "merged_into", "통합으로 새로 생긴 단위"
            if k[1] in other_names:
                return "transferred", "sido_transferred", "상위 시도가 바뀌어 직접 대조하지 않음"
            return "boundary_changed", "boundary_reorganized", "행정구역 개편으로 짝이 없음"

        for side, only in (("previous", set(pm) - both), ("current", set(cm) - both)):
            for k in sorted(only):
                mt, code, note = excluded(k, side)
                not_compared.append({
                    "sido": k[0], "unit": k[1] or k[0], "side": side,
                    "match_type": mt, "reason_code": code,
                    "reason": REASON.get(code, code), "note": note,
                })

        prev_parties = Counter(v["party"] for v in pm.values())
        cur_parties = Counter(v["party"] for v in cm.values())
        counts = {
            "previous_units": len(pm), "current_units": len(cm),
            "direct_comparable": len(both),
            "previous_unmatched": len(pm) - len(both),
            "current_unmatched": len(cm) - len(both),
            "party_hold": outcome_n["party_hold"],
            "party_flip": outcome_n["party_flip"],
            OUTCOME_INDEP: outcome_n[OUTCOME_INDEP],
        }
        offices[tc] = {
            "label": label, "counts": counts,
            "party_seats": {
                "previous": dict(prev_parties.most_common()),
                "current": dict(cur_parties.most_common()),
                "delta": delta_counter(prev_parties, cur_parties),
            },
            # 전체 증감엔 통합·개편으로 인한 구조적 변화가 섞인다(17개 시도 → 16개).
            # 표심으로 뒤집힌 몫은 직접 비교 가능한 단위만 따로 낸다.
            "delta_compared_only": delta_counter(
                Counter(pm[k]["party"] for k in both), Counter(cm[k]["party"] for k in both)),
            "units": units, "not_compared": not_compared,
        }

    councils = {}
    for tc, label in COUNCIL.items():
        p, c = council_seats(prev_races, tc), council_seats(cur_races, tc)
        if not p and not c:
            continue
        councils[tc] = {"label": label, "previous": dict(p.most_common()),
                        "current": dict(c.most_common()), "delta": delta_counter(p, c),
                        "note": "선거구 획정이 달라 단위 대조는 하지 않고 합계만 비교한다."}

    tp, tc_ = turnout(prev_races), turnout(cur_races)
    return {
        "_meta": {
            "current": cur_id, "previous": prev_id,
            "current_name": cur_doc["_meta"].get("election"),
            "previous_name": prev_doc["_meta"].get("election"),
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": "polis 계산",
            "method": ("같은 이름의 단위끼리 대조한다. 개명(강원도→강원특별자치도 등)은 "
                       "이어 붙이고, 통합·신설·개편·이관은 비교하지 않고 not_compared에 담는다."),
        },
        "turnout": {"previous": tp, "current": tc_,
                    "delta": round(tc_ - tp, 1) if tp is not None and tc_ is not None else None},
        "offices": offices,
        "councils": councils,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--current", required=True)
    ap.add_argument("--previous", required=True)
    args = ap.parse_args()
    data = build(args.current, args.previous)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fp = OUT_DIR / f"{args.current}__{args.previous}.json"
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"→ {fp.relative_to(ROOT)}", file=sys.stderr)
    t = data["turnout"]
    print(f"   투표율 {t['previous']}% → {t['current']}% ({t['delta']:+})", file=sys.stderr)
    for tc, o in data["offices"].items():
        n = o["counts"]
        print(f"   {o['label']}: 이전 {n['previous_units']} → 현재 {n['current_units']}"
              f" · 직접비교 {n['direct_comparable']}"
              f" (교체 {n['party_flip']} · 유지 {n['party_hold']}"
              f" · 무소속끼리 {n['independent_to_independent']})"
              f" · 미매칭 이전 {n['previous_unmatched']}·현재 {n['current_unmatched']}",
              file=sys.stderr)
        print(f"      정당 증감(비교분만) {o['delta_compared_only']}", file=sys.stderr)
    for tc, c in data["councils"].items():
        print(f"   {c['label']} 의석 증감: {c['delta']}", file=sys.stderr)


if __name__ == "__main__":
    main()
