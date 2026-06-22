#!/usr/bin/env python3
"""공공데이터포털 중앙선관위 '투표율 분석' fileData(ZIP) 다운로드.

성별·연령대별 투표율(실측, 표본 투표구 기반)의 권위 소스. data.go.kr fileData는
로그인 없이 표준 fileDownload.do 엔드포인트로 받을 수 있다(atchFileId·fileDetailSn).
ZIP 안 '01_투표율분석결과(표본)/11-성별·연령대별 투표율(구시군별).xlsx'를
parse_turnout_demographics.py가 시도×성별×연령대 JSON으로 변환.

새 회차 추가: data.go.kr에서 해당 '투표율 분석' fileData 페이지 열어
  fn_fileDataDown(...) / atchFileId=FILE_... 추출해 ELECTIONS에 등록.

사용: python scripts/fetch/fetch_nec_turnout.py 21st-pres-2025
"""
from __future__ import annotations
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/raw/turnout"
DL = "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={atch}&fileDetailSn={sn}"

# 회차 → (atchFileId, fileDetailSn). data.go.kr 투표율분석 fileData 페이지에서 추출.
ELECTIONS = {
    # 제21대 대통령선거 투표율 분석 (data.go.kr/data/15156333)
    "21st-pres-2025": ("FILE_000000003560318", "1"),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ELECTIONS:
        print(f"usage: fetch_nec_turnout.py <election_id>\n  등록: {list(ELECTIONS)}", file=sys.stderr)
        sys.exit(2)
    eid = sys.argv[1]
    atch, sn = ELECTIONS[eid]
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / f"{eid}_turnout_analysis.zip"
    url = DL.format(atch=atch, sn=sn)
    print(f"다운로드: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    dst.write_bytes(data)
    print(f"→ {dst.relative_to(ROOT)} ({len(data):,} bytes)")
    print("다음: unzip 후 parse_turnout_demographics.py로 변환")


if __name__ == "__main__":
    main()
