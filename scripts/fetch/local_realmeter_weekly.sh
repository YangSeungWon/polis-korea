#!/usr/bin/env bash
# 리얼미터 자체발표 국정평가 — 로컬 주간 회수.
#
# realmeter.net은 GitHub Actions 러너 IP를 막아 CI에선 늘 0건이다(docs/operations.md).
# 그래서 이 PC의 systemd user timer(polis-realmeter.timer)가 매주 이 스크립트를 돌린다.
# 아무도 안 돌려서 2026-11-06 이후 2주가 밀렸고 Live service health가 7일 빨갰다.
#
# 원칙
#   · 사람 작업과 섞지 않는다: master가 아니거나 추적 파일에 변경이 있으면 건너뛴다.
#   · 신규가 없으면 아무것도 바꾸지 않는다.
#   · full_gate를 통과해야만 커밋·push한다. 실패하면 stage된 채로 두고 알린다.
#
# 수동 실행: bash scripts/fetch/local_realmeter_weekly.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
PY=.venv/bin/python
FILES=(data/polls/approval_realmeter.json data/sitemap_lastmod.json
       index.html sitemap-main.xml tracker.html)

log()  { echo "[$(date '+%F %T')] $*"; }
note() { log "$1"; command -v notify-send >/dev/null &&
         notify-send -a polis "리얼미터 주간 회수" "$1" 2>/dev/null || true; }
die()  { note "실패: $1"; exit 1; }

[ "$(git branch --show-current)" = master ] || { note "건너뜀: master 아님"; exit 0; }
git diff --quiet && git diff --cached --quiet || { note "건너뜀: 작업 중인 변경 있음"; exit 0; }
git pull -q --ff-only || die "git pull 실패"

before=$("$PY" -c "import json;print(len(json.load(open('data/polls/approval_realmeter.json'))['records']))")
"$PY" scripts/fetch/fetch_realmeter_self.py --max-pages 3 || die "fetch 실패"
"$PY" scripts/parse/extract_approval_realmeter.py --source self || die "extract 실패"
if git diff --quiet -- data/polls/approval_realmeter.json; then
  log "신규 없음 (n=$before)"; exit 0
fi

for s in build_tracker_static build_home_capabilities build_sitemap; do
  "$PY" "scripts/build/$s.py" || die "$s 실패"
done
git add -- "${FILES[@]}"
after=$("$PY" -c "import json;print(len(json.load(open('data/polls/approval_realmeter.json'))['records']))")

if ! bash scripts/audit/full_gate.sh; then
  die "full_gate 실패 — 변경은 stage된 채로 남김 (n $before→$after)"
fi
git commit -q -m "리얼미터 국정평가 자체발표 회수 (로컬 주간 자동): $(date +%F)" \
  || die "commit 실패"
git push -q || die "push 실패 — 로컬 커밋만 있음"
note "완료: n $before→$after, push됨"
