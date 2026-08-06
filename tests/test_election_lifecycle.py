"""선거 상태가 **데이터와 어긋나지 않는가**.

홈이 8월에도 9회 지선(6-03)을 '진행'으로 표시하고 있었다. 결과 파일은 이미
`is_final: true`인데 `data/elections/9th-local-2026.json`의 `status`가 손으로 적은
`active`로 남아 있었기 때문이다 — **상태가 두 군데 있고 서로 어긋난 것**이다.

정치 데이터 제품에서 freshness는 장식이 아니다. 지난 선거를 '진행'이라고 말하는
화면은 나머지 숫자도 최신이 아닐 거라는 의심을 만든다.

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

print(f"\n[선거 상태 정합] 실패 {len(fails)}")
sys.exit(1 if fails else 0)
