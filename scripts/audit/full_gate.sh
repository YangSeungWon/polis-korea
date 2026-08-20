#!/usr/bin/env bash
# 커밋 전 **전체** 검증. 부분 성공을 커밋 허가로 간주하지 않는다.
#
# 이 세션에서 두 번, 테스트가 깨진 채로 커밋했다. 둘 다 "관련 테스트만 돌리고
# 괜찮겠지" 한 결과다. 한 번은 새 정당 디렉터리가 untracked라 sitemap이 어긋났고,
# 한 번은 새 미리보기 파일이 sitemap 제외 목록에 없었다. 둘 다 사람 주의로 막을
# 종류가 아니라서 gate로 만든다.
#
# 사용: bash scripts/audit/full_gate.sh
set -uo pipefail
PY="${PYTHON:-.venv/bin/python}"
fail=0
step() { printf '  %-34s' "$1"; shift; if "$@" >/tmp/gate.log 2>&1; then echo ok; else
  echo 실패; fail=1; tail -6 /tmp/gate.log | sed 's/^/      /'; fi; }

echo "[1/4] python 테스트"
for f in tests/test_*.py; do step "$(basename "$f")" "$PY" "$f"; done

# containment.json의 exhaustive=true는 "하위가 상위를 남김없이 나눈다"는 사실
# 주장이고, 지역 페이지가 그 위에서 득표를 합산한다. 틀리면 없던 숫자가 만들어지므로
# 주장을 적어두는 것으로 끝내지 않고 매번 센다.
step "verify_containment" "$PY" scripts/audit/verify_containment.py

echo "[2/4] 생성물 정합 (regen_check)"
step "regen_check" env PYTHON="$PY" bash scripts/build/regen_check.sh

echo "[3/4] UI 감사"
if command -v node >/dev/null && [ -d node_modules/playwright ] || \
   node -e "require('playwright')" >/dev/null 2>&1; then
  for f in tests/ui/test_*.mjs; do step "$(basename "$f")" node "$f"; done
else
  echo "  · playwright 없음 — UI 감사 건너뜀 (커밋 전 반드시 확인할 것)"
fi

echo "[4/4] 미커밋 생성물"
CHANGED="$(git -c core.quotepath=false status --porcelain)"
if [ -n "$CHANGED" ]; then
  echo "  · 미커밋 변경 있음 (add 범위를 확인하라)"
  echo "$CHANGED" | head -8 | sed 's/^/      /'
fi

echo
if [ $fail -eq 0 ]; then echo "✓ 전체 gate 통과 — 커밋해도 된다"; else
  echo "✗ gate 실패 — 커밋하지 마라"; fi
exit $fail
