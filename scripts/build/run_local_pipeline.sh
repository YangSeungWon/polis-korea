#!/usr/bin/env bash
# 지선 회차 1건 끝까지 — fetch → 무투표 inject → chunk → timeline → archive sync.
# 새 회차도 옛 회차도 동일하게.
#
# 사용:
#   ./scripts/build/run_local_pipeline.sh 9th-local-2026
#   ./scripts/build/run_local_pipeline.sh 8th-local-2022  # 옛 회차 재수집
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "사용: $0 <election-id>" >&2
  exit 1
fi
EID="$1"
cd "$(dirname "$0")/../.."

# .env 자동 로드
[ -f .env ] && set -a && source .env && set +a

echo "=== 1/5 NEC 라이브/OpenAPI fetch ==="
if [[ "$EID" == 9th-* ]]; then
  python3 scripts/fetch/fetch_nec_live.py --election "$EID"
else
  python3 scripts/fetch/fetch_nec_results.py --election "$EID"
fi

echo
echo "=== 2/5 무투표 inject ==="
python3 scripts/fetch/fetch_local_uncontested.py --election "$EID" || \
  echo "  ! 무투표 fetch 실패 (graceful — API 미공개 가능)"

echo
echo "=== 3/5 chunk results ==="
python3 scripts/build/chunk_results.py --id "$EID"

echo
echo "=== 4/5 timeline 재빌드 ==="
python3 scripts/build/build_timeline.py

echo
echo "=== 5/5 archive HTML 동기화 ==="
python3 scripts/build/sync_archive_html.py

echo
echo "✓ 완료: $EID"
