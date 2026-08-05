"""총선 4층 분리 — 서로 다른 질문을 한 숫자로 뭉개지 않는가.

총선에는 서로 다른 질문이 있고, 하나의 `party_swing`으로 답하려 한 것이 구조적
문제였다:

  ① 전국 결과의 변화        전체 지역구 독립 합산 — **선거구 매칭 불필요**
  ② 비례 정당득표           투표용지 그대로 — 위성정당을 본당과 합치지 않는다
  ③ 같은 선거구에서의 변화   comparable=yes만
  ④ 획정 변화 자체          split/merge/boundary_change — 버리는 게 아니라 콘텐츠

①과 ③을 섞으면 편향된 부분집합이 전국 지표가 된다. 22↔21에서 그 부분집합의
1위 정당 구성이 ±6%p, 21↔20에서는 ±20%p 기울었다.

실행: .venv/bin/python tests/test_general_layers.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CMP = ROOT / "data/comparisons/general"
AGG_KEYS = ("party_swing_in_compared", "turnout_in_compared", "biggest_moves")
fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    nat = sorted(CMP.glob("national__*.json"))
    unit = sorted(p for p in CMP.glob("*__*.json") if not p.name.startswith("national__"))
    ck(f"① 전국 집계 파일 ({len(nat)})", bool(nat))
    ck(f"③ 선거구 비교 파일 ({len(unit)})", bool(unit))

    # ── ① 전국은 매칭 없이, 전체를 센다 ────────────────────────────────────
    print("\n[① 전국] 선거구 매칭 없이 전체를 세는가")
    for fp in nat:
        d = json.loads(fp.read_text(encoding="utf-8"))
        for eid, e in d["elections"].items():
            nd = e["national_district_vote"]
            res = json.loads((ROOT / "data/results" / f"{eid}.json").read_text(encoding="utf-8"))
            n_real = sum(1 for r in res["races"]
                         if r.get("sg_typecode") == "2" and r.get("scope") == "district")
            ck(f"{eid}: 전체 지역구 {n_real}곳을 다 셌다",
               nd["districts"] == n_real, f"{nd['districts']} vs {n_real}")
            # 부분집합이 아니라는 증거 — comparable 개수와 달라야 한다
            ck(f"{eid}: 출마 범위(ran_in)가 정당마다 있다",
               all("ran_in" in v for v in nd["by_party"].values()))
            pcts = [v["pct"] for v in nd["by_party"].values() if v["pct"]]
            ck(f"{eid}: 득표율 합이 100%에 가깝다 ({sum(pcts):.1f}%)",
               99.0 <= sum(pcts) <= 101.0, f"{sum(pcts):.2f}")
        ck("전국 집계에 선거구 lineage 의존이 없다",
           "lineage" not in json.dumps(d["_meta"], ensure_ascii=False)
           or "불필요" in json.dumps(d["_meta"], ensure_ascii=False))

    # ── ② 비례는 ballot 그대로 ──────────────────────────────────────────────
    print("\n[② 비례] 위성정당을 본당과 합치지 않는가")
    for fp in nat:
        d = json.loads(fp.read_text(encoding="utf-8"))
        for eid, e in d["elections"].items():
            pr = e["proportional"]
            if not pr.get("available"):
                continue
            names = [b["ballot_party"] for b in pr["ballot_parties"]]
            ck(f"{eid}: ballot_party 필드를 쓴다", "ballot_party" in pr["ballot_parties"][0])
            if "21st" in eid:
                ck("21대 비례에 위성정당이 그대로 있다 (미래한국당·더불어시민당)",
                   "미래한국당" in names and "더불어시민당" in names, str(names[:4]))
            if "22nd" in eid:
                ck("22대 비례에 위성정당이 그대로 있다 (국민의미래·더불어민주연합)",
                   "국민의미래" in names and "더불어민주연합" in names, str(names[:4]))
            ck(f"{eid}: 합치지 않는다는 근거가 적혀 있다", "위성정당" in pr.get("note", ""))

    # ── ③ 선거구 비교는 게이트를 통과할 때만 집계 ───────────────────────────
    print("\n[③ 선거구] 부분집합을 전국처럼 쓰지 않는가")
    for fp in unit:
        d = json.loads(fp.read_text(encoding="utf-8"))
        tag = fp.stem[:22]
        ck(f"{tag}: aggregation_allowed가 있다", "aggregation_allowed" in d)
        if not d.get("aggregation_allowed"):
            leaked = [k for k in AGG_KEYS if k in d]
            ck(f"{tag}: 차단 시 집계 지표 없음", not leaked, str(leaked))
        ck(f"{tag}: unit-level delta는 살아 있다",
           any(u.get("share_delta") for u in d["units"]))

    # ── 층이 섞이지 않는가 ──────────────────────────────────────────────────
    print("\n[분리] 층이 서로 섞이지 않는가")
    for fp in nat:
        d = json.loads(fp.read_text(encoding="utf-8"))
        ck(f"{fp.stem[:26]}: 전국 파일에 unit-level 키가 없다",
           "units" not in d and not any(k in d for k in AGG_KEYS))
    for fp in unit:
        d = json.loads(fp.read_text(encoding="utf-8"))
        ck(f"{fp.stem[:22]}: 선거구 파일에 전국 집계 키가 없다",
           "national_district_vote" not in d and "proportional" not in d)

    # ── ④ 획정 변화가 버려지지 않는가 ───────────────────────────────────────
    print("\n[④ 획정] 변화 자체가 데이터로 남는가")
    for fp in unit:
        d = json.loads(fp.read_text(encoding="utf-8"))
        changed = [u for u in d["units"]
                   if u["relation"] in ("split", "merged", "boundary_changed")]
        ck(f"{fp.stem[:22]}: 획정 변경 {len(changed)}곳이 사유와 함께 남아 있다",
           bool(changed) and all(u.get("reason") for u in changed))
    geo = ROOT / "data/geography/events.json"
    if geo.exists():
        ev = json.loads(geo.read_text(encoding="utf-8"))["events"]
        ed = [e for e in ev if e["kind"] == "electoral_district"]
        ck(f"선거구 변화가 지리 계보에도 이벤트로 있다 ({len(ed)})", bool(ed))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
