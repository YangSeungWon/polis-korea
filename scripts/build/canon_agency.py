"""data/polls/*.json의 조사기관(agency) 표기 정규화 — `(주)`·`주식회사`·`㈜` 제거.

NESDC 메타 CSV의 agency가 같은 기관을 '(주)리얼미터'/'리얼미터'처럼 둘로 표기해,
tracker house-effect가 한 기관을 두 버킷으로 쪼개 보정이 희석된다. 빌드/추출 산출물을
일괄 후처리해 통일한다(여러 빌더가 m.get("agency")를 그대로 쓰므로 출력단에서 한 번에).

idempotent — daily/tracker 파이프라인 commit 직전 단계로 넣고, 1회 백필로도 쓴다.
사용: python scripts/build/canon_agency.py [--check]
"""
from __future__ import annotations
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLLS = ROOT / "data" / "polls"

# '(주)' '( 주 )' '㈜' '주식회사' + 깨진 '주)'(여는 괄호 유실) + 꺾쇠 '<>' 제거 → 공백 정리.
#   기관명 안의 의미있는 괄호(예: 모노리서치)는 보존.
_STRIP = re.compile(r"㈜|\(\s*주\s*\)|주\s*\)|주식회사|[<>]")

# 같은 회사 다른 표기 별칭 맵 (variant → canonical). house-effect가 한 기관을 여러 버킷으로
#   쪼개지 않게 통일. canonical은 데이터 내 우세 표기. (주)·꺾쇠 제거 후 적용.
#   * 다른 회사는 절대 병합 금지: 에브리리서치≠에브리미디어≠에브리씨앤알, 마크로밀엠브레인≠엠브레인퍼블릭,
#     미디어리서치≠미디어토마토≠미디어리얼리서치코리아.
_ALIASES = {
    "메트릭스코퍼레이션": "메트릭스",
    "모노커뮤니케이션즈": "모노커뮤니케이션즈(모노리서치)",
    "비전코리아솔루션즈": "비전코리아",
    "서던포스트알앤씨": "서던포스트",
    "칸타코리아(칸타 퍼블릭)": "칸타코리아",
    "코리아정보리서치 중부본부": "코리아정보리서치",
    "한국CNR/케이엠 조사연구소": "한국CNR",
    "한국CNR/케이엠조사연구소": "한국CNR",
    "한길리서치센타": "한길리서치",
    "넥스트인터랙티브리서치(넥스트리서치)": "넥스트리서치",
    "한국사회여론연구소(KSOI)": "케이에스오아이 (한국사회여론연구소)",
    "리서치DNA": "리서치디앤에이",
}


def canon_agency(s: str) -> str:
    if not s:
        return s
    out = re.sub(r"\s+", " ", _STRIP.sub("", s)).strip()
    return _ALIASES.get(out, out)


def _records(d):
    """파일 내 폴/레코드 리스트를 반환(없으면 None)."""
    if isinstance(d, dict):
        for k in ("polls", "records"):
            if isinstance(d.get(k), list):
                return d[k]
    return None


def main():
    check = "--check" in sys.argv
    total_files = total_changed = 0
    for fp in sorted(glob.glob(str(POLLS / "*.json"))):
        name = Path(fp).name
        if "scancache" in name or "election_index" in name:
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        recs = _records(d)
        if not recs:
            continue
        changed = 0
        for r in recs:
            a = r.get("agency")
            if a:
                c = canon_agency(a)
                if c != a:
                    r["agency"] = c
                    changed += 1
        if changed:
            total_changed += changed
            total_files += 1
            if check:
                print(f"  {name}: {changed}건 정규화 필요")
            else:
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
                print(f"  {name}: {changed}건 정규화")
    verb = "필요" if check else "완료"
    print(f"총 {total_changed}건 / {total_files}개 파일 {verb}")
    if check and total_changed:
        sys.exit(1)


if __name__ == "__main__":
    main()
