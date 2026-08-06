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

# ── 같은 이름의 다른 정당을 한 덩어리로 세지 않는가 ─────────────────────────
# 원자료의 '국민의당'은 1963·2016·2020이 다 그 이름이다. 그대로 세면 1963~2022에
# 걸친 35M표짜리 한 정당이 생기고, registry의 괄호 표기와도 안 맞아 그쪽은 빈다.
import json as _j  # noqa: E402

_reg = _j.loads((ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"]
_disamb = [p for p in _reg if "(" in p]
_got = [p for p in _disamb if runs.get(p)]
ck(f"괄호로 구분된 정당도 출마 기록을 받는다 ({len(_got)}/{len(_disamb)})",
   len(_got) >= len(_disamb) * 0.7, str(sorted(set(_disamb) - set(_got))[:5]))

# 활동 기간이 비현실적으로 길면 동음이의가 한 덩어리로 세어진 형태다.
#
# **registry에 있는 정당만 세운다.** 미등록 이름(국민당 1958~2026 등)은 우리가
# 갈라 놓지 않아서 뭉친 것이고, 정식명·창당 시점을 자료로 확인하기 전에는 나눌 수
# 없다. 지어내는 대신 보고만 한다 — 다음에 registry를 채울 때의 목록이 된다.
_kh = _j.loads((ROOT / "data/parties/known_homonyms.json").read_text(encoding="utf-8"))
_known = {x["name"] for x in _kh["unresolved"]}
ck("알려진 동음이의에 사유가 있다",
   all(x.get("note") and x.get("span") for x in _kh["unresolved"]))
_conflated = []
for _p, _rs in runs.items():
    if len(_rs) < 2:
        continue
    _y = [int(r["date"][:4]) for r in _rs]
    if max(_y) - min(_y) <= 60:
        continue
    if _p in _known:
        continue                      # 아직 못 가른 것으로 **명시**된 항목
    if _p in _reg:
        ck(f"{_p}: 활동 기간이 한 정당의 것이다 ({min(_y)}~{max(_y)})", False,
           "registry에 있는데 동음이의가 섞였다 — 갈라 놓거나 "
           "known_homonyms.json에 근거와 함께 적어야 한다")
    else:
        _conflated.append((_p, min(_y), max(_y), sum(r["votes"] for r in _rs)))
if _conflated:
    print("\n  [미등록 동음이의 후보] registry에 넣을 때 시점으로 갈라야 한다")
    for _p, _a, _b, _v in sorted(_conflated, key=lambda x: -x[3])[:8]:
        print(f"    {_p:16} {_a}~{_b}  {_v:,}표")

print(f"\n[정당 페이지 내용] 실패 {len(fails)}")
sys.exit(1 if fails else 0)
