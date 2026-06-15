# 공용 프런트엔드 컴포넌트 (UI/UX)

여러 페이지가 공유하는 바닐라 JS 컴포넌트·렌더러. 한 곳에서 고치면 폴·아카이브·역대·대시보드가 같이 바뀐다(단일 렌더러 원칙). 페이지별 로드는 각 `*.html`의 `<script>` 순서 참조.

---

## ElectionTimeline — 선거별 3레인 타임라인 (`assets/election-timeline.js`)

대선·총선·지선 3레인 타임라인 디렉터리. **대시보드(홈 "역대 직접 결과")**와 **폴 허브(`assets/polls/election-index.js`)**가 공유한다. 데스크톱=SVG 가로축, 모바일=유형별 칩(CSS 미디어쿼리 `≤560px`로 토글, 스타일은 `common.css`의 `.poll-tl-*`/`.ptc-*`).

```
ElectionTimeline.render(host, list, opts)
  list = [{slug, name, date, n, type?, party?}]   // type 없으면 slug로 대선/총선/지선 판별
  opts = {
    hrefFn(e)→url,            // 노드 링크 (대시보드=/archive/{slug}/, 폴허브=/polls/{slug}/)
    current(slug|null),       // 강조할 회차(없으면 최신)
    ariaFn(e)→str, note(html), curSuffix,
    nodeColorFn(e, laneColor, isCur)→color,   // 노드 색. 없으면 레인색
  }
```

- **노드 색 정책**: 폴 허브는 `nodeColorFn` 미전달 → **레인색**. 대시보드는 `(e,lane,isCur)=>isCur?lane:중립회색` → **중립 단색 + 최신만 포인트**(정당 rainbow 안 씀; 정당은 hover 툴팁에만). 라벨 텍스트는 항상 레인색(유형 구분).
- 노드 크기 균일(`r=6`), 선택 강조는 외곽 링 + 중앙 흰점(크기 안 키움). 모바일 칩은 ★ 없이 `.is-current`로 강조.
- 연도 눈금: 범위>30년이면 10년, 좁으면 2년 간격.

---

## LensSwitcher — 선거 렌즈 바 (`assets/lens-switcher.js`)

같은 과거 선거를 보는 **3가지 면**을 잇는 바. 어디로 들어와도 한 번에 다른 렌즈로 이동.
종합 결과(`archive/{id}`) · 여론조사 vs 실제(`polls/{id}`) · 역대 흐름(`history/{type}/{n}`).

```
LensSwitcher.mount({ current:'archive'|'polls'|'history', type, n, date?, id?, host? })
  type = 'presidential'|'national_assembly'|'local',  n = 회차,  id = slug(없으면 deriveId로 유도)
```

- **존재하는 렌즈만** 노출: archive=항상, polls=`election_index.json`에 있을 때, history=`results/manifest.json`에 있을 때(비동기 fetch 후 표시).
- 배치: 아카이브=breadcrumb 뒤, 폴=선거 제목 바로 위(`#lens-switcher-host`, 허브에선 no-op), 역대=컨트롤과 viz 사이.

---

## 시도 1위색 hex — `Archive.governorHex.draw` (`assets/archive/render-governor-hex.js`)

17 시도 hex, 1위 정당색 단색. **아카이브 광역장 + 폴(광역장·대선) + history**가 공유하는 캐논.

```
Archive.governorHex.draw(host, races, opts)
  opts = {
    winnerOf(sido)→win,       // 폴/history: 시도별 1위(레이아웃 키 순회). 없으면 races 배열 사용
    layout,                   // 회차별 레이아웃 override(세종 신설 전·전남광주 분리 등)
    skipSido(sido)→bool,      // 승격 전 회차 셀 숨김
    opacityOf(win)→0..1,      // 폴 신뢰도(저신뢰 0.4·격차 비례)
    dashOf(win)→'3,2'|null,   // 폴 저신뢰·n≤2 점선
    onSelect(sido), selected,
  }
```

`전남광주특별시` 1위가 있으면 `honamMergedLayout`로 광주·전남 병합 레이아웃 자동 적용.

---

## 시군구 1위색 hex — `drawSigunguHex` (`assets/render-sigungu-hex.js`)

시군구 choropleth hex. **폴(기초장) + history(시군구) + 아카이브** 공유.

```
drawSigunguHex(svg, cells, resultFn, opts)
  cells = [{sido, name, c, r}]      // code 불필요. period 레이아웃(sigungu_hex_local) 그대로 사용 가능
  resultFn(sido, name)→result
  opts = {
    opacityOf(result), dashOf(result),     // 폴 신뢰도 보존
    tooltipOf(sido,name,result)→str,
    onSelect(sido,name,result,cell), selected:{sido,name},
    layout/underlay/margin/borderWidth/labelFn,
  }
```

> 시도 hex는 `governorHex`, 시군구 hex는 `drawSigunguHex`로 통일됨(폴/아카이브/역대 동일 렌더러). 폴 전용 신뢰도(불투명도·점선)는 반드시 `opacityOf`/`dashOf` opts로 보존할 것.

---

## Dashboard — 홈 대시보드 (`assets/dashboard.js`)

랜딩(`index.html`) 대시보드. 3패널(광역·기초·재보궐) 미리보기 + 선거 단계(시즌)별 데이터 전환(여론조사↔실제) + `#dash-election-dir`에 `ElectionTimeline`으로 역대 디렉터리(클릭→`/archive/{slug}/`). 시도 hex=`governorHex`, 시군구 hex=`drawSigunguHex` 재사용. 타임라인 스타일이 `common.css`에 있어야 함(대시보드는 `components.css` 미로드).

---

## 직위 코드 단일 출처 — `TC_OFFICE`

NEC `sg_typecode` → 표준 직위명. **JS `assets/parties.js`** + **Python `scripts/_geo.py`** 두 곳에 동일하게 유지(수동 동기, 자동 sync 없음 — 바꿀 때 둘 다).

| sg_typecode | 직위 | scope |
|---|---|---|
| 2 | 국회의원 | district |
| 3 | 광역단체장 | sido |
| 4 | 기초단체장 | sigungu |
| 5 | 광역의원 | (지선) |
| 6 | 기초의원 | (지선) |
| 11 | 교육감 | **sido** |

(교육감은 시·도 단위 선출이라 scope=`sido`. 일부 NEC API는 교육감 코드로 `5`를 쓰지만 결과 데이터/`TC_OFFICE`는 `11`.)
