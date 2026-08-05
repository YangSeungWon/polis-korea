"""build / data health 요약 — 한눈에 보는 운영 상태.

polis는 이제 작은 데이터 제품이다(정적 페이지 5천 · 생성기 다수 · fetcher · CI ·
스크린샷 감사 · sitemap · 일일 갱신). 기능이 안정됐으니 유지보수 비용을 줄이는
쪽이 남았고, 그 첫 걸음은 **어디가 아픈지 한 화면에서 보이는 것**이다.

  · 깨진 내부 링크    화면은 멀쩡한데 클릭하면 404 — 눈으로는 안 보인다
  · stale 데이터      fetcher가 조용히 멈춘 지 며칠인지
  · 가장 큰 산출물    페이지 무게가 어디서 오는지
  · 생성기 소요시간   느려지는 지점
  · 배포 SHA          지금 배포된 게 무엇인지

--strict: 깨진 링크가 있으면 exit 1 (CI 게이트).

사용:
  python3 scripts/audit/health.py [--strict] [--json 경로]
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", "node_modules", ".venv", ".github"}
# 신선도 기준은 데이터셋마다 다르다 — 주간 조사에 3일 기준을 대면 늘 빨갛다.
# REFRESH_TARGETS에 각각의 주기를 적는다.


def pages() -> list[Path]:
    return [p for p in ROOT.rglob("*.html")
            if not any(x in p.parts for x in SKIP_DIRS)]


def resolve(u: str) -> Path:
    rel = unquote(u.split("#")[0].split("?")[0]).lstrip("/")
    if rel == "":
        rel = "index.html"
    return ROOT / (rel + "index.html") if rel.endswith("/") else ROOT / rel


def broken_links(ps: list[Path]) -> tuple[int, dict]:
    """내부 링크 전수. 같은 URL은 한 번만 확인한다(10만 건이라 중복이 대부분)."""
    seen, bad, n = set(), Counter(), 0
    for p in ps:
        for u in re.findall(r'href="(/[^"]*)"', p.read_text(encoding="utf-8")):
            n += 1
            k = u.split("#")[0].split("?")[0]
            if k in seen:
                continue
            seen.add(k)
            if not resolve(k).exists():
                bad[k] = 0
    # 깨진 대상별로 어느 페이지가 가리키는지 한 곳만 기록
    if bad:
        for p in ps:
            t = p.read_text(encoding="utf-8")
            for k in list(bad):
                if not bad[k] and f'href="{k}"' in t:
                    bad[k] = str(p.relative_to(ROOT))
            if all(bad.values()):
                break
    return n, dict(bad)


def git_date(rel: str) -> str | None:
    """파일이 마지막으로 **실제로 바뀐** 날. _meta.generated_at은 파일마다 있기도
    없기도 해서 스키마에 기대면 부정확하다 — git은 모든 파일에 같은 기준을 준다."""
    try:
        r = subprocess.run(["git", "-c", "core.quotepath=false", "log", "-1",
                            "--format=%cs", "--", rel],
                           cwd=ROOT, capture_output=True, text=True, timeout=15)
        return r.stdout.strip() or None
    except Exception:
        return None


# **정기적으로 갱신되어야 하는 것만** 본다. 확정된 회차 결과나 캡처가 끝난 공약은
# 안 바뀌는 게 정상이라 여기 넣으면 매일 거짓 경보가 울린다.
#   (cadence_days = 이보다 오래 안 바뀌면 fetcher가 멈춘 것으로 본다)
REFRESH_TARGETS = [
    ("갤럽 국정평가", "data/polls/approval_gallup.json", 10),
    ("갤럽 차기주자", "data/polls/gallup_leaders.json", 10),
    ("리얼미터 정당지지", "data/polls/approval_realmeter.json", 10),
    ("NBS", "data/polls/approval_nbs.json", 14),
]


def data_freshness() -> list[dict]:
    out = []
    for label, rel, cadence in REFRESH_TARGETS:
        fp = ROOT / rel
        if not fp.exists():
            out.append({"label": label, "state": "없음", "days": None, "cadence": cadence})
            continue
        d = git_date(rel)
        days = None
        if d:
            try:
                days = (date.today() - date.fromisoformat(d)).days
            except Exception:
                pass
        out.append({"label": label, "state": d or "미상", "days": days, "cadence": cadence})
    return out


def largest(ps: list[Path], n: int = 5) -> list[tuple[str, int]]:
    sized = sorted(((p, p.stat().st_size) for p in ps), key=lambda x: -x[1])[:n]
    return [(str(p.relative_to(ROOT)), s) for p, s in sized]


def biggest_data(n: int = 5) -> list[tuple[str, int]]:
    ds = sorted(((p, p.stat().st_size) for p in (ROOT / "data").rglob("*.json")),
                key=lambda x: -x[1])[:n]
    return [(str(p.relative_to(ROOT)), s) for p, s in ds]


GENERATORS = ["sync_nav_html", "sync_archive_html", "build_static", "build_person_pages",
              "build_party_pages", "build_region_pages", "build_home_capabilities",
              "build_sitemap"]


def generator_times(py: str) -> list[tuple[str, float]]:
    out = []
    for g in GENERATORS:
        t0 = time.time()
        subprocess.run([py, f"scripts/build/{g}.py"], cwd=ROOT,
                       capture_output=True, timeout=900)
        out.append((g, round(time.time() - t0, 1)))
    return out


def deploy_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return "unknown"


def mb(n: int) -> str:
    return f"{n / 1024:.0f}KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f}MB"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="깨진 링크가 있으면 exit 1")
    ap.add_argument("--json", default=None, help="요약을 JSON으로도 저장")
    ap.add_argument("--time-generators", action="store_true",
                    help="생성기를 실제로 돌려 시간 측정 (저장소를 건드린다)")
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    ps = pages()
    n_links, bad = broken_links(ps)
    fresh = data_freshness()
    rep: dict = {
        "sha": deploy_sha(),
        "pages": len(ps),
        "links": n_links,
        "broken": bad,
        "freshness": fresh,
        "largest_html": largest(ps),
        "largest_data": biggest_data(),
    }

    print(f"\n─ polis health · {rep['sha']} ─")
    print(f"\n페이지 {len(ps):,} · 내부 링크 {n_links:,}")
    print(f"깨진 링크 {len(bad)}" + ("" if not bad else ":"))
    for k, where in list(bad.items())[:10]:
        print(f"    ✗ {k}   ← {where}")

    print("\n데이터 신선도")
    for f in fresh:
        over = f["days"] is not None and f["days"] > f["cadence"]
        age = f"{f['days']}일 전" if f["days"] is not None else "?"
        print(f"  {'⚠ ' if over else '  '}{f['label']:16} {f['state']:12} {age}"
              f"  (주기 {f['cadence']}일)")

    print("\n가장 큰 산출물")
    for name, s in rep["largest_html"]:
        print(f"    {mb(s):>7}  {name}")
    for name, s in rep["largest_data"][:3]:
        print(f"    {mb(s):>7}  {name}")

    if args.time_generators:
        ts = generator_times(args.python)
        rep["generator_seconds"] = dict(ts)
        print(f"\n생성기 (합계 {sum(t for _, t in ts):.1f}s)")
        for g, t in sorted(ts, key=lambda x: -x[1]):
            print(f"    {t:5.1f}s  {g}")

    if args.json:
        Path(args.json).write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        print(f"\n→ {args.json}")

    stale = [f for f in fresh if f["days"] is not None and f["days"] > f["cadence"]]
    if stale:
        names = ", ".join(f["label"] for f in stale)
        print(f"\n⚠ 주기를 넘긴 데이터셋: {names} — fetcher가 조용히 멈췄는지 확인할 것")
    if bad:
        print(f"\n✗ 깨진 내부 링크 {len(bad)}종. 화면은 멀쩡한데 클릭하면 404다.")
        return 1 if args.strict else 0
    print("\n✓ 깨진 내부 링크 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
