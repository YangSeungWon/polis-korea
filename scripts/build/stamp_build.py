"""배포 산출물에 빌드 SHA를 새긴다 — **배포 시점에만**, 저장소에는 커밋하지 않는다.

왜 필요한가: 화면을 보고 결함을 판단할 때 '내가 보고 있는 게 최신인가'를 먼저
확정해야 한다. 실제로 이미 고친 것(공약 제목·재보궐 키)을 결함으로 보고받은 적이
있는데 원인이 브라우저 캐시였다. 그때 화면에서 SHA를 볼 수 있었다면 30초에 끝났다.

  <meta name="polis-build" content="{sha} {iso}">

meta로만 두고 화면에는 그리지 않는다 — 사용자에게 필요한 정보가 아니다.
개발자 도구나 `curl -s URL | grep polis-build`로 확인한다.

저장소를 더럽히지 않는 게 중요하다. HTML에 커밋하면 매 배포마다 4,900개가 바뀌고
생성기 멱등성 검사(regen_check.sh)가 매번 깨진다 — CI 러너에서만 돌린다.

사용: python scripts/build/stamp_build.py [--sha ...] [--check]
"""
from __future__ import annotations
import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", "node_modules", ".venv", ".github"}
MARK = re.compile(r'\n?<meta name="polis-build"[^>]*>')


def git_sha() -> str:
    for env in ("GITHUB_SHA", "COMMIT_SHA"):
        if os.environ.get(env):
            return os.environ[env][:12]
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=10
                              ).stdout.strip()[:12] or "unknown"
    except Exception:
        return "unknown"


def htmls():
    for p in sorted(ROOT.rglob("*.html")):
        if not any(part in SKIP_DIRS for part in p.parts):
            yield p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", default=None)
    ap.add_argument("--check", action="store_true",
                    help="새기지 않고 이미 새겨져 있는지만 확인")
    args = ap.parse_args()

    if args.check:
        missing = [p for p in htmls() if 'name="polis-build"' not in p.read_text(encoding="utf-8")]
        print(f"빌드 SHA 없는 HTML: {len(missing)}")
        return 1 if missing else 0

    sha = args.sha or git_sha()
    stamp = (f'\n<meta name="polis-build" content="{sha} '
             f'{datetime.now(timezone.utc).isoformat(timespec="seconds")}">')
    n = 0
    for p in htmls():
        t = p.read_text(encoding="utf-8")
        if "<head>" not in t:
            continue
        t = MARK.sub("", t)                       # 재실행 시 중복 방지
        t = t.replace("<head>", "<head>" + stamp, 1)
        p.write_text(t, encoding="utf-8")
        n += 1
    print(f"→ 빌드 SHA {sha} · HTML {n}개에 새김 (저장소 커밋 대상 아님)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
