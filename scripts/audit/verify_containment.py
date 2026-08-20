"""containment.json의 주장을 자료로 다시 확인한다.

이 파일은 사람이 쓰는 파일이고, `exhaustive: true`는 "하위 단위가 상위 단위를
남김없이 나눈다"는 **사실 주장**이다. 그 주장 위에서 지역 페이지가 득표를 합산하므로,
틀리면 없던 숫자가 만들어진다. 그래서 주장을 적어두는 것으로 끝내지 않고 매번 센다.

두 산술로 본다:

  ① 시도 총합 무모순 — 그 회차의 Σ(시도의 시군구 electors) == 시도 electors.
     겹치면 초과하고 빠지면 모자란다. 상위 단위와 하위 단위가 같이 들어와
     이중으로 세어지는 상태를 이것이 잡는다.
  ② 상위 앵커 일치 — 같은 회차에 상위 단위 직접 행이 있으면
     Σ(children electors) == 상위 electors.

②가 불가능한 기록도 있다(옛 대선의 선거구 개표는 상위 단위 행이 없다). 그때는
①만으로 판정하고, 그 사실을 그대로 출력한다 — '확인했다'와 '확인할 수 없었다'를
같은 칸에 쓰지 않는다.

실행: .venv/bin/python scripts/audit/verify_containment.py
"""
from __future__ import annotations
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/build"))
from build_region_pages import load_all, sido_canon  # noqa: E402

CONT = ROOT / "data/geography/containment.json"
COUNT_TC = ("1", "3", "4", "11")
fails: list = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def parse(eid: str) -> tuple:
    kind, parent, name = eid.split(":", 2)
    return kind, parent, name


def main() -> int:
    recs = json.loads(CONT.read_text(encoding="utf-8"))["containments"]
    print(f"containment {len(recs)}건")

    rounds = list(load_all())

    # ── ① 시도 총합 무모순 (파일과 무관한 전역 검사) ────────────────────────
    ok = bad = 0
    worst = []
    for eid, _meta, races in rounds:
        tot, part, n = {}, collections.Counter(), collections.Counter()
        for r in races:
            sd, tc, sc = sido_canon(r.get("sido")), r.get("sg_typecode"), r.get("scope")
            if not sd or tc not in ("1", "3", "11"):
                continue
            if sc == "sido":
                tot[(sd, tc)] = r.get("electors")
            elif sc == "sigungu" and r.get("sigungu") and r.get("electors"):
                part[(sd, tc)] += r["electors"]
                n[(sd, tc)] += 1
        for k, v in tot.items():
            if v is None or not n[k]:
                continue
            if v == part[k]:
                ok += 1
            else:
                bad += 1
                worst.append(f"{eid} {k} {v}≠{part[k]}")
    ck(f"시도 총합 무모순 ({ok}건 오차 0)", bad == 0 and ok > 100,
       f"불일치 {bad} — {worst[:3]}")

    # ── ② 기록마다: children이 실재하고, 앵커가 맞는가 ──────────────────────
    keys = collections.defaultdict(set)     # (시도, 이름) → 등장 회차
    rows = collections.defaultdict(list)    # (시도, 이름, eid, tc) → row
    for eid, _meta, races in rounds:
        for r in races:
            sd, sg, tc, sc = (sido_canon(r.get("sido")), r.get("sigungu"),
                              r.get("sg_typecode"), r.get("scope"))
            if sd and sg and tc in COUNT_TC and (sc or "").startswith("sigungu"):
                keys[(sd, sg)].add(eid)
                rows[(sd, sg, eid, tc)].append(r)

    ghost, unverified, mismatch = [], [], []
    for c in recs:
        _k, sd, p = parse(c["parent"])
        kids = [parse(x)[2] for x in c["children"]]
        for kid in kids:
            if not keys.get((sd, kid)):
                ghost.append(f'{c["id"]} → {kid}')
        n_anchor = 0
        for eid in sorted({e for kid in kids for e in keys.get((sd, kid), ())}):
            for tc in ("1", "3", "11"):
                ce = [r for kid in kids for r in rows.get((sd, kid, eid, tc), [])
                      if r.get("scope") == "sigungu"]
                pe = [r for r in rows.get((sd, p, eid, tc), [])
                      if r.get("scope") == "sigungu"]
                if ce and pe and pe[0].get("electors"):
                    s = sum(r.get("electors") or 0 for r in ce)
                    if s == pe[0]["electors"]:
                        n_anchor += 1
                    elif s:
                        mismatch.append(f'{c["id"]} {eid}:{tc} {pe[0]["electors"]}≠{s}')
            pe4 = [r for r in rows.get((sd, p, eid, "4"), [])
                   if r.get("scope") == "sigungu"]
            ce3 = [r for kid in kids for r in rows.get((sd, kid, eid, "3"), [])
                   if r.get("scope") == "sigungu"]
            if pe4 and ce3 and pe4[0].get("electors"):
                s = sum(r.get("electors") or 0 for r in ce3)
                if s == pe4[0]["electors"]:
                    n_anchor += 1
                elif s and not c.get("caveat"):
                    mismatch.append(f'{c["id"]} {eid}:4vs3 {pe4[0]["electors"]}≠{s}')
        if not n_anchor:
            unverified.append(f'{c["id"]}')

    ck("children이 전부 자료에 실재한다", not ghost, f"{len(ghost)}개 — {ghost[:3]}")
    ck("앵커가 있는 기록은 전부 오차 0", not mismatch,
       f"{len(mismatch)}건 — {mismatch[:3]}")
    print(f"  · 앵커로 확인 불가 {len(unverified)}건 — 상위 단위 직접 행이 없는 "
          f"기록이다(옛 대선의 선거구 개표). 시도 총합으로만 판정했다.")
    for u in unverified:
        print(f"      {u}")

    # ── ③ exhaustive가 아닌 기록으로는 합산하지 않는다 ──────────────────────
    non_ex = [c["id"] for c in recs if not c.get("exhaustive")]
    print(f"  · exhaustive=false {len(non_ex)}건 (합산 대상 아님)"
          + (f" — {non_ex[:3]}" if non_ex else ""))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
