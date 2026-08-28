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
  # 비교 산출물은 registry(정당 identity)와 선거구 계보를 **둘 다** 입력으로 받는데
  # 어느 쪽을 고쳐도 자동으로 다시 만들어지지 않아 조용히 낡았다 — compared 204에
  # 멈춰 있었고 다시 돌리자 226이 됐다. 인자 없이 돌면 기존 조합을 전부 다시 만든다.
  build_general_comparison  # data/comparisons/general/{cur}__{prev}.json
  build_general_national    # data/comparisons/general/national__*.json
  build_person_index     # assets/person-index.json 뼈대
  enrich_person_index    #   └ assembly_id·비례 보강 (반드시 뒤에)
  sync_nav_html          # nav 정본 → 모든 HTML
  sync_archive_html      # archive 목록·그룹 구조
  build_poll_accuracy    # data/polls/accuracy.json (여론조사 1위 vs 실제 — 계산 정본)
  build_static           # history/·polls/ 프리렌더 (accuracy 뒤 — 표를 읽는다)
  build_person_pages     # /person/{slug}/
  build_party_pages
  build_observed_parties # data/parties/observed.json (관측 층 — registry와 분리)      # /party/{name}/
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

# 커밋된 데이터만으로 결정되는 **파생물**. 위 GENERATORS와 달리 scripts/build 밖에
# 있거나 인자를 요구해서 그동안 이 검사 밖에 있었다 — 입력만 바뀌고 출력이 안 바뀐
# 상태를 아무도 못 잡았다. comparisons가 그랬고(204에 멈춰 있었다),
# validation_21__20도 그랬다(한나라당 오귀속을 품은 채 낡아 있었다).
# 외부에서 받아오는 fetch 스크립트는 대상이 아니다 — 네트워크가 답을 바꾼다.
DERIVED=(
  "scripts/normalize/party_lifecycle.py --write"      # lifecycle.json ← registry
  "scripts/build/political_axes.py --write"           # political_axes.json ← registry·lifecycle
  "scripts/build/family_vote_share.py"                # family_vote_share.json ← political_axes·results
  "scripts/build/sync_satellites_js.py"               # assets/parties.js ← satellites.json
  "scripts/build/sync_view_thumbs_js.py"              # election-timeline.js ← view_registry.json
  "scripts/build/sync_static_figures.py"             # tracker·parties·홈·재보궐 그림 ← og/static/
  "scripts/build/sync_home_status.py"                # 홈 상단 3칸 정적 시드 ← timeline.json
  "scripts/build/sync_page_seeds.py"                 # 연표·재보궐 정적 시드
  "scripts/normalize/validate_reaggregation.py 22 21" # reaggregated/validation_22__21.json
  "scripts/normalize/validate_reaggregation.py 21 20" # reaggregated/validation_21__20.json
)

# 실패한 생성기의 출력을 보여준다. 버리면 CI 로그에 '실패' 한 줄만 남아 왜 죽었는지
# 알 수 없다 — build_sitemap이 CI에서만 죽었을 때 로그로는 아무것도 알 수 없어
# shallow clone을 손으로 재현해야 했다.
LOG=$(mktemp)
run() {  # run <표시명> <명령...>
  printf '  %-50s' "$1"; shift
  if "$@" >"$LOG" 2>&1; then echo "ok"; else
    echo "실패"; echo; sed 's/^/      /' "$LOG" | tail -15; echo; rm -f "$LOG"; exit 1
  fi
}

echo "생성기 ${#GENERATORS[@]}개 재실행"
for g in "${GENERATORS[@]}"; do run "$g" $PY "scripts/build/$g.py"; done

echo "파생물 ${#DERIVED[@]}개 재실행"
for cmd in "${DERIVED[@]}"; do
  # shellcheck disable=SC2086
  run "$cmd" $PY $cmd
done
rm -f "$LOG"

# 검사 대상은 **생성 산출물**이다. 새 스크립트를 추가하는 중이라 untracked 파일이
# 있는 것은 정상이므로, 추적 중인 변경 + 생성 경로의 새 파일만 본다.
OUT_PATHS=(person party region history polls archive share sitemap.xml robots.txt
           index.html elections.html
           assets/person-index.json assets/parties.js data/timeline.json
           data/comparisons data/sitemap_lastmod.json
           data/parties/lifecycle.json data/parties/political_axes.json
           data/parties/family_vote_share.json data/reaggregated)
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
