"""단독 출마(후보 1명·투표 시행) race의 득표율을 votes/투표수(찬성률)로 재계산.

1~4회 지선(1995~2006)은 무투표 당선 제도가 없어 단독후보도 투표를 시행 → 무효표(반대)가 존재.
백필 시 pct를 votes/유효후보합으로 계산해 단독후보가 100%로 나옴. 실제 의미는 votes/투표수
(찬성률) — 무효율 = 반대. 예) 2회 충남 홍성 이상선 votes/voted=42.2%(무효 57.8%).

대상: 단체장(tc3/4) 중 후보 1명·votes>0·voted>0·무투표 아님. (5~9회 단독은 votes=0 무투표라 제외.)
멱등.

사용: python3 scripts/build/recompute_single_candidate_pct.py
"""
from __future__ import annotations
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/results"


def main():
    total = 0
    for p in sorted(glob.glob(str(RESULTS / "*-local-*.json"))):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        if not isinstance(d, dict) or "races" not in d:
            continue
        changed = 0
        for r in d["races"]:
            if r.get("sg_typecode") not in ("3", "4"):
                continue
            cs = r.get("candidates", [])
            voted = r.get("voted", 0)
            if len(cs) == 1 and not r.get("is_uncontested") and cs[0].get("votes", 0) > 0 and voted > 0:
                c = cs[0]
                newpct = round(c["votes"] / voted * 100, 1)
                if c.get("pct") != newpct:
                    c["pct"] = newpct
                    c["single_candidate"] = True   # 단독 출마(투표 시행) 표시 — 찬성률
                    changed += 1
        if changed:
            Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {Path(p).name}: {changed}곳 재계산")
            total += changed
    print(f"단독 출마 찬성률 재계산: {total}")


if __name__ == "__main__":
    main()
