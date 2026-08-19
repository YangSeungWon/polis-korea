"""sitemap 자동 생성 — sitemap.xml(index) + 층별 sitemap-{층}.xml.

소스:
  - 정적 메인 페이지 (수동 list)
  - archive/{eid}/index.html (디렉토리 자동 스캔)
  - history 24 prerender (data/elections/index.json 또는 디렉토리 스캔)
  - byelection/, about/data-coverage/

lastmod: **페이지 내용이 마지막으로 바뀐 날** (data/sitemap_lastmod.json)

  내용 해시를 매니페스트에 들고 다닌다. 해시가 그대로면 날짜도 그대로고, 바뀐
  페이지만 오늘로 움직인다. git 커밋일을 쓰던 방식을 대체한 것이다 —
  커밋일은 그 질문의 **대리 지표**인데 깨지는 경로가 셋이었다:

    · CI의 actions/checkout이 기본 shallow(fetch-depth 1)라 git log가 비었다.
      그러면 조용히 오늘로 떨어져 **매일 4,980쪽이 전부 '오늘 수정됨'**이 됐다 —
      lastmod를 넣어서 벗어나려던 바로 그 상태다. 로컬은 전체 클론이라 제대로
      나와서 안 보였고, 매일 커밋마다 sitemap 4,981줄이 왕복했다.
    · 리베이스·squash가 커밋일을 바꾼다.
    · 대량 재빌드가 안 바뀐 페이지까지 건드린다.

  해시는 이 셋 어디에도 안 흔들린다. 그리고 diff가 작아져서 '생성물이 낡았나'
  신호가 다시 읽힌다.

  한계 하나: 내용을 바꿨다 되돌리면 날짜는 오늘로 남는다(해시를 현재 것만 들고
  있어서다). 실제보다 새로 잡히는 쪽이라 무해하다 — 크롤러가 한 번 더 올 뿐이다.

priority:
  1.0  /  (홈)
  0.9  주요 진입 (governor/mayor/byelection/history/timeline/polls)
  0.7  archive 활성 회차 (9th-local-2026)
  0.6  archive 옛 회차 / history prerender
  0.5  about·기타

사용: python3 scripts/build/build_sitemap.py
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://polis.ysw.kr"
TODAY = date.today().isoformat()


MANIFEST = ROOT / "data/sitemap_lastmod.json"

_LASTMOD_CACHE: dict | None = None
_MAN: dict | None = None
_SEEDED = 0            # 매니페스트에 없어서 새로 심은 수
_SEED_FROM_GIT = 0     # 그중 git 커밋일로 심은 수


def lastmod_map() -> dict:
    """경로 → 마지막 커밋일. git log 한 번으로 전부 뽑는다.

    페이지마다 git log를 부르면 4,300회 subprocess라 느리다. 그리고 이게 중요한 이유는
    따로 있다 — 예전엔 모든 URL의 lastmod를 빌드일(TODAY)로 찍었다. 매 빌드마다 4,288개가
    전부 '오늘 수정됨'이 되면 검색엔진은 lastmod 신호 자체를 무시하게 되고, 무엇이 실제로
    바뀌었는지 알 수 없어 크롤 우선순위가 잡히지 않는다.
    """
    global _LASTMOD_CACHE
    if _LASTMOD_CACHE is not None:
        return _LASTMOD_CACHE
    out: dict[str, str] = {}
    try:
        r = subprocess.run(
            # core.quotepath=false — 없으면 git이 한글 경로를 "person/\352\260..."로
            # 이스케이프해 내보낸다. 그러면 키가 절대 안 맞아 person/party/region
            # 4천여 개가 조용히 빌드일(TODAY)로 떨어진다 — lastmod를 넣은 뜻이 사라진다.
            ["git", "-c", "core.quotepath=false", "log", "--format=%cs", "--name-only",
             "--since=2024-01-01", "--",
             "person/", "party/", "archive/", "history/", "polls/", "region/"],
            cwd=ROOT, capture_output=True, text=True, timeout=120)
        cur = ""
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if len(line) == 10 and line[4] == "-" and line[7] == "-":
                cur = line          # 커밋일 (최신부터 내려온다)
            elif cur and line not in out:
                out[line] = cur     # 처음 만난 것이 가장 최근 커밋
    except Exception:
        pass
    _LASTMOD_CACHE = out
    return out




def manifest() -> dict:
    global _MAN
    if _MAN is None:
        try:
            _MAN = json.loads(MANIFEST.read_text(encoding="utf-8")).get("pages", {})
        except Exception:
            _MAN = {}
    return _MAN


def page_file(url: str) -> Path:
    """URL → 그 페이지의 파일. /x/ → x/index.html · /x.html → x.html · / → index.html

    **퍼센트 인코딩을 푼다.** 정당 URL만 인코딩돼 나가는데(/party/%EB%8D%94...),
    풀지 않으면 파일을 못 찾아 145쪽이 조용히 오늘로 떨어진다. 옛 git-커밋일
    방식도 같은 이유로 정당 페이지는 늘 오늘이었다 — 이 버그는 새로 생긴 게
    아니라 드러난 것이다.
    """
    u = unquote(url).strip("/")
    if not u:
        return ROOT / "index.html"
    return ROOT / u if u.endswith(".html") else ROOT / u / "index.html"


def lastmod_for(url: str) -> str:
    """URL → 그 페이지 **내용이** 마지막으로 바뀐 날.

    해시가 매니페스트와 같으면 저장된 날짜를 그대로 쓴다. 다르면 오늘 바뀐 것이다.
    매니페스트에 없으면(첫 도입·새 페이지) git 커밋일로 심고, 그것도 없으면 오늘.
    """
    global _SEEDED, _SEED_FROM_GIT
    fp = page_file(url)
    try:
        h = hashlib.sha1(fp.read_bytes()).hexdigest()[:12]
    except OSError:
        return TODAY
    rel = str(fp.relative_to(ROOT))
    m = manifest()
    prev = m.get(rel)
    if prev and prev.get("h") == h:
        return prev["d"]
    if prev:
        m[rel] = {"h": h, "d": TODAY}       # 내용이 바뀌었다
        return TODAY
    _SEEDED += 1
    d = lastmod_map().get(rel)              # 처음 보는 페이지 — git이 알면 그날로
    if d:
        _SEED_FROM_GIT += 1
    else:
        d = TODAY
    m[rel] = {"h": h, "d": d}
    return d



# 정적 메인 페이지
STATIC = [
    ("/", "daily", "1.0"),
    ("/governor/", "daily", "0.9"),
    ("/mayor/", "daily", "0.9"),
    ("/superintendent/", "daily", "0.9"),
    ("/byelection.html", "daily", "0.9"),
    ("/byelection/", "weekly", "0.8"),
    ("/elections.html", "weekly", "0.9"),
    ("/history.html", "weekly", "0.9"),
    ("/timeline.html", "weekly", "0.8"),
    ("/polls.html", "daily", "0.8"),
    ("/tracker.html", "daily", "0.8"),
    ("/party/", "weekly", "0.7"),
    ("/parties.html", "weekly", "0.7"),
    ("/chronology.html", "weekly", "0.6"),
    ("/about/data-coverage/", "weekly", "0.5"),
]


def archive_urls() -> list[tuple[str, str, str]]:
    out = []
    arch_root = ROOT / "archive"
    active = set()
    try:
        idx = json.loads((ROOT / "data/elections/index.json").read_text(encoding="utf-8"))
        active = set(idx.get("active", []))
    except Exception:
        pass
    for d in sorted(arch_root.iterdir()):
        if not (d / "index.html").exists():
            continue
        eid = d.name
        meta_path = ROOT / f"data/elections/{eid}.json"
        # lastmod = 페이지 수정일. results_fetched_at(있으면) → 없으면 index.html git 커밋일.
        #   선거일(m["date"])은 역사적 날짜라 lastmod 부적합(웹 이전 → Search Console 거부).
        lastmod = None
        if meta_path.exists():
            try:
                m = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(m, dict) and isinstance(m.get("archive"), dict):
                    fetched = m["archive"].get("results_fetched_at")
                    if fetched and str(fetched)[:4] >= "2024":
                        lastmod = str(fetched)[:10]
            except Exception:
                pass
        if not lastmod:
            lastmod = lastmod_for(f"/archive/{eid}/")
        priority = "0.7" if eid in active else "0.6"
        freq = "daily" if eid in active else "monthly"
        out.append((f"/archive/{eid}/", freq, priority, lastmod))
    return out


def history_urls() -> list[tuple[str, str, str]]:
    """history/{type}/{n}/[office]/ prerender 디렉토리 스캔."""
    out = []
    hroot = ROOT / "history"
    if not hroot.exists():
        return out
    for p in sorted(hroot.rglob("index.html")):
        rel = p.relative_to(ROOT).parent.as_posix()
        out.append((f"/{rel}/", "monthly", "0.6", lastmod_for(f"/{rel}/")))
    return out


def poll_election_urls() -> list[tuple[str, str, str, str]]:
    """polls/{election-id}/ prerender 디렉토리 스캔 (선거별 여론조사 vs 실제)."""
    out = []
    proot = ROOT / "polls"
    if not proot.exists():
        return out
    for d in sorted(proot.iterdir()):
        if (d / "index.html").exists():
            out.append((f"/polls/{d.name}/", "monthly", "0.6", lastmod_for(f"/polls/{d.name}/")))
    return out


def url_block(loc: str, freq: str, priority: str, lastmod: str) -> str:
    return (
        f"  <url>\n"
        f"    <loc>{BASE}{loc}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{freq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        f"  </url>"
    )


def person_urls() -> list[tuple[str, str, str, str]]:
    """build_person_pages가 만든 sitemap_person.txt 소비."""
    p = ROOT / "data/sitemap_person.txt"
    if not p.exists():
        return []
    return [(loc.strip(), "monthly", "0.5", lastmod_for(loc.strip()))
            for loc in p.read_text(encoding="utf-8").splitlines() if loc.strip()]


def party_urls() -> list[tuple[str, str, str, str]]:
    """build_party_pages가 만든 sitemap_party.txt 소비 (개별 정당 프로필 페이지)."""
    p = ROOT / "data/sitemap_party.txt"
    if not p.exists():
        return []
    return [(loc.strip(), "monthly", "0.6", lastmod_for(loc.strip()))
            for loc in p.read_text(encoding="utf-8").splitlines() if loc.strip()]


def region_urls() -> list[tuple[str, str, str, str]]:
    """build_region_pages가 만든 sitemap_region.txt 소비."""
    p = ROOT / "data/sitemap_region.txt"
    if not p.exists():
        return []
    return [(loc.strip(), "monthly", "0.5", lastmod_for(loc.strip()))
            for loc in p.read_text(encoding="utf-8").splitlines() if loc.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-today", action="store_true",
                    help="매니페스트도 git 이력도 없을 때 전부 오늘로 심는다(최초 1회)")
    args = ap.parse_args()
    fresh = not MANIFEST.exists()

    # 층별로 나눠 낸다. 한 파일에 5,005개를 넣으면 Search Console이 '색인 생성됨
    # 3,100'처럼 사이트 전체 숫자 하나만 돌려준다 — 어느 층이 안 들어가는지 알 수
    # 없다. 인물 4,326개가 86%를 차지해 나머지 층의 상태를 통째로 가린다.
    # sitemap마다 따로 보고되므로, 나누는 것만으로 '어디가 막혔나'를 물을 수 있다.
    parties = party_urls()
    regions = region_urls()
    persons = person_urls()
    sections = [
        ("main",    [(loc, freq, pr, lastmod_for(loc)) for loc, freq, pr in STATIC]),
        ("archive", archive_urls()),
        ("history", history_urls()),
        ("polls",   poll_election_urls()),
        ("party",   parties),
        ("region",  regions),
        ("person",  persons),
    ]

    written = []
    for name, urls in sections:
        if not urls:
            continue
        body = "\n".join(url_block(loc, freq, pr, lm) for loc, freq, pr, lm in urls)
        (ROOT / f"sitemap-{name}.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + body + "\n</urlset>\n", encoding="utf-8")
        # 이 층의 lastmod 중 가장 최근 — 색인이 이 파일을 다시 읽을지 판단하는 값이다.
        written.append((name, len(urls), max(lm for *_, lm in urls)))

    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(f"  <sitemap>\n    <loc>{BASE}/sitemap-{n}.xml</loc>\n"
                    f"    <lastmod>{lm}</lastmod>\n  </sitemap>"
                    for n, _, lm in written)
        + "\n</sitemapindex>\n", encoding="utf-8")

    # 낡은 층 파일 청소 — 층이 비어 안 쓰게 됐는데 파일이 남으면 유령 URL을 계속
    # 제출하게 된다.
    live = {f"sitemap-{n}.xml" for n, _, _ in written}
    for f in ROOT.glob("sitemap-*.xml"):
        if f.name not in live:
            f.unlink()

    out = "\n".join((ROOT / f"sitemap-{n}.xml").read_text(encoding="utf-8")
                    for n, _, _ in written)
    (ROOT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    # 개수는 **쓴 것**을 센다. 손으로 더한 합계는 항목이 늘 때마다 어긋난다 —
    # 실제로 poll_election_urls가 빠져 있어 4,951이라고 찍으면서 4,960을 쓰고 있었다.
    # 빌드 로그가 사실과 다르면 로그를 보고 판단할 수 없게 된다.
    # ── 조용히 오늘로 떨어지지 않는다 ─────────────────────────────────────
    # 매니페스트도 없고 git 이력도 없으면(CI의 shallow clone) 모든 페이지가 오늘로
    # 찍힌다. 그게 정확히 이 값을 무의미하게 만들던 상태다 — 조용히 넘어가면 다시
    # 몇 달을 모른 채 간다. 죽어서 드러낸다.
    if _SEEDED and not _SEED_FROM_GIT and not args.seed_today:
        raise SystemExit(
            f"✗ lastmod를 심을 근거가 없다 — 새 페이지 {_SEEDED}개인데 git 이력이 비었다.\n"
            "  CI라면 actions/checkout이 shallow(fetch-depth 1)여서일 수 있다.\n"
            "  data/sitemap_lastmod.json이 커밋돼 있으면 git 이력 없이도 동작한다.\n"
            "  정말 처음 만드는 거라면 --seed-today")
    # 사라진 페이지를 매니페스트에서 뺀다. 안 빼면 유령이 계속 쌓인다 — 선거구
    # 지역 12쪽을 없앤 날, 매니페스트는 그 12쪽을 계속 가리키고 있었다(검사가
    # 잡았다). 이 파일은 '지금 내는 sitemap의 짝'이지 기록 보관소가 아니다.
    _live = {str(page_file(u).relative_to(ROOT))
             for _n, urls in sections for u, *_r in urls}
    _man = manifest()
    _gone = [k for k in _man if k not in _live]
    for k in _gone:
        del _man[k]

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "_note": ("페이지 내용 해시 → 그 내용이 처음 나타난 날. sitemap의 lastmod가 여기서 "
                  "나온다. git 커밋일을 쓰면 shallow clone·리베이스·대량 재빌드에 흔들려 "
                  "매일 4,980쪽이 '오늘'로 찍혔다 — 해시는 안 흔들린다."),
        "_fields": {"h": "index.html 내용 sha1 앞 12자", "d": "그 내용이 처음 나타난 날"},
        "pages": dict(sorted(manifest().items())),
    }, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")

    total = out.count("<loc>")
    detail = " + ".join(f"{n} {name}" for name, n, _ in written)
    if _gone:
        print(f"   매니페스트에서 사라진 페이지 {len(_gone)}개 제거")
    print(f"→ sitemap.xml: sitemapindex {len(written)}층 · {total} URLs "
          f"({detail}) · robots.txt")
    if _SEEDED:
        print(f"   lastmod 새로 심음 {_SEEDED} (git 이력 {_SEED_FROM_GIT} · 오늘 "
              f"{_SEEDED - _SEED_FROM_GIT}){' · 매니페스트 최초 생성' if fresh else ''}")


if __name__ == "__main__":
    main()
