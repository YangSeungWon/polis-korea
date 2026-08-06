"""정당 페이지가 **그 정당만의 사실**을 담는가.

'등장 선거'는 당선자 기준이라 원외 정당은 아무것도 안 나왔다. 녹색당은 7회 선거에
73명이 나와 85만표를 얻었는데 페이지에는 한 줄도 없었다(76자).
**당선되지 않았다는 것과 참여하지 않았다는 것은 다르다.**

이 검사는 길이를 기준으로 삼지 않는다 — 글자 수에는 최소 기준이 없고, 짧아도 고유한
사실이면 가치가 있다. 대신 **데이터에 출마 기록이 있는데 페이지에 없는가**를 본다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/build"))
fails: list = []


def ck(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        fails.append(name)
        print(f"  ✗ {name}{' — ' + detail if detail else ''}")


from build_party_pages import build_runs  # noqa: E402

runs = build_runs()
missing, checked = [], 0
for d in sorted((ROOT / "party").iterdir()):
    f = d / "index.html"
    if not d.is_dir() or not f.exists():
        continue
    name = d.name
    rec = runs.get(name)
    if not rec:
        continue
    checked += 1
    html = f.read_text(encoding="utf-8")
    if "pty-runs" not in html:
        missing.append(name)
ck(f"출마 기록이 있는 정당은 페이지에도 있다 ({checked}곳 확인)", not missing,
   str(missing[:5]))

# 원외 정당(당선 0)도 빠지지 않는가 — 여기가 원래 통째로 비던 자리다
outside = [p for p, rs in runs.items()
           if rs and sum(r["won"] for r in rs) == 0 and (ROOT / "party" / p).is_dir()]
if outside:
    got = [p for p in outside if "pty-runs" in (ROOT / "party" / p / "index.html").read_text(
        encoding="utf-8")]
    ck(f"당선 0인 정당도 출마 기록이 있다 ({len(got)}/{len(outside)})",
       len(got) == len(outside), str(sorted(set(outside) - set(got))[:5]))

# 같은 선거를 두 번 세지 않는가 — .sigungu·national_assembly_* 중복 표현
for p, rs in list(runs.items())[:200]:
    dates = [r["date"] for r in rs]
    ck(f"{p}: 같은 날짜를 두 번 세지 않는다", len(dates) == len(set(dates)),
       str([d for d in dates if dates.count(d) > 1][:2]))

print(f"\n[정당 페이지 내용] 실패 {len(fails)}")
sys.exit(1 if fails else 0)
