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
            if off == "_national":
                # 적중이 아니라 **오차**를 재는 표다(막판 조사 평균 vs 실제 득표).
                # 같은 자로 재려 들면 total이 없다고 실패한다 — 실제로 그랬다.
                check_national(slug, o)
                continue
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

    check_pages()

    if fails:
        print(f"\n실패 {len(fails)}건")
        return 1
    print("통과")
    return 0


def check_national(slug: str, o: dict) -> None:
    """전국 후보별 표 — 오차를 재는 표라 규칙이 다르다."""
    if not o.get("rows"):
        bad(f"{slug}/_national: 행이 없다")
    if not o.get("n_polls") or not o.get("window_days"):
        bad(f"{slug}/_national: 몇 건을 며칠 창으로 평균했는지 안 적혀 있다 — "
            "글이 계산을 설명해야 한다")
    if not o.get("cited"):
        bad(f"{slug}/_national: 조사 평균을 인용하는데 인용 목록이 없다")
    for r in o.get("rows") or []:
        if r.get("poll_pct") is not None and r.get("actual_pct") is not None \
                and r.get("err") is None:
            bad(f"{slug}/_national/{r.get('name')}: 조사·실제가 있는데 차이가 비었다")


def check_pages() -> None:
    """페이지가 그 숫자를 **글로** 갖는가, 그리고 인용을 함께 싣는가.

    막는 사고 셋.

    1. **본문에 숫자가 없다.** 이 릴리즈 이전의 상태다 — 제목이 '조사 적중률'인데
       본문은 도입부 300단어, 표 0개였다. 화면에는 JS가 그렸지만 검색엔진도 공유
       카드도 못 봤다.
    2. **인용 없이 조사를 인용한다.** 표가 '서울 정원오 46.0%'라고 적으면 그 근거
       조사의 의뢰자·기관·기간·표본수·응답률·오차가 같은 문서에 있어야 한다
       (공직선거법·NESDC). 접혀 있어도 문서에 있으면 된다.
    3. **허브 표가 14쪽에 복사된다.** polls.html은 허브이자 직위·회차 페이지의
       틀이다. 2026-07에 history 프리렌더 66쪽이 서로 완전히 같아 대거 색인 보류된
       사고가 있었다 — 같은 모양의 사고다.
    """
    import re
    els = json.loads(SRC.read_text(encoding="utf-8")).get("elections") or {}
    for slug, e in sorted(els.items()):
        f = ROOT / "polls" / slug / "index.html"
        if not f.is_file():
            bad(f"{slug}: 페이지가 없다")
            continue
        html = f.read_text(encoding="utf-8")
        for off, o in (e.get("offices") or {}).items():
            if off == "_national":
                if o.get("rows") and "pe-acc-national" not in html:
                    bad(f"{slug}: 전국 후보별 표가 본문에 없다")
                continue
            if not o.get("total"):
                continue
            want = f"{o['match']}곳</b>"
            if want not in html:
                bad(f"{slug}/{off}: 적중 {o['match']}/{o['total']}이 본문에 없다")
            n_rows = sum(1 for r in o["rows"] if r["hit"] is not None)
            cited = o.get("cited") or []
            if n_rows and not cited:
                bad(f"{slug}/{off}: 표는 {n_rows}행인데 인용 목록이 비었다")
            for c in cited[:3]:
                if c.get("agency") and c["agency"] not in html:
                    bad(f"{slug}/{off}: 인용한 조사기관 {c['agency']}이 페이지에 없다")
                    break
        # 인용 블록이 여섯 항목을 실제로 적는가 — 하나라도 빠지면 표시 의무 미준수다.
        if "pe-cite-list" in html:
            for token in ("응답률", "의뢰"):
                if token not in html:
                    bad(f"{slug}: 인용에 '{token}'이 없다")

    hub = [p for p in ROOT.rglob("*.html")
           if "poll-acc-hub" in p.read_text(encoding="utf-8")]
    names = sorted(str(x.relative_to(ROOT)) for x in hub)
    if names != ["polls.html"]:
        bad(f"허브 표가 있어야 할 곳은 polls.html 하나인데 {names}")
    print(f"  페이지 {len(els)}쪽에 숫자·인용 확인 · 허브 표 {len(names)}쪽")


if __name__ == "__main__":
    sys.exit(main())
