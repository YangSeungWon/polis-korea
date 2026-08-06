#!/usr/bin/env bash
# 생성기를 실제로 돌린 뒤 저장소가 예상 상태인지 본다.
#
# nav 4축 재편이 363개 페이지에 반영되지 못한 사고의 직접 원인이 여기 있었다:
# daily-refresh가 build_static.py를 **실행은 했는데** git add 범위에 없어 결과가 매일
# 버려졌다. 생성기가 성공했다는 것과 저장소가 옳다는 것은 다른 말이다.
#
# 이 검사가 잡는 것:
#   · 생성기를 돌리고 결과를 커밋하지 않은 상태
#   · 생성된 HTML을 손으로 고친 것(다음 빌드에 조용히 날아간다)
#   · 생성기 입력(데이터)만 바뀌고 출력이 갱신되지 않은 상태
#   · **기계마다 결과가 달라지는 비결정성** — 실제로 Path.iterdir() 순서에 의존하는
#     코드를 넣었더니 로컬은 통과하고 CI에서 4,326개가 전부 diff로 잡혔다.
#     같은 기계에서 두 번 돌려서는 절대 안 잡힌다(FS 순서가 같으니까).
#     '커밋된 산출물 vs 지금 생성한 것'을 다른 기계에서 비교하는 이 검사만이 잡는다.
#
# 여기 넣는 생성기는 **커밋되는 산출물을 만드는 것**만이다. 일회성 데이터 마이그레이션
# 스크립트는 대상이 아니다.
set -euo pipefail
PY="${PYTHON:-python}"

# 순서가 중요하다. build_person_index는 뼈대만 만들고 enrich_person_index가
# assembly_id 등을 채운다 — 앞엣것만 돌리면 정당 페이지의 '소속 인물'이 통째로
# 사라진다(실제로 그랬다). 의존 관계가 있는 것은 반드시 짝으로 넣는다.
GENERATORS=(
  build_timeline         # data/timeline.json (정당·회차 메타)
  build_person_index     # assets/person-index.json 뼈대
  enrich_person_index    #   └ assembly_id·비례 보강 (반드시 뒤에)
  sync_nav_html          # nav 정본 → 모든 HTML
  sync_archive_html      # archive 목록·그룹 구조
  build_static           # history/·polls/ 프리렌더
  build_person_pages     # /person/{slug}/
  build_party_pages      # /party/{name}/
  build_region_pages     # /region/{시도-시군구}/
  build_home_capabilities
  build_tracker_static   # tracker.html 정적 요약 (JS 없이 읽히는 현재 지표)
  build_history_static   # history.html 진입점 (빈 상태 → 시작점)
  region_timeline        # data/region_timeline/ (지역 정치사 점·비교선·사건)
  render_region_timeline #   └ region-timeline/*.html (반드시 뒤에)
  map_timelapse          # data/map_timelapse/ (경계·선거·투영 상태 — 사건 있는 지역 전부)
  render_map_timelapse   #   └ map-timelapse/*.html (반드시 뒤에)
  build_sitemap          # sitemap.xml·robots.txt (마지막 — 위 산출물을 훑는다)
)

echo "생성기 ${#GENERATORS[@]}개 재실행"
for g in "${GENERATORS[@]}"; do
  printf '  %-24s' "$g"
  $PY "scripts/build/$g.py" >/dev/null 2>&1 && echo "ok" || { echo "실패"; exit 1; }
done

# 검사 대상은 **생성 산출물**이다. 새 스크립트를 추가하는 중이라 untracked 파일이
# 있는 것은 정상이므로, 추적 중인 변경 + 생성 경로의 새 파일만 본다.
OUT_PATHS=(person party region history polls archive share sitemap.xml robots.txt
           index.html elections.html
           assets/person-index.json data/timeline.json)
# **stage된 것은 통과**시킨다. 이 검사가 막으려는 것은 "커밋에 안 들어가는 산출물"이지
# "새로 생긴 산출물"이 아니다. 새 생성기를 추가하는 커밋은 산출물이 HEAD에 없는 게
# 당연한데, 그걸 실패로 보면 새 산출물을 **영원히** 커밋할 수 없다(add → 여전히 실패).
# porcelain의 둘째 칸이 공백이면 stage됨 — 지금 만들 커밋에 들어간다는 뜻이다.
CHANGED="$(git status --porcelain -- "${OUT_PATHS[@]}" '*.html' | grep -Ev '^[AMRDC] ' || true)"
if [ -n "$CHANGED" ]; then
  echo
  echo "✗ 생성기를 돌렸더니 커밋 밖에 남는 산출물이 있다."
  echo "  원인은 대개 셋이다:"
  echo "    1) 생성기를 돌리고 결과를 커밋하지 않았다(CI의 git add 범위 확인)"
  echo "    2) 생성된 파일을 손으로 고쳤다(다음 빌드에 조용히 날아간다)"
  echo "    3) 새 산출물이 stage되지 않았다 — git add 하면 된다"
  echo
  echo "$CHANGED" | head -20
  echo
  git diff --stat | tail -5
  exit 1
fi
echo
echo "✓ 생성기 재실행 후 남는 산출물 없음 — 커밋될 내용이 정본과 일치"
