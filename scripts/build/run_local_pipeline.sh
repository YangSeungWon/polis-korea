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

echo "=== 1/6 NEC 라이브/OpenAPI fetch (개표·득표) ==="
if [[ "$EID" == 9th-* ]]; then
  python3 scripts/fetch/fetch_nec_live.py --election "$EID"
else
  python3 scripts/fetch/fetch_nec_results.py --election "$EID"
fi

echo
echo "=== 2/6 당선인 확정 (무투표·중선거구 정수·비례 의석 — 라이브 개표 누락분) ==="
# 라이브 개표엔 무투표 선거구·중선거구 정수·당선이 없음 → 확정 당선인 명부로 오버레이.
# 추정(infer_council_winners·calc_proportional)은 부정확하므로 명부가 우선. 명부 없을 때만 추정 fallback.
if [[ "$EID" == 9th-* ]]; then
  # OpenAPI 미게시 → NEC 개표방송 포털 당선인 명부(EPEI01).
  python3 scripts/fetch/fetch_single_winners_live.py   # tc4 기초장 + tc5 광역의원(무투표 보충)
  python3 scripts/fetch/fetch_council_winners_live.py   # tc6 기초의원 지역구 + tc9 비례
  # tc8 광역의원 비례는 calc_proportional 추정 유지 (명부 EPEI01_#8 불명확 — 교육의원 등 혼입).
else
  # 5~8회: OpenAPI 당선인. tc6 지역구(rebuild) + tc9 비례.
  N="${EID%%th-*}"
  python3 scripts/fetch/fetch_council_winners.py --n "$N" --rebuild || true
  python3 scripts/fetch/fetch_council_prop.py --n "$N" || true
fi

echo
echo "=== 3/6 무투표 inject (기초장·광역의원 등 — 기초의원은 위 명부가 처리) ==="
python3 scripts/fetch/fetch_local_uncontested.py --election "$EID" || \
  echo "  ! 무투표 fetch 실패 (graceful — API 미공개 가능)"

echo
echo "=== 4/6 chunk results ==="
python3 scripts/build/chunk_results.py --id "$EID"

echo
echo "=== 5/6 timeline 재빌드 ==="
python3 scripts/build/build_timeline.py

echo
echo "=== 6/6 archive HTML 동기화 ==="
python3 scripts/build/sync_archive_html.py

echo
echo "✓ 완료: $EID"
