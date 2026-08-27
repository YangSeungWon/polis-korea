"""여론조사 적중률 데이터가 성립하는가 (data/polls/accuracy.json).

**막는 사고 셋.**

1. **인용 의무 누락.** 특정 조사를 인용하면 의뢰자·기관·조사기간·표본수·응답률·
   표본오차를 함께 표시해야 한다(공직선거법·NESDC, data/polls/README.md). 이 데이터의
   행 하나하나가 조사 한 건을 인용하므로, 표를 만들기 **전에** 여기서 막는다. 나중에
   붙이면 어긋난다 — 페이지가 이미 "정당·후보자 본인 의뢰 조사는 제외됩니다"라고
   적어 두고도 그 필터가 계산에 들어갔는지는 아무도 안 보고 있었다.

2. **계열을 줄세우기.** 총선은 지역구, 대선은 시도 1위, 지선은 광역단체장을 센다.
   unit이 비면 허브의 회차 간 표가 단위 없이 숫자만 나란히 놓게 되고, 20대 대선
   13/17이 '여론조사가 틀렸다'로 읽힌다(실제로는 박빙 시도가 많았다는 뜻).

3. **셈이 안 맞음.** match > total 같은 것.

실행: .venv/bin/python tests/test_poll_accuracy.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "build"))
import poll_accuracy as PA  # noqa: E402

SRC = ROOT / "data" / "polls" / "accuracy.json"
# 인용 의무 항목 중 **반드시 값이 있어야** 하는 것. source_url·ntt_id는 추적용이고,
# co_agency 같은 것은 없을 수 있다.
REQUIRED = ("agency", "requester", "sample_size", "response_rate",
            "sample_error", "period_start", "period_end")

fails: list[str] = []


def bad(msg: str) -> None:
    fails.append(msg)
    print(f"  ✗ {msg}")


def main() -> int:
    print("여론조사 적중률 데이터")
    if not SRC.is_file():
        bad("data/polls/accuracy.json이 없다 — build_poll_accuracy를 안 돌렸다")
        return 1
    d = json.loads(SRC.read_text(encoding="utf-8"))
    els = d.get("elections") or {}
    if len(els) < 9:
        bad(f"회차 {len(els)}개 — election_index의 9개보다 적다")

    n_rows = n_cited = 0
    for slug, e in sorted(els.items()):
        offices = e.get("offices") or {}
        if not offices:
            bad(f"{slug}: 직위가 하나도 없다")
        for off, o in offices.items():
            if not o.get("unit"):
                bad(f"{slug}/{off}: unit이 없다 — 계열마다 세는 단위가 다르다")
            rows = o.get("rows") or []
            hits = [r for r in rows if r.get("hit") is not None]
            if o.get("total") != len(hits):
                bad(f"{slug}/{off}: total {o.get('total')} ≠ 비교 가능한 행 {len(hits)}")
            if (o.get("match") or 0) > (o.get("total") or 0):
                bad(f"{slug}/{off}: match {o['match']} > total {o['total']}")
            for r in rows:
                n_rows += 1
                if r.get("hit") is None:
                    continue          # 비교 못 한 행은 조사를 인용하지 않는다
                c = r.get("cite")
                if not c:
                    bad(f"{slug}/{off}/{r['region']}: 조사를 인용하는데 cite가 없다")
                    continue
                n_cited += 1
                miss = [k for k in REQUIRED if c.get(k) in (None, "")]
                if miss:
                    bad(f"{slug}/{off}/{r['region']}: 인용 의무 항목 없음 — {', '.join(miss)}")
                if len(fails) > 8:
                    print("  … 이하 생략")
                    return 1
    print(f"  회차 {len(els)} · 행 {n_rows} · 조사를 인용하는 행 {n_cited}")

    # 교육감은 정당을 표방하지 않는다 — 비교할 정당이 없으니 0이 맞다. '데이터가
    # 없다'와 '없는 게 맞다'를 구분해 둔다(docs/absence.md).
    for slug, e in els.items():
        edu = (e.get("offices") or {}).get("교육감")
        if edu and edu.get("total"):
            bad(f"{slug}: 교육감 적중률이 {edu['total']}건 있다 — 교육감은 정당이 없다")

    # 감쇠 기준이 선거일이라 값이 시각에 불변인가 — 다시 만들어 같은지 본다.
    if not fails:
        P = PA.Parties()
        if P.canon("민주당", "2026-06-03") != "더불어민주당":
            bad("정당 동음이의 해소가 깨졌다 — '민주당'@2026이 더불어민주당이 아니다")
        if P.canon("민주당", "1956-05-15") == "더불어민주당":
            bad("동음이의를 시점 무시하고 합쳤다 — '민주당'@1956")

    if fails:
        print(f"\n실패 {len(fails)}건")
        return 1
    print("통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
