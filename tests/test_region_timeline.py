"""지역 타임라인 — 시간축은 합치되 수치는 series 안에서만 잇는가.

  timeline continuity  ≠  metric comparability
  same election family ≠  same metric series

지방선거 하나에 광역단체장·기초단체장·광역의원·기초의원·비례가 다 들어 있다.
전부 '지방선거'지만 같은 시계열이 아니다 — 직위도 유권자 구성도 다르다.

그리고 **화면이 새 주장을 만들지 않는다**. 비교 가능 판정은 comparison engine이
이미 했고, renderer는 그것이 허용한 것만 보여준다.

실행: .venv/bin/python tests/test_region_timeline.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data/region_timeline"
FAM = ("conservative", "democratic", "progressive", "regional", "other")
fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    files = sorted(DIR.glob("*.json"))
    if not files:
        print("  · 타임라인 없음, 건너뜀")
        return 0
    print(f"\n[series] 직위가 다르면 잇지 않는가 ({len(files)}개 지역)")
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        pts = d["points"]
        ck(f"{d['region']}: 모든 점에 series가 있다",
           all(p.get("comparison_series_id") for p in pts))
        # 지방선거가 한 series로 뭉치면 안 된다
        loc = {p["comparison_series_id"] for p in pts if p["election_type"] == "local"}
        if loc:
            ck(f"{d['region']}: 지방선거가 직위별로 갈린다 ({len(loc)}종)", len(loc) > 1,
               str(loc))
        # 같은 series 안에서는 선거 종류가 하나여야 한다
        bad = {}
        for p in pts:
            bad.setdefault(p["comparison_series_id"], set()).add(p["election_type"])
        ck(f"{d['region']}: 한 series에 여러 선거 종류가 섞이지 않는다",
           all(len(v) == 1 for v in bad.values()),
           str({k: v for k, v in bad.items() if len(v) > 1}))

    print("\n[층 분리] winner와 계보 구성이 섞이지 않는가")
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        for p in d["points"][:40]:
            ck(f"{d['region']}/{p['election_id']}: winner와 구성이 별도 키",
               "winner" in p and "lineage_composition" in p)
            break

    print("\n[분모] 분류 안 된 표를 지우지 않는가")
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        for p in d["points"]:
            c = p["lineage_composition"]
            if not c:
                continue
            tot = sum(c["share"].values())
            ck(f"{d['region']}/{p['election_id']}: 합이 100 (재정규화 안 함)",
               abs(tot - 100) < 0.6, f"{tot:.2f}")
            # unknown과 무소속은 다른 정보다
            ck(f"{d['region']}/{p['election_id']}: unknown과 무소속이 따로",
               "unknown_share" in c and "independent_share" in c)
            # mixed는 계열이 아니라 상태 — 구성 계열을 밝힌다
            if c["mixed_share"] > 0:
                ck(f"{d['region']}/{p['election_id']}: mixed의 구성 계열이 있다",
                   bool(c["mixed_constituents"]))
            break

    print("\n[claim 제한] 화면이 새 주장을 만들지 않는가")
    checked = 0
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        for p in d["points"]:
            cm = p.get("comparison")
            if not cm:
                continue
            checked += 1
            ck(f"{d['region']}/{p['unit_name_at_the_time']}: 허용 여부가 명시된다",
               all(k in cm for k in ("may_show_level", "may_show_winner",
                                     "may_show_delta", "measurement_scope")))
            # 재집계는 동 귀속표 기준 — 전체 결과가 아니다
            if cm["method"] == "reaggregated":
                ck(f"{d['region']}/{p['unit_name_at_the_time']}: scope가 attributable_only",
                   cm["measurement_scope"] == "attributable_only")
            # delta가 금지됐으면 값이 없어야 한다
            if not cm["may_show_delta"]:
                ck(f"{d['region']}/{p['unit_name_at_the_time']}: delta 금지면 값 없음",
                   not cm.get("delta"))
    ck(f"comparison이 붙은 점이 있다 ({checked})", checked > 0)
    # 하남시갑 — level·winner 금지, delta만 허용. 이 사례가 사라지면 회귀다
    h = DIR / "하남.json"
    if h.exists():
        d = json.loads(h.read_text(encoding="utf-8"))
        g = [p for p in d["points"]
             if p["unit_name_at_the_time"] == "하남시갑" and p.get("comparison")]
        if g:
            cm = g[0]["comparison"]
            ck("하남시갑: 수준값·승자는 금지, 변화량만 허용",
               not cm["may_show_level"] and not cm["may_show_winner"]
               and cm["may_show_delta"])
            ck("하남시갑: 국민의힘 변화량은 구도 변화로 차단",
               cm["delta_blocked"].get("pid:국민의힘") == "candidacy_configuration_changed")

    print("\n[이름] 현재 이름으로 소급하지 않는가")
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        ck(f"{d['region']}: 그 시점 이름과 경계 시점을 갖는다",
           all(p.get("unit_name_at_the_time") and p.get("boundary_valid_at")
               for p in d["points"]))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
