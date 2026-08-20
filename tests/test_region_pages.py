"""지역 페이지 — 없는 값이 0으로 새지 않는지.

2026-08-05 사고: 1~4회 지방선거는 원자료에 electors만 있고 voters가 없다.
`r.get("voters") or 0`이 None을 0으로 강제해 0/134603 = '투표율 0.0%'가 924행에
찍혔다. 사용자는 이걸 실제 투표율로 읽는다 — 없던 사실이 만들어진 것이다.

숫자 칸은 세 상태를 구분해야 한다:
  값 / 무투표(도메인 사실) / 자료 없음(결손)

실행: .venv/bin/python tests/test_region_pages.py
"""
from __future__ import annotations
import collections
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/build"))
from build_region_pages import (collect, collect_sido, fold_index,  # noqa: E402
                                MIN_ROUNDS)

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

    # ── 4. 원천 집계 단위를 지역으로 만들지 않았는가 ────────────────────────
    # 검사는 fold_target을 쓰지 않는다. 그걸 쓰면 fold_target을 통째로 꺼도 검사가
    # 같이 꺼져 통과한다(변이 시험에서 실제로 그랬다). 지역 이름만 보고 판정한다.
    keys = {(sd, sg) for (sd, sg) in by}
    names = collections.defaultdict(set)
    for sd, sg in keys:
        names[sd].add(sg)

    # 5·6·7대 대선은 서울 5개 구·광주시를 국회의원 선거구 갑/을/병/정으로 나눠
    # 집계한다. 그걸 지역으로 만들어 실재하지 않는 페이지 12개가 생겼고, 실재하는
    # 동대문구에서는 1963·1967·1971 대선이 통째로 비어 있었다.
    fake = []
    for sd, sg in sorted(keys):
        m2 = re.match(r"^(.+?)([갑을병정무])구$", sg)
        if not m2:
            continue
        base = m2.group(1)
        t = base if base[-1:] in "시구군" else base + "구"
        if t != sg and t in names[sd]:
            fake.append(f"{sd}-{sg} (→{t})")
    ck("선거구를 지역 페이지로 만들지 않는다", not fake, str(fake[:4]))

    # 일반구를 모시에 접지 않으면 모시에서 그 직위가 통째로 사라진다(성남시
    # 광역단체장 0건 · 교육감 0건 · 대선 2건).
    parents = collections.defaultdict(list)
    for sd, sg in sorted(keys):
        m2 = re.match(r"^(.+?시)(.+구)$", sg)
        if m2 and m2.group(1) in names[sd]:
            parents[(sd, m2.group(1))].append(sg)
    empty = []
    for (sd, pc), kids in sorted(parents.items()):
        rows = by.get((sd, pc)) or []
        if len(rows) < MIN_ROUNDS:
            continue
        # 광역단체장이 **시군구로 분해돼 오는 것은 5회 지선(2010)부터**다. 1~4회는
        # 시도 단위 한 행뿐이라 접을 하위 행이 아예 없다. 그래서 기준은 선거가
        # 있었던 해(1995)가 아니라 분해가 시작된 해다 — 1997년에 없어진 경남
        # 울산시를 이 검사로 잡으면 자료에 없는 것을 있으라고 요구하게 된다.
        if any(r["date"] >= "2010" for r in rows) and \
                "광역단체장" not in {r["office"] for r in rows}:
            empty.append(f"{sd}-{pc}(구 {len(kids)})")
    ck("하위 구를 가진 시에 광역단체장이 있다", not empty, str(empty[:4]))

    # 합산본과 직접 행이 겹치면 같은 표를 두 번 센다. **지금 자료에는 겹치는 것이
    # 없어 이 검사는 한 번도 발화하지 않는다** — 검증된 가드가 아니라 방어용이다.
    # 새 회차가 시 단위와 구 단위를 같이 내보내면 그때 걸린다.
    dupes = []
    for (sd, sg), rows in by.items():
        for k, cnt in collections.Counter((r["eid"], r["tc"]) for r in rows).items():
            if cnt > 1:
                dupes.append(f"{sd}-{sg} {k} x{cnt}")
    ck("같은 (회차, 직위) 행이 둘 이상이 아니다", not dupes, str(dupes[:4]))

    # ── 5. '표심' 대비 — 모르면 다르다고 하지 않는다 ────────────────────────
    # 이 지역 1위가 실제 당선자와 달랐는지를 표에 적는다. 실제 당선자를 모르는
    # 회차(전국 집계 행이 없는 옛 대선)는 아무 말도 하지 않아야 한다 — 시도별
    # 1위를 모아 전국 1위를 지어내면 그건 우리 계산이지 당선 사실이 아니다.
    # 접기 규칙은 containment.json에서 온다. 그 파일을 못 읽으면 fold_index가 조용히
    # 비어 모든 합산이 사라진다 — 페이지가 없어지는 게 아니라 행이 비는 방식이라
    # 눈에 안 띈다. 규칙 수를 직접 센다.
    fi = fold_index()
    ck(f"containment.json에서 접기 규칙을 읽었다 ({len(fi)}개)", len(fi) > 50, str(len(fi)))
    ck("선거구 하위 단위는 페이지를 만들지 않는다",
       any(not keep for _p, keep in fi.values()),
       "electoral_district 기록이 하나도 안 읽혔다")

    cmp_tc = {"1", "3", "11"}
    bad_scope = [f'{sd}-{sg} {r["eid"]} tc={r["tc"]}'
                 for (sd, sg), rows in by.items() for r in rows
                 if r.get("won_by") and r["tc"] not in cmp_tc]
    ck("기초단체장은 실제 당선자와 견주지 않는다", not bad_scope, str(bad_scope[:3]))

    # 견줄 수 있는 것이 실제로 있어야 검사가 산 검사다.
    cmp_rows = [r for _k, rows in by.items() for r in rows if r.get("won_by")]
    diff = [r for r in cmp_rows if r["won_by"] != r["name"]]
    ck(f"견줄 수 있는 행이 있다 ({len(cmp_rows):,}건)", len(cmp_rows) > 1000,
       str(len(cmp_rows)))
    ck(f"갈린 행이 있다 ({len(diff):,}건) — 0이면 검사가 죽은 것이다",
       0 < len(diff) < len(cmp_rows), str(len(diff)))

    # 손으로 확인한 사실 하나를 못 박는다. 2022 경기지사는 도 전체로 김동연이
    # 이겼지만 성남시 합산은 김은혜다 — 이 대비가 이 기능의 존재 이유다.
    sn = [r for r in (by.get(("경기도", "성남시")) or [])
          if r["eid"] == "8th-local-2022" and r["office"] == "광역단체장"]
    ck("성남시 2022 광역단체장: 지역 1위 김은혜 · 도 당선 김동연",
       len(sn) == 1 and sn[0]["name"] == "김은혜" and sn[0].get("won_by") == "김동연",
       str([(r["name"], r.get("won_by")) for r in sn]))

    # ── 6. 시도 층 ──────────────────────────────────────────────────────────
    bs = collect_sido(collect.won)
    ck(f"시도 페이지가 있다 ({len(bs)}곳)", len(bs) >= 17, str(len(bs)))

    # 광역단체장·교육감은 시도가 선거구 자체라 이 행이 곧 당선 결과다. 견줄 상대가
    # 없는데 won_by를 채우면 '당선자와 다르다'는 없는 사실이 생긴다.
    bad = [f'{sd} {r["eid"]} {r["office"]}' for sd, rows in bs.items() for r in rows
           if r["tc"] in ("3", "11") and r.get("won_by")]
    ck("시도의 광역단체장·교육감은 견줄 상대를 갖지 않는다", not bad, str(bad[:3]))

    # 대통령은 견준다 — 0이면 기능이 아니라 검사가 죽은 것이다.
    pres = [r for rows in bs.values() for r in rows if r["tc"] == "1"]
    diff = [r for r in pres if r.get("won_by") and r["won_by"] != r["name"]]
    ck(f"시도 대선이 전국 당선자와 견줘진다 ({len(diff)}/{len(pres)}건 갈림)",
       0 < len(diff) < len(pres), f"{len(diff)}/{len(pres)}")

    # 손으로 확인한 사실: 2022 대선에서 경기도 1위는 이재명, 전국 당선은 윤석열.
    gg = [r for r in (bs.get("경기도") or [])
          if r["eid"] == "20th-pres-2022" and r["tc"] == "1"]
    ck("경기도 2022 대선: 도 1위 이재명 · 전국 당선 윤석열",
       len(gg) == 1 and gg[0]["name"] == "이재명" and gg[0].get("won_by") == "윤석열",
       str([(r["name"], r.get("won_by")) for r in gg]))

    # 시도 페이지가 실재하고 시군구가 자기 시도로 올라갈 수 있어야 한다.
    made = {d.name for d in (ROOT / "region").iterdir()
            if d.is_dir() and "-" not in d.name}
    ck(f"시도 디렉터리가 만들어졌다 ({len(made)}곳)", len(made) >= 17, str(len(made)))
    no_up = [d.name for d in sorted((ROOT / "region").iterdir())
             if d.is_dir() and "-" in d.name
             and d.name.split("-", 1)[0] in made
             and f'/region/{quote(d.name.split("-", 1)[0])}/'
             not in (d / "index.html").read_text(encoding="utf-8")]
    ck("시군구가 자기 시도로 올라가는 링크를 갖는다", not no_up,
       f"{len(no_up)}개 — {no_up[:3]}")

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
