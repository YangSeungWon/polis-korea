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
#
# 상태는 넷으로 가른다 — '최근 데이터 없음'과 '수집 실패'는 다르다.
# (null ≠ 0, 무투표 ≠ 결손과 같은 계열이다.)
#   fresh              다음 예정일이 아직 안 왔다
#   expected_pause     원출처가 쉬는 기간이다 — 결함이 아니다
#   manual_refresh     원출처가 CI 러너 IP를 차단한다 — 로컬에서 돌려야 한다
#   overdue            예정일이 지났는데 안 들어왔다 — 봐야 한다
#   fetch_failed       파일 자체가 없다
#
# 기관별 달력을 거대한 시스템으로 만들지 않는다. **지금 확인 가능한 예외만** 적는다.
PAUSES = {
    # 한국갤럽 2026년 공식 일정 — 여름 휴가철 데일리 오피니언 2주 휴간.
    # https://www.gallup.co.kr/company/noticeContents.asp?seqNo=10330
    "gallup": [("2026-07-27", "2026-08-07")],
}

# realmeter.net은 GitHub Actions 러너 IP를 차단한다(NESDC와 같은 계열). CI에선
# 항상 '총 0건'이라 예정일을 넘겨도 우리 결함이 아니다 — 로컬에서 돌려야 갱신된다.
# 그렇다고 조용히 넘기면 몇 달이고 옛 데이터가 남으므로 별도 상태로 드러낸다.
CI_BLOCKED = {"realmeter"}

REFRESH_TARGETS = [
    # (라벨, 파일, 주기(일), 소스 키)
    ("갤럽 국정평가", "data/polls/approval_gallup.json", 10, "gallup"),
    # 차기주자는 국정평가와 **주기가 다르다**. 갤럽 '장래 정치 지도자 선호도'는
    # 대선 국면에만 주간이고 평시엔 분기다 — 실제 간격이 2025-04까지 7일이었다가
    # 그 뒤 147·77·91·98일로 벌어졌다. 국정평가와 같은 10일을 쓰면 평시엔 늘
    # overdue가 뜬다(실제로 그랬다). 관측된 간격을 덮는 값으로 둔다.
    ("갤럽 차기주자", "data/polls/gallup_leaders.json", 150, "gallup"),
    ("리얼미터 국정평가", "data/polls/approval_realmeter.json", 10, "realmeter"),
    ("NBS", "data/polls/approval_nbs.json", 14, "nbs"),
]


def in_pause(key: str | None, d: date) -> tuple[str, str] | None:
    """그 날짜가 원출처의 휴간 기간에 걸리는가."""
    for a, b in PAUSES.get(key or "", []):
        if date.fromisoformat(a) <= d <= date.fromisoformat(b):
            return (a, b)
    return None


def next_expected(last: date, cadence: int, key: str | None) -> date:
    """다음 발표 예정일. 휴간에 걸리면 휴간이 끝난 뒤로 민다.
    경과일만 보면 예정된 휴간이 '지연'으로 잡힌다.

    휴간 뒤로 밀 때 **다음 날이 아니라 한 주기 뒤**로 민다. 휴간이 끝난 이튿날
    바로 발표하는 기관은 없다 — 갤럽은 화~목 조사하고 금요일에 낸다. 이튿날로
    밀었더니 휴간 종료(08-07) 다음 날인 08-08을 예정일로 잡고, 실제 첫 발표가
    오기도 전에 overdue가 떴다. 감시가 가짜로 울리면 진짜 지연을 놓친다.
    """
    nxt = date.fromordinal(last.toordinal() + cadence)
    for _ in range(6):          # 연속 휴간 대비(무한루프 방지 상한)
        rng = in_pause(key, nxt)
        if not rng:
            return nxt
        nxt = date.fromordinal(date.fromisoformat(rng[1]).toordinal() + cadence)
    return nxt


def data_freshness() -> list[dict]:
    today = date.today()
    out = []
    for label, rel, cadence, key in REFRESH_TARGETS:
        fp = ROOT / rel
        if not fp.exists():
            out.append({"label": label, "state": "fetch_failed", "last": None,
                        "next": None, "note": "파일 없음"})
            continue
        d = git_date(rel)
        last = None
        if d:
            try:
                last = date.fromisoformat(d)
            except Exception:
                pass
        if not last:
            out.append({"label": label, "state": "fetch_failed", "last": d,
                        "next": None, "note": "갱신일 미상"})
            continue
        nxt = next_expected(last, cadence, key)
        if today <= nxt:
            state, note = "fresh", ""
        elif in_pause(key, today):
            rng = in_pause(key, today)
            state, note = "expected_pause", f"원출처 휴간 {rng[0]}~{rng[1]}"
        elif key in CI_BLOCKED:
            state, note = ("manual_refresh",
                           f"{(today - nxt).days}일 지남 · CI 러너 차단 — 로컬에서 "
                           "fetch_realmeter_self.py + extract_approval_realmeter.py --source self")
        else:
            state, note = "overdue", f"{(today - nxt).days}일 지남"
        out.append({"label": label, "state": state, "last": str(last),
                    "next": str(nxt), "note": note})
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
    MARK = {"fresh": "  ", "expected_pause": "· ", "manual_refresh": "↻ ",
            "overdue": "⚠ ", "fetch_failed": "✗ "}
    for f in fresh:
        print(f"  {MARK.get(f['state'], '  ')}{f['label']:16} {f['state']:15}"
              f" 최신 {f['last'] or '?':10} 다음 {f['next'] or '?':10} {f['note']}")

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

    over = [f for f in fresh if f["state"] == "overdue"]
    if over:
        names = ", ".join(f["label"] for f in over)
        print(f"\n⚠ 예정일이 지난 데이터셋: {names}")
        print("   원출처에 새 발표가 있는지 먼저 본다 — 없으면 외부 지연이지 우리 결함이 아니다.")
    paused = [f for f in fresh if f["state"] == "expected_pause"]
    if paused:
        print(f"\n· 휴간 중(정상): {', '.join(f['label'] for f in paused)}")
    manual = [f for f in fresh if f["state"] == "manual_refresh"]
    if manual:
        print(f"\n↻ 로컬 수동 갱신 필요: {', '.join(f['label'] for f in manual)}")
        print("   원출처가 CI 러너 IP를 차단한다 — 우리 결함도 외부 지연도 아니다.")
    if bad:
        print(f"\n✗ 깨진 내부 링크 {len(bad)}종. 화면은 멀쩡한데 클릭하면 404다.")
        return 1 if args.strict else 0
    print("\n✓ 깨진 내부 링크 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
