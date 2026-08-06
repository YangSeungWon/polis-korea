"""템플릿별 **얇음·중복** 감사 — 미색인의 후보를 저장소에서 먼저 좁힌다.

Search Console의 `크롤링됨 - 현재 색인이 생성되지 않음`을 유형별로 나누려면 콘솔
접근이 필요하지만, **어느 템플릿이 위험한가**는 저장소에서 먼저 잴 수 있다.
Google이 별도 색인할 가치를 판단하는 실질 근거가 본문의 양과 고유성이기 때문이다.

재는 것은 둘뿐이다:

    본문 길이   JS를 뺀 정적 <main> 텍스트 (크롤러가 처음 보는 것)
    본문 중복   같은 텍스트를 가진 페이지 수 (이름만 바뀐 껍데기)

**목표는 5천 페이지를 전부 색인시키는 게 아니다.** 얇은 템플릿이 나오면 선택지는
셋이다 — 실제 내용을 더 싣거나, 상위 문서로 canonical하거나, noindex한다.
지금 상태를 모르면 그 셋 중 무엇도 근거 있게 고를 수 없다.

사용: python scripts/audit/audit_seo_templates.py [--list person]
"""
from __future__ import annotations

import collections
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {"node_modules", ".git", ".venv", "og", "assets", "data", "scripts",
        "tests", "docs", "share"}
TEMPLATES = ("person/", "region/", "party/", "archive/", "history/", "polls/")
THIN = 300          # 이보다 짧으면 '이 문서만의 내용'이 거의 없다고 본다


def template_of(p: Path) -> str:
    s = str(p)
    for k in TEMPLATES:
        if s.startswith(k):
            return k.rstrip("/")
    return "top"


def body_text(html: str) -> str:
    m = re.search(r"<main.*?</main>", html, re.S)
    b = m.group(0) if m else html
    t = re.sub(r"<script.*?</script>", "", b, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()


def scan() -> dict:
    rows: dict = collections.defaultdict(list)
    for p in sorted(ROOT.rglob("*.html")):
        rel = p.relative_to(ROOT)
        if any(x in rel.parts for x in SKIP):
            continue
        try:
            html = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        t = body_text(html)
        rows[template_of(rel)].append({
            "path": str(rel), "chars": len(t),
            "links": len(re.findall(r"<a [^>]*href", html)),
            "hash": hashlib.md5(t.encode()).hexdigest()[:10],
        })
    return rows


def main(argv: list) -> int:
    rows = scan()
    want = argv[argv.index("--list") + 1] if "--list" in argv else None
    print(f"{'template':10}{'n':>6}{'중앙':>7}{'하위25%':>8}"
          f"{'<'+str(THIN)+'자':>8}{'중복':>6}  판단")
    for k, v in sorted(rows.items(), key=lambda kv: -len(kv[1])):
        lens = sorted(x["chars"] for x in v)
        med, q1 = lens[len(lens) // 2], lens[len(lens) // 4]
        thin = sum(1 for x in lens if x < THIN)
        dup = len(v) - len({x["hash"] for x in v})
        note = []
        if thin > len(v) * 0.4:
            note.append(f"얇음 {thin / len(v):.0%}")
        if dup > len(v) * 0.3:
            note.append(f"본문 중복 {dup}")
        print(f"{k:10}{len(v):6}{med:7}{q1:8}{thin:8}{dup:6}  "
              + (" · ".join(note) or "—"))
    if want and want in rows:
        print(f"\n[{want}] 가장 얇은 20개")
        for x in sorted(rows[want], key=lambda r: r["chars"])[:20]:
            print(f"  {x['chars']:5}자 링크{x['links']:3}  {x['path']}")
    print("\n얇거나 중복인 템플릿은 셋 중 하나를 골라야 한다 — "
          "내용을 더 싣기 / 상위로 canonical / noindex.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
