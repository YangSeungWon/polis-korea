"""회차 간 구조 이상치 — 선거 결과가 조용히 무너졌는지 데이터만 보고 판정한다.

UI를 보기 전에 잡는 것이 목적이다. 2026-08 시군구의회 사건은 화면이 '텅 빈 것처럼'
보여서 사용자가 스크린샷으로 발견했는데, 원인은 지역구 행에 sigungu가 비어 있던
것이었다 — race 수는 그대로였다. 그래서 개수만 보면 안 되고 **필드 결측률**도 본다.

두 축:
  1. 개수  — 직위별 race·후보·당선인·단위 수를 직전 동종 회차와 비교
  2. 결측  — 그 직위 행에서 sido/sigungu/district가 비어 있는 비율

scope를 정규화하지 않으면 비교가 무의미하다. 같은 tc3라도 어떤 회차는 시도 행만,
어떤 회차는 시군구 분해 행까지 있어 개수가 몇 배 차이 난다 → 직위별 primary scope만 센다.

재보궐은 제외한다. 회차마다 규모가 ±900% 흔들려 비교 자체가 성립하지 않는다.

severity:
  error  직전에 있던 직위가 통째로 사라짐 / 결측률이 새로 50%p 이상 뛰었음
  warn   개수가 직전 대비 25% 이상 변함 (실제 제도·행정 변화일 수 있다 — 확인용 신호)

사용:
  python3 scripts/audit/audit_structure.py           # 전체
  python3 scripts/audit/audit_structure.py --strict  # warn도 exit 1
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"

# 직위별 '한 번씩만 세는' scope. 하위 분해 행(sigungu_part 등)을 같이 세면
# 회차마다 커버리지가 달라 개수가 몇 배로 튄다.
PRIMARY = {
    "1": "sido", "2": "district", "3": "sido", "4": "sigungu",
    "5": "district", "6": "district", "7": "nation",
    "8": "proportional_sido", "9": "proportional_sigungu", "11": "sido",
}
TC_LABEL = {
    "1": "대통령", "2": "국회의원", "3": "광역단체장", "4": "기초단체장",
    "5": "광역의원", "6": "기초의원", "7": "총선비례", "8": "광역비례",
    "9": "기초비례", "11": "교육감",
}
# 직위별로 채워져 있어야 하는 지역 필드. 비면 지도·hex가 그 행을 집계에서 떨어뜨린다.
REQUIRED = {
    "3": ("sido",), "11": ("sido",), "8": ("sido",),
    "4": ("sido", "sigungu"), "9": ("sido", "sigungu"),
    "5": ("sido", "district"), "6": ("sido", "sigungu", "district"),
    "2": ("sido", "district"),
}
# 개수 변화 문턱. 지표마다 자연 변동폭이 다르다 — 하나로 잡으면 소음이 된다.
#   race·units  선거구 획정이라 회차 간 안정적이다(제도 변경 때만 크게 움직인다)
#   cands       매 선거 다르다(2017 대선 후보 15명 → 2022년 14명 같은 변동은 사실)
#              → 문턱을 훨씬 높게. 낮게 잡았더니 51건 중 40건이 후보 수였다.
WARN_PCT = {"races": 25.0, "units": 25.0, "cands": 80.0}
MISS_JUMP = 50.0       # 결측률이 이만큼(%p) 새로 뛰면 error


def load_races(fp: Path) -> list | None:
    """races가 없는 파일(구 스키마 local_N.json 등)은 대상이 아니다."""
    try:
        d = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None
    if "races" not in d:
        return None
    races = list(d["races"])
    if (d.get("_meta") or {}).get("chunked"):
        cp = fp.with_name(fp.stem + ".sigungu.json")
        if cp.exists():
            try:
                races += json.loads(cp.read_text(encoding="utf-8")).get("races") or []
            except Exception:
                pass
    return races


def indirect_rounds() -> set:
    """간선 회차 (통일주체국민회의·선거인단). 시도별 개표가 없고 전국 1건뿐이라
    직선 회차와 개수를 비교하면 '직위가 사라졌다'는 오탐이 난다."""
    try:
        rounds = json.loads((ROOT / "data/timeline.json").read_text(encoding="utf-8"))["rounds"]
    except Exception:
        return set()
    return {(r.get("kind"), r.get("n")) for r in rounds if r.get("indirect")}


def election_meta(eid: str) -> dict:
    p = ROOT / "data/elections" / f"{eid}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def profile(races: list) -> dict:
    """직위 → {races, cands, winners, units, miss:{필드:비율}}"""
    out = {}
    by_tc = defaultdict(list)
    for r in races:
        tc = r.get("sg_typecode")
        if tc and r.get("scope") == PRIMARY.get(tc):
            by_tc[tc].append(r)
    for tc, rs in by_tc.items():
        cands = sum(len(r.get("candidates") or []) for r in rs)
        winners = sum(1 for r in rs
                      for c in (r.get("candidates") or []) if c.get("is_winner"))
        units = len({(r.get("sido"), r.get("sigungu"), r.get("district")) for r in rs})
        miss = {}
        for f in REQUIRED.get(tc, ()):
            n = sum(1 for r in rs if not r.get(f))
            miss[f] = round(n / len(rs) * 100, 1) if rs else 0.0
        out[tc] = {"races": len(rs), "cands": cands, "winners": winners,
                   "units": units, "miss": miss}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="warn도 exit 1")
    ap.add_argument("--kind", default=None, help="local/presidential/general_election")
    args = ap.parse_args()

    INDIRECT = indirect_rounds()
    rows = []
    for fp in sorted(RESULTS.glob("*.json")):
        if ".sigungu." in fp.name:
            continue
        races = load_races(fp)
        if races is None:
            continue
        eid = fp.stem
        em = election_meta(eid)
        kind = em.get("kind") or ""
        if not kind or kind == "byelection" or "byelection" in eid:
            continue   # 재보궐은 회차마다 규모가 달라 비교가 성립하지 않는다
        if (kind, em.get("n")) in INDIRECT:
            continue   # 간선 — 전국 1건뿐이라 직선과 비교 불가
        rows.append((kind, em.get("date") or "", eid, profile(races)))

    by_kind = defaultdict(list)
    for kind, date, eid, prof in sorted(rows, key=lambda x: (x[0], x[1])):
        by_kind[kind].append((eid, prof))

    errors, warns = [], []
    for kind, seq in by_kind.items():
        if args.kind and kind != args.kind:
            continue
        print(f"\n== {kind} ({len(seq)}회차)")
        for i in range(1, len(seq)):
            eid, cur = seq[i]
            peid, prev = seq[i - 1]
            notes = []
            for tc in sorted(set(prev) | set(cur), key=lambda x: int(x)):
                lbl = TC_LABEL.get(tc, tc)
                p, c = prev.get(tc), cur.get(tc)
                if p and not c:
                    errors.append(f"{eid}: {lbl}가 통째로 사라짐 (직전 {peid} race {p['races']})")
                    notes.append(f"✗ {lbl} 사라짐")
                    continue
                if not p or not c:
                    continue
                for key, label in (("races", "race"), ("cands", "후보"), ("units", "단위")):
                    if not p[key]:
                        continue
                    d = (c[key] / p[key] - 1) * 100
                    if abs(d) >= WARN_PCT[key]:
                        warns.append(f"{eid}: {lbl} {label} {p[key]:,} → {c[key]:,} ({d:+.0f}%)")
                        notes.append(f"⚠ {lbl} {label} {d:+.0f}%")
                # 결측률이 새로 뛰었는가 — 개수는 그대로인데 지역 필드가 빈 사고
                for f, pct in c["miss"].items():
                    was = p["miss"].get(f, 0.0)
                    if pct - was >= MISS_JUMP:
                        errors.append(
                            f"{eid}: {lbl} '{f}' 결측 {was:.0f}% → {pct:.0f}% "
                            f"— 지도·hex 집계에서 이 행들이 빠진다")
                        notes.append(f"✗ {lbl} {f} 결측 {pct:.0f}%")
            print(f"  {eid:24} {' · '.join(notes) if notes else 'ok'}")

    print(f"\nerror {len(errors)} · warn {len(warns)}")
    for e in errors:
        print(f"  ✗ {e}")
    for w in warns:
        print(f"  ⚠ {w}")
    if errors:
        return 1
    return 1 if (args.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
