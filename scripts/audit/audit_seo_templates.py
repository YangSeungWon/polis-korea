"""템플릿별 **얇음·중복** 감사 — 미색인의 후보를 저장소에서 먼저 좁힌다.

Search Console의 `크롤링됨 - 현재 색인이 생성되지 않음`을 유형별로 나누려면 콘솔
접근이 필요하지만, **어느 템플릿이 위험한가**는 저장소에서 먼저 잴 수 있다.
Google이 별도 색인할 가치를 판단하는 실질 근거가 본문의 양과 고유성이기 때문이다.

재는 것은 셋이다:

    본문 길이   JS를 뺀 정적 <main> 텍스트
    자료 길이   <script type="application/json"> 등에 실려 렌더해야 보이는 내용
    본문 중복   같은 텍스트를 가진 페이지 수 (이름만 바뀐 껍데기)

**'자료 길이'를 따로 세는 이유** — 2026-08 이걸 안 세다가 결론을 틀리게 냈다.
인물 페이지의 6월 버전을 재니 정적 본문이 68자라 "빈 껍데기라서 색인이 안 됐다"고
읽었는데, 실제로는 내용이 `<script id="person-data">`에 다 있었고 Google은 그걸
**렌더해서 색인**했다(색인된 페이지의 검색 스니펫에 그 JSON에만 있던 득표율이
찍혀 있었다). 같은 시점 색인된 페이지와 안 된 페이지의 정적 본문이 똑같이 68자라,
정적 길이는 그 둘을 가르지 못한다.

그러니 정적 본문 68자는 두 가지를 뜻할 수 있고 대응이 다르다:

    68자 + 자료 0      진짜 빈 껍데기 — 실을 내용이 없다
    68자 + 자료 2KB    내용은 있고 렌더가 필요하다 — 정적화의 후보

정적 렌더가 유리한 건 여전히 맞다(렌더 비용 없이 읽힌다). 다만 **미색인의 원인으로
정적 길이를 지목하려면 자료 길이가 0인지 먼저 봐야 한다.**

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
    """렌더 없이 읽히는 텍스트. <script>는 뺀다 — 그건 data_len이 따로 센다."""
    m = re.search(r"<main.*?</main>", html, re.S)
    b = m.group(0) if m else html
    t = re.sub(r"<script.*?</script>", "", b, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()


def data_len(html: str) -> int:
    """렌더해야 보이는 내용의 양 — data script의 페이로드 길이.

    JSON-LD(구조화 데이터)는 뺀다. 그건 본문이 아니라 메타데이터라 '실을 내용이
    있느냐'는 질문에 답하지 않는다.
    """
    total = 0
    for m in re.finditer(r'<script([^>]*)>(.*?)</script>', html, re.S):
        attrs, payload = m.group(1), m.group(2)
        if "application/json" not in attrs:
            continue
        if "ld+json" in attrs:
            continue
        total += len(payload.strip())
    return total


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
            "path": str(rel), "chars": len(t), "data": data_len(html),
            "links": len(re.findall(r"<a [^>]*href", html)),
            "hash": hashlib.md5(t.encode()).hexdigest()[:10],
            "text": t,
        })
    return rows


def _unique_len(rows: list) -> dict:
    """페이지별 **고유 텍스트** 길이 — 그 템플릿의 상투구를 뺀 나머지.

    ⚠️ 처음엔 '모든 페이지의 공통 앞뒤'로 재려다 실패했다. 페이지는 첫 글자부터
    다르므로(이름·정당명) 공통 접두가 늘 비고, 결과가 전체 길이와 같아진다 —
    주석은 상투구를 뺀다고 하는데 실제로는 한 글자도 안 뺐다.

    상투구는 **위치가 아니라 빈도**로 찾는다: 그 템플릿 페이지의 80% 이상에 나오는
    토큰은 틀에서 온 것이다('출마 이력', '득표율', '소속 인물은 당선 국회의원 기준').
    남는 것이 그 페이지만의 사실이다.
    """
    import collections
    texts = {r["path"]: (r.get("text") or "") for r in rows}
    n = len(texts)
    if n < 3:
        return {p: len(t) for p, t in texts.items()}
    df: collections.Counter = collections.Counter()
    toks = {p: t.split() for p, t in texts.items()}
    for ts in toks.values():
        df.update(set(ts))
    boiler = {w for w, c in df.items() if c >= n * 0.8}
    return {p: sum(len(w) + 1 for w in ts if w not in boiler) for p, ts in toks.items()}


def main(argv: list) -> int:
    rows = scan()
    want = argv[argv.index("--list") + 1] if "--list" in argv else None
    print(f"{'template':10}{'n':>6}{'중앙':>7}{'하위25%':>8}"
          f"{'<'+str(THIN)+'자':>8}{'빈 껍데기':>9}{'중복':>6}  판단")
    for k, v in sorted(rows.items(), key=lambda kv: -len(kv[1])):
        lens = sorted(x["chars"] for x in v)
        med, q1 = lens[len(lens) // 2], lens[len(lens) // 4]
        thin = [x for x in v if x["chars"] < THIN]
        # ⚠️ '자료 0'만으로 빈 껍데기라 부르면 틀린다. 정당 페이지는 애초에 JSON을
        # 안 싣는데 145쪽이 전부 자료 0이라, 짧은 18쪽이 '빈 껍데기'로 찍혔다.
        # 그 18쪽엔 각자 다른 역사적 사실이 있었다(중복 0) — 짧은 이유는 그 정당의
        # 역사가 짧기 때문이고, 실을 게 없어서가 아니다.
        #
        # 그래서 **고유 텍스트**를 본다: 같은 템플릿 안에서 모두가 공유하는 앞뒤
        # (nav·푸터·안내문)를 빼고 남는 길이. 그게 0에 가까울 때만 빈 껍데기다.
        uniq = _unique_len(v)
        empty = sum(1 for x in thin if uniq.get(x["path"], x["chars"]) < 40)
        dup = len(v) - len({x["hash"] for x in v})
        note = []
        if len(thin) > len(v) * 0.4:
            note.append(f"얇음 {len(thin) / len(v):.0%}")
        if empty:
            note.append(f"빈 껍데기 {empty}")
        if dup > len(v) * 0.3:
            note.append(f"본문 중복 {dup}")
        print(f"{k:10}{len(v):6}{med:7}{q1:8}{len(thin):8}{empty:9}{dup:6}  "
              + (" · ".join(note) or "—"))
    if want and want in rows:
        print(f"\n[{want}] 가장 얇은 20개")
        u = _unique_len(rows[want])
        for x in sorted(rows[want], key=lambda r: r["chars"])[:20]:
            print(f"  {x['chars']:5}자(고유 {u.get(x['path'], 0):4}) 자료{x['data']:6} "
                  f"링크{x['links']:3}  {x['path']}")
    print("\n얇거나 중복인 템플릿은 셋 중 하나를 골라야 한다 — "
          "내용을 더 싣기 / 상위로 canonical / noindex.")
    print("'빈 껍데기'는 **고유 텍스트**(템플릿 공통 앞뒤를 뺀 나머지)가 40자 미만인 "
          "것이다. 짧다고 다 빈 게 아니다 — 정당 18쪽은 짧지만 각자 다른 사실을 "
          "갖고 있고 중복이 0이다. 그 정당의 역사가 짧은 것이지 실을 게 없는 게 아니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
