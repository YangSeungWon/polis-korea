"""무투표 당선(uncontested) 플래그 일괄 부여 — 단독후보·득표0 race.

무투표 당선 = 후보 1명·개표 없음(votes=0). 지선 5회+·총선 제헌 등에서 발생.
NEC 데이터엔 race로 존재하나 is_uncontested 플래그가 빠진 경우가 있어 렌더가 '0.0%'로
표시됨 → 단독후보+votes0이면 is_uncontested=True·후보 won/uncontested=True 부여.

주의: 1~4회 지선 단독후보는 votes>0(당시 무투표 제도 없어 투표 시행, 유효표 100%)이라
대상 아님. votes==0 조건이 이를 자동 배제(권위 nec_uncontested 캐시와도 일치 — 검증됨).

대상 office: 지선 tc3/4(광역·기초장), 총선 scope=district. (광역/기초의원 tc5/6은 옛 회차가
당선자명부라 단독≠무투표 → 제외.)

사용: python3 scripts/build/flag_uncontested.py
"""
from __future__ import annotations
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"


def is_target(r):
    # 단체장(광역3·기초4) + 국회의원 지역구. 지선 광역/기초의원(tc5·6)은 옛 회차 당선자명부라
    # 단독≠무투표 → scope=district여도 제외.
    tc, scope = r.get("sg_typecode"), r.get("scope")
    if tc in ("5", "6"):
        return False
    return tc in ("2", "3", "4") or scope == "district"


def main():
    files = sorted(set(glob.glob(str(RESULTS / "*-local-*.json")) +
                       glob.glob(str(RESULTS / "*-general-*.json"))))
    total = 0
    for p in files:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        if not isinstance(d, dict) or "races" not in d:
            continue
        changed = 0
        for r in d["races"]:
            if not is_target(r):
                continue
            cs = r.get("candidates", [])
            if len(cs) == 1 and cs[0].get("votes", 0) == 0 and not r.get("is_uncontested"):
                r["is_uncontested"] = True
                cs[0]["uncontested"] = True
                cs[0]["won"] = True
                changed += 1
        if changed:
            Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {Path(p).name}: +{changed}")
            total += changed
    print(f"신규 무투표 플래그: {total}")


if __name__ == "__main__":
    main()
