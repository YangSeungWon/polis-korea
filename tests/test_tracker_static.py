"""요약 수치는 **산출방식과 떨어질 수 없다**.

`국정수행 긍정 50.2%`만 떼어 보면(검색 스니펫·공유·스크린샷) polis의 자체 집계나
최신 단일 조사로 읽힌다. 실제로는 서로 다른 기관·기간·방법론을 단순평균한 값이고,
그 평균 자체가 또 하나의 방법론이다. 그러니 값과 같은 자리에 있어야 한다.

이 검사는 문구를 고정하지 않는다 — **수치가 있으면 산출방식도 있는가**만 본다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fails: list = []


def ck(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        fails.append(name)
        print(f"  ✗ {name}{' — ' + detail if detail else ''}")


html = (ROOT / "tracker.html").read_text(encoding="utf-8")
m = re.search(r"TK_STATIC_START.*?TK_STATIC_END", html, re.S)
ck("tracker에 정적 요약 블록이 있다", bool(m))
if m:
    blk = m.group(0)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", blk))
    nums = re.findall(r"\d+\.\d+%", text)
    ck("요약에 실제 수치가 있다 (JS 없이 읽히는가)", len(nums) >= 2, str(nums[:4]))
    if nums:
        # 값이 있으면 방식도 있어야 한다. 셋 중 하나라도 빠지면 숫자가 홀로 남는다.
        ck("산출방식이 같은 블록에 있다", "단순평균" in text, text[:120])
        ck("몇 건을 평균했는지 밝힌다", bool(re.search(r"최근 \d+개 조사", text)))
        ck("기준 시점이 있다", bool(re.search(r"\d{4}-\d{2}-\d{2}", text)))
        # 우리가 보정한 값이 아니라는 것 — 있는 그대로를 옮겼다는 진술
        ck("보정 여부를 밝힌다", "보정" in text or "가중" in text)
        ck("기관 차이를 밝힌다", "house effect" in text or "기관마다" in text)

print(f"\n[지지율 요약 정합] 실패 {len(fails)}")
sys.exit(1 if fails else 0)
