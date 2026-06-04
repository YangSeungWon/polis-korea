# assets/archive/

회차 아카이브 페이지 JS — 5개 파일로 분리.

```
shared.js   → SIDO_ORDER · ssh · pcol · mainParty(위성정당)
              · filterPoll · renderPollsList · renderTrendSVG (공용)
local.js    → Archive.local.render(ctx)    지선 (광역단체장 17 시도)
pres.js     → Archive.pres.render(ctx)     대선 (전국 1 + 시도 17)
              · renderExitPoll exports (총선이 재사용)
general.js  → Archive.general.render(ctx)  총선 (지역구 254 + 비례)
core.js     → 엔트리 IIFE: meta load → fetch → kind 분기 dispatch
```

## 로드 순서

HTML이 정확히 이 순서로 5개 script 태그 (archive/{id}/index.html 참조).

```html
<script src="assets/archive/shared.js"></script>
<script src="assets/archive/local.js"></script>
<script src="assets/archive/pres.js"></script>
<script src="assets/archive/general.js"></script>
<script src="assets/archive/core.js"></script>
```

core 이전 4개는 `window.Archive` 네임스페이스에 helpers·모드 attach만.

## ctx 객체

core.js가 만들어서 모드별 `render(ctx)` 에 전달:

```js
ctx = {
  meta: {                   // 회차 메타 — data/elections/{id}.json 에서
    id, name, date,
    electionKind,           // canonical: presidential|general_election|local
    electionN, sgTypecode,
    proportionalSgTypecode, // 총선만, '7'
    resultsPath, pollsPath, exitPollPath, byelectionId,
    pollsWindow: { start, end },
  },
  results,                  // data/results/{id}.json (또는 null)
  polls,                    // 필터된 폴 배열 (또는 null)
  byReasons,                // 재보궐 사유 배열 (지선만 사용)
  exitData,                 // data/exit_polls/{id}.json
  sgTypecode,               // 해결된 sg_typecode
}
```

## 신규 모드 추가

1. `assets/archive/{kind}.js` 생성 — `window.Archive.{kind} = { render(ctx) }`
2. archive HTML에 script 태그 추가
3. `core.js` 분기에 한 줄 추가

기존 mode를 가져다 쓸 수도 있음 — 예: 총선이 `Archive.pres.renderExitPoll(ctx)` 재사용.
