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
    ("build_og_maps 대상 산정", [sys.executable, "scripts/build/build_og_maps.py", "--list"]),
    ("build_map_manifest", [sys.executable, "scripts/build/build_map_manifest.py"]),
    ("build_share_pages", [sys.executable, "scripts/build/build_share_pages.py"]),
    ("sync_view_registry_js", [sys.executable, "scripts/build/sync_view_registry_js.py"]),
]

fails = []


def main() -> int:
    print("[연기] 브라우저 없이 진입 경로가 살아 있는가")
    for label, cmd in SMOKE:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=180)
        ok = r.returncode == 0
        print(f"  {'✓' if ok else '✗'} {label}"
              + ("" if ok else f" — exit {r.returncode}\n      {r.stderr.strip()[-300:]}"))
        if not ok:
            fails.append(label)
    print(f"\n{'실패 ' + str(len(fails)) if fails else '전부 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
