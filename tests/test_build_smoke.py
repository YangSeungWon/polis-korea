"""빌드 스크립트 연기 시험 — 브라우저·네트워크 없이 진입 경로만 태운다.

regen_check.sh는 생성기를 전부 재실행해 산출물을 비교하지만, **거기 못 들어가는
스크립트**가 있다. build_og_maps는 playwright와 로컬 http 서버가 필요해서 CI에서
안 돈다. 그 틈에서 실제로 사고가 났다:

    2026-08 뷰 표를 레지스트리로 통합하면서 VIEW_DEFS 블록을 잘라냈는데, 같은
    범위에 list_slugs()가 있어 함께 지워졌다. --slug 단일 실행은 그 함수를 안 타서
    통과했고, 전량 실행에서 NameError로 죽었다. 커밋은 이미 푸시된 뒤였다.

py_compile은 이걸 못 잡는다(NameError는 실행 시점이다). 그래서 각 스크립트의
'브라우저 없이 갈 수 있는 가장 깊은 지점'까지 실제로 실행한다.

실행: .venv/bin/python tests/test_build_smoke.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (라벨, 명령) — 브라우저·네트워크 없이 끝나야 하고, 종료코드 0이어야 한다.
SMOKE = [
    ("build_map_manifest", [sys.executable, "scripts/build/build_map_manifest.py"]),
    ("sync_view_thumbs_js", [sys.executable, "scripts/build/sync_view_thumbs_js.py"]),
    # 폴 적중률은 계산 정본이 파이썬으로 옮겨온 것이라, 브라우저 없이 도는지가
    # 중요하다 — 옛 계산은 JS에만 있어서 CI가 아무것도 못 봤다.
    ("build_poll_accuracy", [sys.executable, "scripts/build/build_poll_accuracy.py"]),
    # 여론조사 지도도 브라우저 없이 대상 산정까지는 돌아야 한다(archive와 같은 이유).
    ("build_og_maps --pages polls",
     [sys.executable, "scripts/build/build_og_maps.py", "--pages", "polls", "--list"]),
    ("build_og_maps --pages static",
     [sys.executable, "scripts/build/build_og_maps.py", "--pages", "static", "--list"]),
    ("sync_static_figures", [sys.executable, "scripts/build/sync_static_figures.py"]),
    ("build_timelapse_index", [sys.executable, "scripts/build/build_timelapse_index.py"]),
    ("sync_home_status", [sys.executable, "scripts/build/sync_home_status.py"]),
    ("sync_page_seeds", [sys.executable, "scripts/build/sync_page_seeds.py"]),
]

# CI에 없는데 로컬엔 있는 모듈. requirements.txt에 없으면서 import되면 CI에서만 죽는다.
# 2026-08 실제로 그랬다 — 지도 <figure>의 width/height를 Pillow로 읽었는데, 로컬엔
# 다른 패키지의 의존성으로 깔려 있고 requirements.txt엔 없어서 CI에서 ModuleNotFound로
# 죽었다. 폭·높이 두 값 때문에 이미지 라이브러리를 빌드 의존성으로 만들 이유가 없어
# PNG 헤더에서 직접 읽는 쪽으로 바꿨고(result_tables.png_size), 여기서 그걸 지킨다.
BLOCK = ["PIL", "playwright"]

BLOCKER = (
    "import builtins\n"
    "_i = builtins.__import__\n"
    "BLOCK = %r\n"
    "def _f(n, *a, **k):\n"
    "    if n.split('.')[0] in BLOCK:\n"
    "        raise ModuleNotFoundError(\"No module named '%%s'\" %% n)\n"
    "    return _i(n, *a, **k)\n"
    "builtins.__import__ = _f\n"
) % (BLOCK,)

# 브라우저 없이 끝나야 하고, 위 모듈 없이도 끝나야 한다.
NO_PIL = [
    # --list는 브라우저 없이 대상만 산정한다. playwright import가 그 위에 있으면
    # 이 경로가 브라우저 없이 도는 게 아니게 된다 — 실제로 그랬고 이 검사가 잡았다.
    ("build_og_maps --list", "scripts/build/build_og_maps.py", ["--list"]),
    ("sync_archive_html", "scripts/build/sync_archive_html.py"),
    ("build_static", "scripts/build/build_static.py"),
    ("build_map_manifest", "scripts/build/build_map_manifest.py"),
    ("build_sitemap", "scripts/build/build_sitemap.py"),
]

fails = []


def run_without(label: str, script: str, argv: list | None = None) -> None:
    code = BLOCKER + (f"exec(open({script!r}, encoding='utf-8').read(), "
                      f"{{'__name__': '__main__', '__file__': {script!r}}})")
    r = subprocess.run([sys.executable, "-c", code] + (argv or []), cwd=ROOT,
                       capture_output=True, text=True, timeout=300)
    ok = r.returncode == 0
    print(f"  {'✓' if ok else '✗'} {label}"
          + ("" if ok else f" — {r.stderr.strip()[-260:]}"))
    if not ok:
        fails.append(label)


def main() -> int:
    print("[연기] 브라우저 없이 진입 경로가 살아 있는가")
    for label, cmd in SMOKE:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=180)
        ok = r.returncode == 0
        print(f"  {'✓' if ok else '✗'} {label}"
              + ("" if ok else f" — exit {r.returncode}\n      {r.stderr.strip()[-300:]}"))
        if not ok:
            fails.append(label)

    print(f"\n[의존성] {'·'.join(BLOCK)} 없이도 도는가 (CI엔 없다)")
    for row in NO_PIL:
        run_without(*row)

    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
