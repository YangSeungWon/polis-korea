"""지역 페이지 — 없는 값이 0으로 새지 않는지.

2026-08-05 사고: 1~4회 지방선거는 원자료에 electors만 있고 voters가 없다.
`r.get("voters") or 0`이 None을 0으로 강제해 0/134603 = '투표율 0.0%'가 924행에
찍혔다. 사용자는 이걸 실제 투표율로 읽는다 — 없던 사실이 만들어진 것이다.

숫자 칸은 세 상태를 구분해야 한다:
  값 / 무투표(도메인 사실) / 자료 없음(결손)

실행: .venv/bin/python tests/test_region_pages.py
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/build"))
from build_region_pages import collect, MIN_ROUNDS  # noqa: E402

fails = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main():
    by = collect()

    # ── 1. 데이터 레이어: 0으로 강제된 값이 없다 ────────────────────────────
    zero_turnout, zero_pct_contested = [], []
    for (sd, sg), rows in by.items():
        for r in rows:
            if r.get("turnout") == 0:
                zero_turnout.append((sd, sg, r["eid"]))
            # 무투표가 아닌데 1위 득표율이 0이면 강제변환이거나 원자료 결손이다.
            if r.get("pct") == 0 and not r.get("uncontested"):
                zero_pct_contested.append((sd, sg, r["eid"]))
    ck("투표율 0.0이 없다 (없는 값 ≠ 0)", not zero_turnout, str(zero_turnout[:3]))
    ck("경합인데 1위 득표율 0.0인 행이 없다", not zero_pct_contested,
       str(zero_pct_contested[:3]))

    # voters가 없는 회차는 turnout이 None이어야 한다 — 계산을 시도조차 하면 안 된다.
    old = [r for rows in by.values() for r in rows
           if r["eid"] in ("1st-local-1995", "2nd-local-1998",
                           "3rd-local-2002", "4th-local-2006")]
    ck(f"1~4회 지선 {len(old)}행은 투표율이 None",
       old and all(r["turnout"] is None for r in old),
       str([r["eid"] for r in old if r["turnout"] is not None][:3]))

    # ── 2. 렌더 레이어: HTML에 0.0%가 없고 세 상태가 구분된다 ───────────────
    pages = sorted((ROOT / "region").glob("*/index.html"))
    ck(f"지역 페이지가 있다 ({len(pages)}개)", len(pages) > 100)
    bad = [p.parent.name for p in pages if ">0.0%<" in p.read_text(encoding="utf-8")]
    ck("어느 페이지에도 0.0%가 없다", not bad, str(bad[:5]))

    joined = "".join(p.read_text(encoding="utf-8") for p in pages[:80])
    ck("결손은 —(rg-nd)로 표시", "rg-nd" in joined)
    ck("무투표는 별도 표시(rg-nv)", any("rg-nv" in p.read_text(encoding="utf-8")
                                    for p in pages))
    ck("결손과 무투표가 다른 클래스", "rg-nd" != "rg-nv")

    # ── 3. 구조 ─────────────────────────────────────────────────────────────
    thin = [(sd, sg) for (sd, sg), rows in by.items()
            if 0 < len(rows) < MIN_ROUNDS and (ROOT / "region" / f"{sd}-{sg}").exists()]
    ck(f"회차 {MIN_ROUNDS}건 미만은 페이지가 없다", not thin, str(thin[:3]))
    dup = [p.parent.name for p in pages
           if p.parent.name.startswith(("강원도-", "전라북도-"))]
    ck("개명 전 시도로 만든 페이지가 없다", not dup, str(dup[:3]))

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
