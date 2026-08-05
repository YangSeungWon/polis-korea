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

# split(하나 → 여럿)의 정확한 대응은 데이터에서 유도할 수 없다. 인천 중구가 제물포구·
# 영종구로 갈렸다는 건 행정 사실이지 결과 파일에 적혀 있지 않다. 근거 없이 매핑을 지어내면
# 그 위에 쌓는 swing 계산이 조용히 틀린다. 그래서 같은 시도에서 사라진 단위와 새로 생긴
# 단위가 함께 있으면 'boundary_reorganized'로만 표시하고, 정확한 대응은 출처가 생겼을 때
# data/geo/boundary_changes.json에 선언해 쓰도록 남겨 둔다.
BOUNDARY_MAP = ROOT / "data/geo/boundary_changes.json"


def load_boundary_map(cur_id: str, prev_id: str) -> dict:
    """선언된 경계 변경 대응표. 없으면 빈 dict — 추정하지 않는다."""
    if not BOUNDARY_MAP.exists():
        return {}
    try:
        d = json.loads(BOUNDARY_MAP.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d.get(f"{cur_id}__{prev_id}") or {}

# 결과 분류. '수성'을 정당 기준으로 못 박는다. 무소속→무소속은 서로 다른 사람인데
# party bucket만 같은 것이라 수성으로 부르면 정치적으로 틀린 말이 된다.
OUTCOME_INDEP = "independent_to_independent"
# 개명은 정권 교체가 아니다. 한나라당→새누리당(2012)·새정치민주연합→더불어민주당(2015)은
# 같은 당이 이름을 바꾼 것인데, 문자열로 비교하면 '16곳 전부 정당 교체'가 된다 —
# 실제로 6회 지선 광역단체장이 그렇게 찍히고 있었다. 명백한 오독을 만드는 종류다.
#
# registry의 relation='rename' 간선만 따라간다. 합당(merge)·분당(split)은 다른 당이
# 되는 사건이라 이어 붙이지 않는다 — 그건 정말로 정치적 변화다.
RENAME_REL = {"rename"}


def rename_groups() -> dict:
    """정당명 → 개명 사슬의 대표 이름. 개명으로만 이어진 것끼리 한 덩어리."""
    try:
        reg = json.loads((ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"]
    except Exception:
        return {}
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for name, info in reg.items():
        find(name)
        if info.get("relation") in RENAME_REL:
            for pr in info.get("predecessors") or []:
                if pr in reg:
                    union(pr, name)
    return {n: find(n) for n in parent}


_RENAME = None


def same_party(a: str, b: str) -> bool:
    """개명 사슬까지 감안한 동일성. 무소속은 정당이 아니므로 여기서 다루지 않는다."""
    global _RENAME
    if not a or not b:
        return False      # 정당명이 없으면 '같다'고 말할 근거가 없다
    if a == b:
        return True
    if _RENAME is None:
        _RENAME = rename_groups()
    return bool(a and b and _RENAME.get(a, a) == _RENAME.get(b, b))

# 단독 선출직만 단위 대조가 가능하다(1위 정당이 곧 결과).
# 대선(tc1)은 시도가 곧 비교 단위다 — 전국 1석짜리 선거라 '의석 증감'은 뜻이 없고
# 지역별 표심 이동(swing)이 본론이다.
SINGLE_WINNER = {
    "1": ("sido", "대통령 — 시도별"),
    "3": ("sido", "광역단체장"),
    "4": ("sigungu", "기초단체장"),
}
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


def election_name(eid: str) -> str | None:
    """회차 메타의 정식 명칭. results _meta에 없을 때 쓰는 보조 출처."""
    fp = ROOT / "data/elections" / f"{eid}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8")).get("name")
        except Exception:
            pass
    return None


def turnout(races):
    """전국 투표율. 회차 종류마다 최상위 직이 다르므로(대선 1·지선 3·총선 2) 고정하지 않고
    sido scope에서 선거인수가 가장 많은 직을 쓴다 — 그게 전 유권자를 덮는 직이다."""
    # 결손을 0으로 더하지 않는다. 옛 회차(2·3·5대 대선 등)는 원자료에 투표수가 없어
    # `voters or 0`으로 합치면 '투표율 0.0%'라는 없던 사실이 만들어진다.
    # 일부 시도만 있어도 그 합은 전국 투표율이 아니므로, **전부 있을 때만** 계산한다.
    by_tc = defaultdict(lambda: [0, 0, 0, 0])   # [electors, voters, 행수, voters 있는 행수]
    for r in races:
        if r.get("scope") == "sido":
            b = by_tc[r.get("sg_typecode")]
            b[0] += r.get("electors") or 0
            b[2] += 1
            if r.get("voters") is not None:
                b[1] += r["voters"]
                b[3] += 1
    if not by_tc:
        return None
    el, vo, n, n_vo = max(by_tc.values(), key=lambda b: b[0])
    if not el or n_vo != n:
        return None
    return round(vo / el * 100, 1)


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
        if not pm and not cm:
            continue        # 이 회차 종류에 없는 직 — 0으로 채운 빈 블록을 만들지 않는다
        both = set(pm) & set(cm)

        units, not_compared = [], []
        outcome_n = Counter()
        for k in sorted(both):
            p, c = pm[k], cm[k]
            # 이름이 바뀐 시도는 renamed — 경계는 같다.
            mt = "renamed" if (scope == "sido" and p.get("raw_sido") != c.get("raw_sido")) else "exact"
            if p["party"] == "무소속" and c["party"] == "무소속":
                outcome = OUTCOME_INDEP          # 같은 정당이 아니라 정당이 없는 것
            elif same_party(p["party"], c["party"]):
                outcome = "party_hold"   # 개명 포함 — 이름이 바뀐 것과 당이 바뀐 것은 다르다
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

        # 같은 시도에서 사라진 단위와 생긴 단위가 함께 있으면 개편으로 본다. 한쪽만
        # 있으면 신설/폐지다 — 추정 없이 관측만으로 가르는 기준.
        gone_by_sido = Counter(k[0] for k in set(pm) - both)
        born_by_sido = Counter(k[0] for k in set(cm) - both)

        def excluded(k, side):
            other_names = cur_names if side == "previous" else prev_names
            if side == "previous" and k[0] in merged_into:
                return "merged", "merged_into", f"{merged_into[k[0]]}로 통합"
            if side == "current" and k[0] in set(merged_into.values()):
                return "merged", "merged_into", "통합으로 새로 생긴 단위"
            if k[1] in other_names:
                return "transferred", "sido_transferred", "상위 시도가 바뀌어 직접 대조하지 않음"
            reorg = gone_by_sido.get(k[0], 0) and born_by_sido.get(k[0], 0)
            if reorg:
                return ("boundary_changed", "boundary_reorganized",
                        "같은 시도에서 단위가 사라지고 새로 생겼다 — 행정구역 개편")
            if side == "previous":
                return "abolished", "abolished_unit", "이번 회차에 대응 단위가 없다"
            return "new", "new_unit", "지난 회차에 대응 단위가 없다"

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

    # 전국 득표율 변화 — 대선에서 가장 먼저 읽히는 값. nation scope가 있을 때만.
    def nation_share(races):
        for r in races:
            if r.get("scope") == "nation" and r.get("sg_typecode") == "1":
                return {c.get("party") or "무소속": c.get("pct")
                        for c in (r.get("candidates") or []) if c.get("pct") is not None}
        return {}
    np_, nc_ = nation_share(prev_races), nation_share(cur_races)
    nation = None
    if np_ and nc_:
        keys = sorted(set(np_) | set(nc_))
        nation = {
            "previous": np_, "current": nc_,
            "delta": {k: round(nc_.get(k, 0) - np_.get(k, 0), 2) for k in keys
                      if abs(nc_.get(k, 0) - np_.get(k, 0)) >= 0.05},
            "note": "정당 기준 전국 득표율. 후보가 달라도 정당이 같으면 이어 본다.",
        }

    tp, tc_ = turnout(prev_races), turnout(cur_races)
    return {
        "_meta": {
            "current": cur_id, "previous": prev_id,
            "current_name": cur_doc["_meta"].get("election"),
            # 옛 회차는 results _meta에 이름이 없다 — 없으면 회차 메타에서 가져온다.
            # 비면 화면에 '2nd-pres-1952와 비교'처럼 내부 ID가 그대로 나간다.
            "previous_name": (prev_doc["_meta"].get("election")
                              or election_name(prev_id)),
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": "polis 계산",
            "method": ("같은 이름의 단위끼리 대조한다. 개명(강원도→강원특별자치도 등)은 "
                       "이어 붙이고, 통합·신설·개편·이관은 비교하지 않고 not_compared에 담는다."),
        },
        "turnout": {"previous": tp, "current": tc_,
                    "delta": round(tc_ - tp, 1) if tp is not None and tc_ is not None else None},
        "nation": nation,
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
    fmt = lambda v: f"{v}%" if v is not None else "자료 없음"
    d = f" ({t['delta']:+})" if t["delta"] is not None else ""
    print(f"   투표율 {fmt(t['previous'])} → {fmt(t['current'])}{d}", file=sys.stderr)
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
