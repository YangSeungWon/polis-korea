"""국회 '지금' 의석 — 의원 명부(data/assembly/current.json)가 거짓을 말하지 않는가.

막는 사고:
  · 키 없이 받은 5줄 샘플이 '지금 의석'이 된다(재적 299 → 5).
  · 공석을 0석으로 숨기거나, 정원과 재적이 안 맞는데 그대로 낸다.
  · 지역구·비례 정원(254·46)을 넘는 명부 — 갈래를 잘못 읽었다.
  · 연락처·보좌진 같은 화면에 안 쓰는 개인 정보를 저장소에 쌓는다.
  · API가 낯선 정당명을 보내도 조용히 지나간다.
  · 홈 정적 시드와 파일이 갈린다(크롤러와 사람이 다른 숫자를 본다).

실행: .venv/bin/python tests/test_assembly_now.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / "data" / "assembly" / "current.json"
fails: list[str] = []


def ck(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    if not F.is_file():
        print("✗ data/assembly/current.json 없음")
        return 1
    d = json.loads(F.read_text(encoding="utf-8"))
    meta, ms = d["_meta"], d["members"]
    law = meta["seats_by_law"]

    print("\n[명부]")
    ck(f"재적 {d['seated']} = 명부 {len(ms)}", d["seated"] == len(ms))
    ck(f"재적 + 공석 = 정원 {law}", d["seated"] + d["vacant"] == law, f"{d['seated']}+{d['vacant']}")
    ck("공석은 0 이상(정원 초과 명부가 아니다)", d["vacant"] >= 0)
    ck("샘플(5줄)이 아니다 — 정원의 90% 이상", len(ms) >= law * 0.9, str(len(ms)))
    kinds = Counter(m["kind"] for m in ms)
    ck(f"지역구 ≤ 254 · 비례 ≤ 46 ({kinds['지역구']}·{kinds['비례대표']})",
       kinds["지역구"] <= 254 and kinds["비례대표"] <= 46 and set(kinds) <= {"지역구", "비례대표"}, str(kinds))
    ck("정당 합 = 재적", sum(n for _, n in d["party_seats"]) == d["seated"])
    ck("정당별 수 = 명부에서 센 수", dict(d["party_seats"]) == dict(Counter(m["party"] for m in ms)))
    ck("정당을 모르는 의원이 없다", all(m["party"] for m in ms))
    ck("의원 중복 없음(code)", len({m["code"] for m in ms}) == len(ms))

    print("\n[개인 정보]")
    allowed = {"name", "party", "kind", "district", "reelected", "code"}
    extra = {k for m in ms for k in m} - allowed
    ck("연락처·보좌진·약력을 남기지 않는다", not extra, str(extra))

    print("\n[정당명]")
    reg = json.loads((ROOT / "data/parties/registry.json").read_text(encoding="utf-8"))["parties"]
    obs: set = set()
    try:
        ob = json.loads((ROOT / "data/parties/observed.json").read_text(encoding="utf-8"))
        rows = ob.get("parties", ob) if isinstance(ob, dict) else ob
        obs = {o["name"] for o in rows if isinstance(o, dict) and "name" in o}
    except Exception:
        pass
    strange = [p for p, _ in d["party_seats"] if p != "무소속" and p not in reg and p not in obs]
    ck("정당명이 registry 또는 관측 목록에 있다", not strange, str(strange))

    print("\n[날짜·출처]")
    ck("받은 날짜가 있다", bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta.get("fetched") or "")))
    ck("받은 날짜가 미래가 아니다", (meta.get("fetched") or "9999") <= date.today().isoformat())
    ck("출처가 적혀 있다", "열린국회정보" in (meta.get("source") or ""))

    print("\n[홈 정적 시드]")
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<div class="status-now" id="status-asm-now">(.*?)</div>', html)
    ck("홈 국회 카드에 '지금' 줄", bool(m))
    if m:
        seed = dict(re.findall(r'<span class="leg-item">([^<]+?) <b>(\d+)</b></span>', m.group(1)))
        want = {p: str(n) for p, n in d["party_seats"]}
        if d["vacant"]:
            want["공석"] = str(d["vacant"])
        ck("시드 숫자 = 명부", seed == want, f"{seed} vs {want}")
        ck("시드에 기준일", meta["fetched"] in m.group(1))

    print(f"\n{'전부 통과' if not fails else f'실패 {len(fails)}'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
