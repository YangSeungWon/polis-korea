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

# 이름만 바뀐 같은 단위 — 이어 붙인다.
SIDO_RENAME = {"강원도": "강원특별자치도", "전라북도": "전북특별자치도"}

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
            "pct": top.get("pct"), "margin": margin}


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

    offices = {}
    for tc, (scope, label) in SINGLE_WINNER.items():
        key_field = "sido" if scope == "sido" else "sigungu"
        pm = unit_map(prev_races, tc, scope, key_field)
        cm = unit_map(cur_races, tc, scope, key_field)
        units, not_compared = [], []
        flips = holds = 0
        for k in sorted(set(pm) & set(cm)):
            p, c = pm[k], cm[k]
            changed = p["party"] != c["party"]
            flips += changed
            holds += (not changed)
            units.append({
                "sido": k[0], "unit": k[1] or k[0],
                "prev_party": p["party"], "cur_party": c["party"], "changed": changed,
                "prev_pct": p["pct"], "cur_pct": c["pct"],
                "prev_margin": p["margin"], "cur_margin": c["margin"],
                "margin_delta": (round(c["margin"] - p["margin"], 2)
                                 if p["margin"] is not None and c["margin"] is not None else None),
            })
        # 사유를 가능한 만큼 특정한다. 같은 이름이 다른 시도에 있으면 '시도 이관'
        # (경북 군위군 → 대구 편입), 통합 시도로 흡수됐으면 '시도 통합', 그 외는 개편·신설.
        merged_into = {}
        merge_meta = (json.loads((ROOT / f"data/elections/{cur_id}.json").read_text(encoding="utf-8"))
                      .get("sido_merge") or [])
        for mm in merge_meta:
            for src in mm.get("merge_from") or []:
                merged_into[canon_sido(src)] = mm.get("canonical")
        cur_names = {k[1] for k in cm}
        prev_names = {k[1] for k in pm}
        for k in sorted(set(pm) - set(cm)):
            if k[0] in merged_into:
                reason = f"{merged_into[k[0]]}로 통합"
            elif k[1] in cur_names:
                reason = "다른 시도로 이관"
            else:
                reason = "이번 회차에 같은 이름의 단위가 없음 (개편·폐지)"
            not_compared.append({"sido": k[0], "unit": k[1] or k[0], "side": "previous",
                                 "reason": reason})
        for k in sorted(set(cm) - set(pm)):
            if k[0] in merged_into.values():
                reason = "통합으로 새로 생긴 단위"
            elif k[1] in prev_names:
                reason = "다른 시도에서 이관"
            else:
                reason = "지난 회차에 없던 단위 (신설·개편)"
            not_compared.append({"sido": k[0], "unit": k[1] or k[0], "side": "current",
                                 "reason": reason})
        offices[tc] = {
            "label": label,
            "party_seats": {
                "previous": dict(Counter(v["party"] for v in pm.values()).most_common()),
                "current": dict(Counter(v["party"] for v in cm.values()).most_common()),
                "delta": delta_counter(Counter(v["party"] for v in pm.values()),
                                       Counter(v["party"] for v in cm.values())),
            },
            # 전체 증감에는 통합·개편으로 인한 구조적 변화가 섞인다(17개 시도 → 16개).
            # 실제로 표심이 뒤집힌 몫은 '비교된 단위'만 따로 낸다.
            "delta_compared_only": delta_counter(
                Counter(pm[k]["party"] for k in set(pm) & set(cm)),
                Counter(cm[k]["party"] for k in set(pm) & set(cm))),
            "flips": flips, "holds": holds,
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
        print(f"   {o['label']}: 교체 {o['flips']} · 수성 {o['holds']}"
              f" · 비교 제외 {len(o['not_compared'])} · 증감 {o['party_seats']['delta']}",
              file=sys.stderr)
    for tc, c in data["councils"].items():
        print(f"   {c['label']} 의석 증감: {c['delta']}", file=sys.stderr)


if __name__ == "__main__":
    main()
