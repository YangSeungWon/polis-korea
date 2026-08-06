"""기초의원 비례(tc9) 결손의 **의미**를 지킨다.

득표가 0인 데는 서로 다른 이유가 있고, 그걸 뭉개면 화면이 거짓말을 한다:

    무투표 당선  후보가 정수 이하라 투표를 안 했다 — 표심이 애초에 측정되지 않았다
    원인 미상    개표현황에도 무투표 명부에도 없다 — 왜인지 모른다
    자료 없음    수집을 안 했다 (5~8회가 그랬다 — 지금은 회수했다)

셋 다 '빈 칸'으로 보이지만 전혀 다른 사실이다.

## 왜 assertion보다 기준선이 필요했나

무투표 API 페이지 하나가 504였을 때, 스크립트가 조용히 끊고 나머지를 '무투표 아님'으로
남겨 8회가 61→12로 줄었다. 개별 assertion은 전부 통과한다 — 12곳도 '유효한' 값이다.
**직전 정상 결과 대비 급감**을 봐야 잡힌다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/fetch"))

RESULTS = ROOT / "data/results"
BASELINE = ROOT / "data/audits/council_prop_baseline.json"
EVENTS = ROOT / "data/geography/events.json"
fails: list = []


def ck(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        fails.append(f"{name}{' — ' + detail if detail else ''}")
        print(f"  ✗ {name}{' — ' + detail if detail else ''}")


def rows_of(fname: str) -> list:
    d = json.loads((RESULTS / fname).read_text(encoding="utf-8"))
    return [r for r in d.get("races", [])
            if r.get("sg_typecode") == "9" and r.get("scope") == "proportional_sigungu"]


def has_votes(r: dict) -> bool:
    return any(c.get("party") and (c.get("votes") or 0) > 0
               for c in (r.get("candidates") or []))


base = json.loads(BASELINE.read_text(encoding="utf-8"))["rounds"]

for n, b in sorted(base.items()):
    rows = rows_of(b["file"])
    votes = [r for r in rows if has_votes(r)]
    unc = [r for r in rows if r.get("uncontested")]
    unknown = [r for r in rows if not has_votes(r) and not r.get("uncontested")]
    tag = f"{n}회"

    # ① 무투표는 결손이 아니다 — 개표가 없는 게 정상이다
    ck(f"{tag}: 무투표 행에는 득표가 없다",
       not [r for r in unc if has_votes(r)],
       str([r["sigungu"] for r in unc if has_votes(r)][:3]))
    ck(f"{tag}: 무투표 행은 의석이 있다",
       all(any(c.get("seats") for c in (r.get("candidates") or [])) for r in unc))

    # ⑤ 결손 = 확인된 무투표 + 미상 (남거나 모자라면 어딘가 새고 있다)
    missing = [r for r in rows if not has_votes(r)]
    ck(f"{tag}: 결손 = 무투표 + 미상 ({len(missing)} = {len(unc)} + {len(unknown)})",
       len(missing) == len(unc) + len(unknown))

    # ⑥ 급감 감시 — 숫자를 고정하지 않되 절반 아래로 떨어지면 세운다
    ck(f"{tag}: 무투표 판정이 급감하지 않았다 ({len(unc)} vs 기준선 {b['uncontested']})",
       len(unc) >= b["uncontested"] * 0.5,
       "수집이 부분 실패했을 때 나타나는 형태다")
    ck(f"{tag}: 득표 커버리지가 급감하지 않았다 "
       f"({len(votes)} vs 기준선 {b['with_votes']})",
       len(votes) >= b["with_votes"] * 0.9)

    # 미상은 **찾아본 흔적**을 남긴다 — 같은 조사를 반복하지 않기 위해
    for r in unknown:
        ck(f"{tag} {r['sigungu']}: 미상에 provenance가 있다",
           bool(r.get("unknown_reason") and r.get("checked_sources")
                and r.get("last_verified")))

# ② 그 시점에 없던 이름이 결과 행으로 나타나지 않는다
evs = json.loads(EVENTS.read_text(encoding="utf-8"))["events"]
renames = [(e["from"][0]["parent"], e["from"][0]["name"], e["to"][0]["name"],
            e["effective_date"], e["id"])
           for e in evs
           if e.get("kind") == "admin_unit" and e.get("type") == "rename"
           and e.get("territorial_continuity") == "same"
           and len(e.get("from") or []) == 1 and len(e.get("to") or []) == 1]
ck("rename 이벤트가 하나는 있다", bool(renames))
for path in sorted(RESULTS.glob("*.json")):
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        continue
    date = (doc.get("_meta") or {}).get("election_date") or ""
    races = doc.get("races") or doc.get("district") or []
    if not date or not isinstance(races, list):
        continue
    for parent, old, new, eff, eid in renames:
        if date >= eff:
            continue
        bad = [r for r in races if isinstance(r, dict)
               and r.get("sido") == parent and r.get("sigungu") == new]
        ck(f"{path.name}({date}): 개칭 전인데 '{new}' 행이 없다 ← {eid}",
           not bad, f"{len(bad)}행 — 그 시점 이름은 '{old}'다")

# ③④ 수집 파이프라인의 성질 — 데이터가 아니라 **동작**을 검사한다
import fetch_council_prop_votes as F  # noqa: E402

# ④ 내부 행과 API 행이 같은 정규화를 거치는가
api = F.uncon_keys("강원도", "춘천시")            # API가 준 그 시점 이름
row = {"sido": "강원특별자치도", "sigungu": "춘천시"}   # 우리 행은 현행 표기
ck("시도 표기가 달라도 같은 곳으로 맞는다", F.is_uncontested(row, api))
ck("다른 곳까지 맞지는 않는다",
   not F.is_uncontested({"sido": "강원특별자치도", "sigungu": "원주시"}, api))
# 개칭·이관도 같은 함수가 처리한다
ck("개칭 전후 이름이 맞물린다",
   F.is_uncontested({"sido": "인천광역시", "sigungu": "미추홀구"},
                    F.uncon_keys("인천광역시", "남구")))

# ③ pagination 중 한 페이지라도 실패하면 publish하지 않는다
import urllib.request  # noqa: E402

import time as _t  # noqa: E402

_orig, _sleep = urllib.request.urlopen, _t.sleep
urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("504"))
_t.sleep = lambda *_a: None          # 재시도 대기까지 실제로 자면 검사가 36초 걸린다
try:
    F.fetch_uncontested("20220601")
    ck("API 부분 실패 시 중단한다", False, "예외 없이 진행했다 — 부분 결과가 확정된다")
except RuntimeError:
    ck("API 부분 실패 시 중단한다", True)
except Exception as e:                                           # noqa: BLE001
    ck("API 부분 실패 시 중단한다", False, f"다른 예외: {e!r}")
finally:
    urllib.request.urlopen, _t.sleep = _orig, _sleep

print(f"\n[기초비례 결손 의미] 실패 {len(fails)}")
sys.exit(1 if fails else 0)
