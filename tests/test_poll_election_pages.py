"""회차별 여론조사 페이지가 **서로 다른 문서**인가.

9개 `/polls/{id}/`는 공용 템플릿에서 title·canonical만 바꿔 굽는다. 회차 고유 내용이
JS에만 있으면 크롤러에게는 **같은 페이지 9개**로 보인다 — 실제로 정적 본문이 1,228자
그대로 똑같았다(고유 본문 1/9).

그리고 이 실패는 조용하다. 삽입할 블록이 빈 문자열이면 마커만 지워지고 길이도 그대로라
아무 티가 안 난다(그렇게 한 번 놓쳤다). 그래서 **비어 있지 않은가**를 따로 본다.

'저장소에 파일이 있다'와 '현행 생성기가 재현한다'는 다르다 — 재생성 후에도 성립해야 한다.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fails: list = []


def ck(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        fails.append(name)
        print(f"  ✗ {name}{' — ' + detail if detail else ''}")


idx = json.loads((ROOT / "data/polls/election_index.json").read_text(encoding="utf-8"))
slugs = [e["slug"] for e in idx]
ck("election_index가 비어 있지 않다", len(slugs) >= 2, str(len(slugs)))

bodies: dict = {}
for slug in slugs:
    f = ROOT / "polls" / slug / "index.html"
    ck(f"{slug}: 페이지가 있다", f.exists())
    if not f.exists():
        continue
    html = f.read_text(encoding="utf-8")
    m = re.search(r"<main.*?</main>", html, re.S)
    body = m.group(0) if m else html
    text = re.sub(r"\s+", " ",
                  re.sub(r"<[^>]+>", " ",
                         re.sub(r"<script.*?</script>", "", body, flags=re.S))).strip()
    bodies.setdefault(hashlib.md5(text.encode()).hexdigest(), []).append(slug)
    # 빈 블록은 마커만 지우고 티가 안 난다 — 내용이 실제로 들어갔는지 본다
    ck(f"{slug}: 회차 고유 블록이 비어 있지 않다", "pe-static" in html)
    ck(f"{slug}: 조사 건수가 적혀 있다", bool(re.search(r"조사 <b>[\d,]+건</b>", html)))
    ck(f"{slug}: 마커가 남아 있지 않다", "PE_STATIC" not in html)

dups = {h: v for h, v in bodies.items() if len(v) > 1}
ck(f"정적 본문이 회차마다 다르다 (고유 {len(bodies)}/{len(slugs)})", not dups,
   str(list(dups.values())[:2]))

print(f"\n[회차별 여론조사 페이지] 실패 {len(fails)}")
sys.exit(1 if fails else 0)
