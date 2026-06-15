# polis-korea 운영 모델

> 메타가 데이터, 코드가 사이클. 메타 1줄 수정으로 사이트가 다음 선거로 자연 전환.

## 시점별 사이트 상태

| 시점 | 페이지 모드 | 사용자 의도 | 자동/수동 |
|---|---|---|---|
| 선거 6개월~1주 전 | 여론조사 시계열·후보 카드·시군구 hex | "여론 추세?" | cron daily |
| 공표금지 (D-6 00시 ~ D-day 18시) | "공표금지 중" 배너, 신규 차단 | "마지막 추세?" | 메타 `blackout` |
| 선거 당일 18시~ | 출구조사 → 실시간 개표 | "결과?" | fetch_nec_results 빈번 |
| 선거 직후 1주 | 확정 결과 + 여론조사 vs 결과 비교 카드 | "정확도·분석" | cron daily |
| 선거 후 1~6개월 | archive 이동, index가 다음 선거로 | "다음 선거?" | 메타 변경 |
| 선거 사이 (active 0) | history만 + "다음 선거 미정" | "역대 보기" | passive |

## 핵심 추상

`data/elections/index.json`의 `active`·`archive` 배열을 사람이 수정하면 사이트가 자동 전환:

```json
// 지선 임박 (현재)
{ "active": ["9th-local-2026"], "archive": [...] }

// 지선 끝나면
{ "active": ["21st-pres-2027"], "archive": ["9th-local-2026", ...] }
```

`scripts/election_meta.py`의 `current_election()`이 오늘 기준 가장 가까운 active 반환.

## 데이터 흐름

```
NESDC + NEC API → cron → parse → build → polls.json → site
                                              ↑
                  data/elections/*.json (메타) — 모든 동작 기준
```

자동 처리:
1. 선거별 시각화 단위 (지선=시군구·총선=지역구·대선=시군구+인구비례) — 메타 `offices.scope`
2. 공표금지 — 메타 `blackout`
3. NESDC scrape `gubun` — 메타 `nesdc.gubun`
4. NEC 개표 fetch `sg_id` — 메타 `nec.sg_id`
5. 통합 시도 (전남광주 등) — 메타 `sido_merge`
6. 자체조사 후보 정당 매핑 — 메타 `candidates_overrides`

## 사람 손길

| 빈도 | 작업 |
|---|---|
| 새 선거 사이클당 1회 | 메타 파일 작성 (`data/elections/{id}.json`, ~30분) |
| 선거 직후 | `index.json`의 active → archive 이동 (1줄) |
| 가끔 | 사용자 신고 fix |
| 분기 1회 | PDF Release 재업로드 (cache 한도 관리) |

## 1년 운영 예시 (2026~2027)

```
2026-05-30 (오늘): 9회 지선 active
2026-06-03 18시~: 출구조사·개표 모드
2026-06-04: 확정 결과 + 비교 카드 출시
2026-07: 9회 지선 archive로 (index.json 1줄 수정)
2026-07~2027-02: active 0 또는 21대 대선 메타 미리 active (6개월 전)
2027-03-08: 대선 당일 → 결과
2027-09 가을 보궐 (있다면): 별도 byelection active 추가
2028-04: 22대 총선 active (지역구 hex 활성)
```

## 인프라

- **호스팅**: GitHub Pages — polis.ysw.kr
- **데이터 갱신**: GitHub Actions cron (매일 KST 06:37)
- **raw PDF 캐시**: actions/cache (5GB까지, restore-keys로 누적)
- **Base seed**: GitHub Release (분기 1회 재업로드)
- **검증**: tests/test_golden + tests/test_build_golden + scripts/audit_quality (error 시 워크플로 실패 → 자동 알림)

## 빌드 — TS 지도 모듈 + 정적 프리렌더

지도 모듈은 **TypeScript 소스**(`src/history/`)를 esbuild로 번들해 IIFE JS로 생성한다. 생성물은 **직접 편집 금지**(상단 배너 `// ⚠️ 생성 파일`), `.ts`를 고치고 CI가 빌드.

| 소스(.ts) | 생성물(.js) | 빌드 |
|---|---|---|
| `src/history/hexgrid.ts` | `assets/hexgrid.js` | `npm run build:hexgrid` |
| `src/history/geomap.ts` | `assets/history/geomap.js` | `npm run build:geomap` |

- `npm run build:map`(=둘 다) + `npm run typecheck`(`tsc --noEmit`)는 Pages 배포 전 CI에서 실행.
- `geomap.ts`는 회차→경계 매핑의 단일 출처: `PRES_SGG_GEO_YEAR`(13~21대 SGIS 연도)·`PRES_HGIS_ROUNDS`({2..7}=HGIS)·`LOCAL_SGG_GEO_YEAR`·`PERIOD_SIDO_YEARS`(시도 외곽선)·`LOCAL_SIDO_CODE2`.

정적 프리렌더(Python): `build_static.py`가 `polls.html`/템플릿 + `__INITIAL_STATE__` 주입으로 `/governor`·`/mayor`·`/superintendent`·`/party`·`/polls/{id}/`·`/history/{type}/{n}/` + `sitemap.xml` 생성. `sync_archive_html.py`가 `archive/{id}/index.html` + `data/archive_index.json`(대시보드 역대 타임라인 소스) 생성. `sync_nav_html.py`가 NAV 마커 사이 헤더 nav 동기화(idempotent). HTML `<script>`/메타 바꾸면 `build_static.py` 재생성 필수.

공용 프런트엔드 컴포넌트(ElectionTimeline·LensSwitcher·시도/시군구 hex 캐논)는 `docs/shared-components.md`.

## 디렉터리 구조

```
.
├── *.html                          # 정적 페이지 (index·polls·history·byelection)
├── assets/                         # CSS·JS
├── data/
│   ├── elections/                  # 선거 메타 (사이클 정의)
│   │   ├── index.json              # active·archive 레지스트리
│   │   ├── {id}.json               # 각 선거 메타
│   │   └── {id}-candidates.json    # 자체조사 후보 매핑
│   ├── polls/                      # 빌드 결과 (aggregated·byelection·history)
│   ├── results/                    # 개표 결과 (선거별)
│   ├── geo/                        # 시군구·지역구 hex 좌표
│   ├── sources.json                # 데이터 출처 레지스트리
│   └── raw/                        # gitignore (원본 PDF·CSV)
├── src/history/                    # TS 지도 모듈 소스 (→ esbuild → assets/*.js)
├── scripts/                        # Python 파이프라인 + 메타 loader
├── tests/                          # golden + build_golden + audit
└── docs/                           # 이 문서들
```
