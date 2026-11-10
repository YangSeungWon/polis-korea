"""Live delivery and freshness checks; independent of push-triggered CI.

A static site can serve HTTP 200 indefinitely while its deployment is stale.
Check its build SHA, the age of the FIRST undelivered commit, and source dates.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
import re
import subprocess
import time
from urllib.request import Request, urlopen

from health import ROOT, REFRESH_TARGETS, data_freshness

SITE = 'https://polis.ysw.kr'


class BuildMeta(HTMLParser):
    sha = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name') == 'polis-build':
            value = attrs.get('content', '').split()
            if value and re.fullmatch(r'[0-9a-f]{12,40}', value[0]):
                self.sha = value[0]


def build_sha(html):
    parser = BuildMeta()
    parser.feed(html)
    if not parser.sha:
        raise ValueError('서비스에 유효한 polis-build SHA가 없습니다')
    return parser.sha


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def read_live(path):
    # 캐시 우회. GitHub 토큰이나 다른 자격 증명을 서비스에 보내지 않는다.
    req = Request(f'{SITE}/{path}?health={time.time_ns()}',
                  headers={'User-Agent': 'polis-health/1.0', 'Cache-Control': 'no-cache'})
    with urlopen(req, timeout=30) as response:
        return response.read().decode('utf-8')


def deployment_problem(deployed, expected, exact, max_hours, now=None):
    if expected.startswith(deployed):
        return None
    if exact:
        return f'배포 SHA 불일치: 서비스 {deployed}, 대상 {expected[:12]}'
    # 짧은 SHA를 먼저 검증하고 같은 브랜치의 조상인지 확인한다.
    try:
        resolved = git('rev-parse', '--verify', f'{deployed}^{{commit}}')
        subprocess.run(['git', 'merge-base', '--is-ancestor', resolved, expected],
                       cwd=ROOT, check=True, capture_output=True)
        dates = git('log', '--format=%cI', f'{resolved}..{expected}').splitlines()
        oldest = min(datetime.fromisoformat(d) for d in dates)
    except (subprocess.CalledProcessError, ValueError):
        return f'서비스 SHA {deployed}를 현재 브랜치 이력과 대조할 수 없습니다'
    now = now or datetime.now(timezone.utc)
    hours = (now - oldest).total_seconds() / 3600
    if hours > max_hours:
        return f'배포 지연 {hours:.1f}시간: 서비스 {deployed}, 대상 {expected[:12]}'
    return None


def freshness_problems(rows):
    return [f"{r['label']}: {r['state']} (최신 {r['last']}, 예정 {r['next']})"
            for r in rows if r['state'] not in {'fresh', 'expected_pause'}]


def latest_date(data):
    return max((r.get('period_end') or r.get('date') or ''
                for r in data.get('records', [])), default='')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--deployment-only', action='store_true')
    ap.add_argument('--exact', action='store_true', help='배포 직후: SHA가 정확히 일치해야 함')
    ap.add_argument('--max-hours', type=float, default=24)
    ap.add_argument('--attempts', type=int, default=1)
    ap.add_argument('--delay', type=float, default=10)
    args = ap.parse_args()
    expected = git('rev-parse', 'HEAD')
    problems = []
    for attempt in range(max(1, args.attempts)):
        try:
            deployed = build_sha(read_live(''))
            problem = deployment_problem(deployed, expected, args.exact, args.max_hours)
        except Exception as exc:
            problem = f'서비스 확인 실패: {exc}'
        if not problem:
            print(f'✓ 서비스 SHA {deployed} / 대상 {expected[:12]}')
            break
        print(problem)
        if attempt + 1 < args.attempts:
            time.sleep(args.delay)
    if problem:
        problems.append(problem)
    if not args.deployment_only:
        rows = data_freshness()
        for row in rows:
            print(f"{row['label']}: {row['state']} · 최신 {row['last']}")
        problems.extend(freshness_problems(rows))
        for label, path, _, _ in REFRESH_TARGETS:
            try:
                delivered = latest_date(json.loads(read_live(path)))
                if not delivered:
                    problems.append(f'{label}: 서비스에 조사일이 없습니다')
                    continue
                source = latest_date(json.loads((ROOT / path).read_text()))
                if delivered < source:
                    problems.append(f'{label}: 서비스 {delivered} < 저장소 {source}')
            except Exception as exc:
                problems.append(f'{label}: 서비스 데이터 확인 실패: {exc}')
    report = '\n'.join(f'- {p}' for p in problems) if problems else '- 서비스 반영·신선도 정상'
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write('## 운영 상태\n\n' + report + '\n')
    print(report)
    return int(bool(problems))


if __name__ == '__main__':
    raise SystemExit(main())
