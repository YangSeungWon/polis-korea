"""선거 상태가 **데이터와 어긋나지 않는가**.

홈이 8월에도 9회 지선(6-03)을 '진행'으로 표시하고 있었다. 결과 파일은 이미
`is_final: true`인데 `data/elections/9th-local-2026.json`의 `status`가 손으로 적은
`active`로 남아 있었기 때문이다 — **상태가 두 군데 있고 서로 어긋난 것**이다.

정치 데이터 제품에서 freshness는 장식이 아니다. 지난 선거를 '진행'이라고 말하는
화면은 나머지 숫자도 최신이 아닐 거라는 의심을 만든다.

## 상태는 셋이고, 서로 다른 것을 말한다

    {id}.json status        선거 생애 — 진행 중인가 끝났는가
    results _meta.is_final  개표 자료가 확정인가
    index.json active       **수집 대상**인가 (NESDC 일일 스캔·sitemap 주기)

세 번째가 특히 헷갈린다. `active`라는 이름 때문에 '선거 진행 중'으로 읽히지만
실제 의미는 '아직 수집할 게 남았다'다. 선거가 끝나도 한동안 수집이 이어질 수 있고,
그건 모순이 아니라 **다른 축**이다. 이 검사는 그 경우 명시적으로 적게만 한다.

상태 축:  예정 → 투표일 → 개표 중 → 잠정 → 확정

이 검사는 라벨을 고정하지 않는다. **모순만** 잡는다:
  · 결과가 확정(is_final)인데 status=active일 수 없다
  · 선거일이 한참 지났는데 status=active일 수 없다
  · 아직 오지 않은 선거가 '확정'일 수 없다
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ELECTIONS = ROOT / "data/elections"
RESULTS = ROOT / "data/results"
# 선거 후 이 기간이 지나도 active면 손으로 안 넘긴 것이다(개표·이의신청 여유 포함).
STALE_DAYS = 30
today = date.today()
fails: list = []


def ck(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        fails.append(f"{name}{' — ' + detail if detail else ''}")
        print(f"  ✗ {name}{' — ' + detail if detail else ''}")


for f in sorted(ELECTIONS.glob("*.json")):
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        continue
    if not isinstance(d, dict) or not d.get("date"):
        continue
    eid, when, status = f.stem, d["date"], d.get("status")
    ar = d.get("archive") if isinstance(d.get("archive"), dict) else {}
    label = ar.get("list_label")
    try:
        eday = date.fromisoformat(when)
    except ValueError:
        continue

    # 결과 파일의 확정 여부 — 이게 사실이고 status는 표기다
    rp = RESULTS / f"{eid}.json"
    is_final = None
    if rp.exists():
        try:
            is_final = (json.loads(rp.read_text(encoding="utf-8")).get("_meta") or {}
                        ).get("is_final")
        except Exception:                                        # noqa: BLE001
            pass

    if is_final is True:
        ck(f"{eid}: 결과가 확정인데 status=active가 아니다", status != "active",
           f"status={status} · is_final=True")
        ck(f"{eid}: 결과가 확정인데 '진행' 라벨이 아니다", label != "진행",
           f"list_label={label}")
    if eday + timedelta(days=STALE_DAYS) < today:
        ck(f"{eid}: 선거일({when})이 {STALE_DAYS}일 넘게 지났는데 active가 아니다",
           status != "active", f"오늘 {today}")
    if eday > today:
        ck(f"{eid}: 아직 안 치른 선거가 '확정'이 아니다", label != "확정",
           f"선거일 {when}")

# index.active('수집 대상')와 status('선거 생애')는 다른 축이다 — 다만 **끝난 선거를
# 계속 수집한다면 그건 의도여야 한다.** 우연히 남아 있는 것과 구별되게 이유를 적게 한다.
idx = json.loads((ELECTIONS / "index.json").read_text(encoding="utf-8"))
for eid in idx.get("active", []):
    f = ELECTIONS / f"{eid}.json"
    if not f.exists():
        continue
    d = json.loads(f.read_text(encoding="utf-8"))
    # status를 명시적으로 끝났다고 적은 것만 본다. status 필드가 아예 없는 메타
    # (재보궐 등 다른 shape)까지 끌어들이면 검사가 사실이 아닌 것을 주장하게 된다.
    if d.get("status") != "archive":
        continue
    ck(f"{eid}: 끝난 선거를 계속 수집한다면 이유를 적는다",
       bool(d.get("collect_reason")),
       f"status={d.get('status')}인데 index.active에 있다 — "
       "수집을 멈추거나 collect_reason을 남긴다")

# 네 번째 축이 다시 index.active를 빌려 쓰지 못하게 한다.
#   status(끝났나) · is_final(확정인가) · active(더 수집하나) · date(앞으로 있나)
# 앞의 셋은 수집·자료 상태고 마지막은 일정이다. timeline이 active를 앵커로 쓰면
# '수집을 멈추면 미래 일정이 사라지는' 결합이 생긴다 — 실제로 그 구조였다.
src = (ROOT / "scripts/build/build_timeline.py").read_text(encoding="utf-8")
code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
ck("build_timeline이 index.active를 일정 앵커로 쓰지 않는다",
   'idx.get("active"' not in code and "idx.get('active'" not in code,
   "일정은 각 선거 메타의 date에서 읽는다")

# active가 비어 있는 것은 정상이다 — 지금 수집 중인 선거가 없다는 뜻일 뿐이다.
ck("index.json에 세 축의 뜻이 적혀 있다", bool(idx.get("_meaning")))

print(f"\n[선거 상태 정합] 실패 {len(fails)}")
sys.exit(1 if fails else 0)
