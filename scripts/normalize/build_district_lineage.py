"""총선 선거구 계보 — 두 회차를 **비교해도 되는 단위와 안 되는 단위를 데이터로 판정**한다.

이것이 완료조건이다. 화면이 아니다. 판정이 서기 전에는 총선 swing이나 득표율 delta를
만들지 않는다 — 경계가 바뀐 단위를 이어 붙이면 없던 변화가 만들어진다.

**읍·면·동 시계열을 기다리지 않는다.** 그게 오래된 병목인데, 우리에겐 이미 1~22대
선거구 폴리곤(data/geo/district_{n}_geojson.json)이 있다. 폴리곤 교차 면적이면
같은 질문에 답할 수 있다: '이 선거구는 지난 회차의 무엇이었나, 그리고 얼마나 같은가.'

관계 유형 (한 쌍 = 현재 선거구 하나에 대한 판정):
  exact            1:1 · 양방향 겹침 ≥ EXACT — 이름도 같다
  renamed          1:1 · 양방향 겹침 ≥ EXACT — 이름만 다르다
  boundary_changed 1:1 · 겹침이 EXACT 미만 MAJOR 이상 — 같은 자리지만 경계가 움직였다
  split            이전 1 → 현재 N (이전 선거구가 여럿으로 쪼개졌다)
  merged           이전 N → 현재 1 (여럿이 하나로 합쳐졌다)
  new              대응하는 이전 선거구가 없다
  unresolvable     겹침이 흩어져 어느 쪽으로도 못 정한다

재집계 가능 여부(comparable)는 관계와 별개로 판정한다:
  exact·renamed             → True   그대로 비교
  boundary_changed          → False  같은 이름이어도 유권자가 다르다
  split·merged·new·unresolv → False  단위가 다르다

출력: data/district_lineage/{현재}__{직전}.json
사용: python3 scripts/normalize/build_district_lineage.py [--pair 22 21] [--all]
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data/geo"
OUT = ROOT / "data/district_lineage"

# 문턱.
#
# 회차별 폴리곤은 출처와 단순화 수준이 다르다 — 21·22대만 오마이뉴스 원본(1.5MB)이고
# 나머지는 재구성본(436KB~784KB)이다. 그래서 **경계가 실제로 안 바뀌었는데도** 겹침이
# 94~97%에 머무는 쌍이 많다(20·21대에서 180여 개).
#
# 이 구간을 한쪽으로 밀면 둘 다 틀린다: exact로 밀면 실제 획정 변화를 놓치고,
# boundary_changed로 밀면 멀쩡한 단위를 비교 불가로 버린다.
# 그래서 **모르는 것을 모른다고 적는다** — comparable을 yes/no가 아니라 3-state로 둔다.
# (오늘 세운 원칙: null ≠ 0, '최근 데이터 없음' ≠ '수집 실패'와 같은 계열)
EXACT = 0.97      # 양방향 이 이상 → 같은 단위 (확실)
NEAR = 0.90       # 이 구간(0.90~0.97)은 폴리곤 정밀도 한계 — 판정 불가
MAJOR = 0.60      # 이 이상이면 '주된 대응'
MINOR = 0.05      # 이 미만은 경계 노이즈로 보고 버린다


def load(n: int) -> list[dict] | None:
    fp = GEO / f"district_{n}_geojson.json"
    if not fp.exists():
        return None
    from shapely.geometry import shape
    out = []
    for f in json.loads(fp.read_text(encoding="utf-8")).get("features", []):
        p = f.get("properties") or {}
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)          # 자기교차 폴리곤 복구 — 없으면 교차 계산이 죽는다
        if g.is_empty:
            continue
        out.append({
            "sido": p.get("SIDO") or "",
            "name": p.get("SGG") or "",
            "key": f"{p.get('SIDO', '')} {p.get('SGG', '')}".strip(),
            "geom": g,
        })
    return out


def overlaps(cur: list[dict], prev: list[dict]) -> dict:
    """현재 선거구 → [(이전 key, 현재 대비 비율, 이전 대비 비율)] (큰 순)."""
    from shapely.strtree import STRtree
    tree = STRtree([x["geom"] for x in prev])
    out = {}
    for c in cur:
        ov = []
        for i in tree.query(c["geom"]):
            p = prev[i]
            inter = c["geom"].intersection(p["geom"]).area
            if inter <= 0:
                continue
            f_cur = inter / c["geom"].area if c["geom"].area else 0
            f_prev = inter / p["geom"].area if p["geom"].area else 0
            if f_cur < MINOR and f_prev < MINOR:
                continue                      # 경계선 노이즈
            ov.append({"prev": p["key"], "of_current": round(f_cur, 4),
                       "of_previous": round(f_prev, 4)})
        ov.sort(key=lambda x: -x["of_current"])
        out[c["key"]] = ov
    return out


def classify(cur_key: str, ov: list[dict], prev_fanout: dict) -> tuple[str, str, str]:
    """(관계, 비교가능 yes/no/unknown, 사유). 사유는 사람이 읽고 판단할 수 있게 남긴다."""
    if not ov:
        return "new", "no", "대응하는 이전 선거구 없음"
    top = ov[0]
    major = [o for o in ov if o["of_current"] >= MAJOR or o["of_previous"] >= MAJOR]

    # 1:1 — 서로가 서로의 대부분을 차지한다
    if top["of_current"] >= EXACT and top["of_previous"] >= EXACT:
        same_name = cur_key == top["prev"]
        return ("exact" if same_name else "renamed"), "yes", (
            "양방향 겹침 ≥97%" + ("" if same_name else " · 이름만 다름"))

    # 0.90~0.97 — 실제 경계 변화인지 폴리곤 정밀도 차이인지 **데이터로 못 가른다**.
    # 이름이 같고 양방향 90% 이상이면 대개 후자지만, 단언할 근거가 없다.
    if top["of_current"] >= NEAR and top["of_previous"] >= NEAR:
        return "minor_boundary_change", "unknown", (
            f"겹침 {top['of_current'] * 100:.0f}%/{top['of_previous'] * 100:.0f}% — "
            "실제 경계 변화인지 폴리곤 정밀도 차이인지 구분 불가"
            + ("" if cur_key == top["prev"] else f" · 이전 '{top['prev']}'"))

    # 현재가 이전 하나에 거의 담긴다 = 이전이 쪼개졌다
    if top["of_current"] >= EXACT and top["of_previous"] < EXACT:
        n = prev_fanout.get(top["prev"], 0)
        if n >= 2:
            return "split", "no", f"이전 '{top['prev']}'이 {n}개로 분할"
        return "boundary_changed", "no", (
            f"이전 '{top['prev']}'의 {top['of_previous'] * 100:.0f}%만 차지")

    # 이전 여럿이 현재 하나에 담긴다 = 합쳐졌다
    if len(major) >= 2 and sum(o["of_current"] for o in major) >= EXACT:
        return "merged", "no", "이전 " + " + ".join(o["prev"] for o in major[:4]) + " 통합"

    if top["of_current"] >= MAJOR and top["of_previous"] >= MAJOR:
        return "boundary_changed", "no", (
            f"주 대응 '{top['prev']}' 겹침 {top['of_current'] * 100:.0f}%"
            f"/{top['of_previous'] * 100:.0f}%")

    return "unresolvable", "no", (
        "겹침이 흩어짐 — " + ", ".join(
            f"{o['prev']} {o['of_current'] * 100:.0f}%" for o in ov[:3]))


def build(cur_n: int, prev_n: int) -> dict | None:
    cur, prev = load(cur_n), load(prev_n)
    if not cur or not prev:
        return None
    ov = overlaps(cur, prev)

    # 이전 선거구가 몇 개로 갈라졌는지 — split 판정에 필요하다
    fanout: dict = {}
    for c_key, lst in ov.items():
        for o in lst:
            if o["of_current"] >= EXACT:      # 현재가 그 이전 안에 거의 담긴다
                fanout[o["prev"]] = fanout.get(o["prev"], 0) + 1

    units, counts = [], {}
    for c in cur:
        rel, comparable, why = classify(c["key"], ov[c["key"]], fanout)
        counts[rel] = counts.get(rel, 0) + 1
        units.append({
            "district": c["key"], "sido": c["sido"],
            "relation": rel, "comparable": comparable, "reason": why,
            "previous": [{k: o[k] for k in ("prev", "of_current", "of_previous")}
                         for o in ov[c["key"]][:4]],
        })
    matched_prev = {o["prev"] for lst in ov.values() for o in lst
                    if o["of_previous"] >= MAJOR}
    gone = sorted({p["key"] for p in prev} - matched_prev)

    n_ok = sum(1 for u in units if u["comparable"] == "yes")
    n_unk = sum(1 for u in units if u["comparable"] == "unknown")
    return {
        "_meta": {
            "current_n": cur_n, "previous_n": prev_n,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": "polis 계산 — 선거구 폴리곤 교차 면적",
            "method": ("두 회차 선거구 폴리곤의 교차 면적으로 대응을 찾는다. "
                       f"양방향 {EXACT:.0%} 이상이면 같은 단위, {MAJOR:.0%} 이상이면 주 대응, "
                       f"{MINOR:.0%} 미만은 경계 노이즈로 버린다."),
            "thresholds": {"exact": EXACT, "major": MAJOR, "minor": MINOR},
            "note": ("comparable='yes'인 단위로만 회차 간 득표율·swing을 만든다. "
                     "경계가 바뀐 단위를 이어 붙이면 없던 변화가 만들어진다. "
                     "'unknown'은 폴리곤 출처·정밀도가 회차마다 달라 판정할 수 없는 것으로, "
                     "'같다'로도 '다르다'로도 쓰지 않는다."),
            "polygon_caveat": ("21·22대는 오마이뉴스 원본(1.5MB), 나머지는 재구성본"
                               "(436KB~784KB)이라 단순화 수준이 다르다. 경계가 실제로 "
                               "안 바뀌었는데도 겹침이 94~97%에 머무는 쌍이 많다."),
        },
        "counts": {**counts, "total": len(units), "comparable": n_ok,
                   "comparable_unknown": n_unk,
                   "previous_total": len(prev), "previous_unmatched": len(gone)},
        "previous_unmatched": gone,
        "units": units,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", nargs=2, type=int, metavar=("CUR", "PREV"))
    ap.add_argument("--all", action="store_true", help="보유한 인접 회차 전부")
    args = ap.parse_args()

    have = sorted(int(p.stem.split("_")[1]) for p in GEO.glob("district_*_geojson.json"))
    pairs = ([(args.pair[0], args.pair[1])] if args.pair
             else [(have[i], have[i - 1]) for i in range(1, len(have))] if args.all
             else [(have[-1], have[-2])])

    OUT.mkdir(parents=True, exist_ok=True)
    for cur_n, prev_n in pairs:
        d = build(cur_n, prev_n)
        if not d:
            print(f"  {cur_n}↔{prev_n}: geojson 없음 — skip", file=sys.stderr)
            continue
        fp = OUT / f"{cur_n}__{prev_n}.json"
        fp.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        c = d["counts"]
        rels = " · ".join(f"{k} {v}" for k, v in sorted(c.items())
                          if k not in ("total", "comparable", "previous_total",
                                       "previous_unmatched"))
        print(f"  {cur_n:2}대 ← {prev_n:2}대  비교가능 {c['comparable']:3}"
              f" · 판정불가 {c['comparable_unknown']:3} / {c['total']:3}"
              f"  ({rels})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
