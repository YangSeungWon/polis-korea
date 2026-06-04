# polis-korea 데이터 스키마 가이드

신규 회차·모드 작업할 때 매번 코드 추적하던 매트릭스를 한 페이지에 정리.

## 1. 회차 ID 규약

`{n}{th|st|nd|rd}-{kind}-{YYYY}` — 예: `21st-pres-2025`, `22nd-general-2024`, `9th-local-2026`, `8th-byelection-2025`.

`kind` ∈ `{pres, general, local, byelection}`. archive.js `electionKind`는 풀네임(`presidential`/`general_election`/`local`) 사용 — 변환 필요. 통일은 [election-meta.md] 참조.

## 2. 회차 메타 (`data/elections/`) — 단일 출처

```
data/elections/
  index.json              # { active: [...id], archive: [...id] }
  {id}.json               # 회차 모든 메타 (NEC + NESDC + archive + wiki)
```

**페이지·스크립트는 `assets/elections.js` 또는 `data/elections/{id}.json` 직독으로만 회차 정보 참조** — `window.__ARCHIVE__`는 `{ id }`만, 나머지는 레지스트리에서 derive.

전체 메타 구조 (대선 예):

```json
{
  "id": "21st-pres-2025",
  "name": "제21대 대통령선거",
  "kind": "presidential",         // canonical: presidential | general_election | local | byelection
  "type": "pres",                 // legacy 약칭 (호환용)
  "n": 21,
  "date": "2025-06-03",
  "status": "archive",            // archive | active | upcoming
  "nesdc": { "gubun": "VT027", "csv": "data/raw/..." },
  "nec": { "sg_id": "20250603" },
  "offices": [{ "level", "sg_typecode", "scope" }],
  "archive": {                    // archive 페이지 데이터 paths
    "page": "/archive/21st-pres-2025/",
    "results_path": "data/results/21st-pres-2025.json",
    "polls_path": "data/polls/aggregated_21pres.json",
    "exit_poll_path": "data/exit_polls/21st-pres-2025.json",
    "polls_window": ["2024-12-03", "2025-06-02"],
    "sg_typecode": "1",
    "proportional_sg_typecode": null,
    "byelection_id": null,
    "list_label": "확정"          // index.html 회차 목록 태그
  },
  "wiki_exit_polls": {            // fetch_exit_polls.py 소스
    "kind": "local" | "pres",
    "templates": [{ "page", "key", "name" }]
  }
}
```

신규 회차 추가 체크리스트:
1. `data/elections/{id}.json` 생성 — 위 구조대로 (archive 블록까지)
2. `data/elections/index.json` active/archive에 id 추가
3. `python3 scripts/build/sync_archive_html.py` — `archive/{id}/index.html` + `index.html` 회차 목록 동시 자동 생성
4. `assets/history.js`의 `ARCHIVE_PAGES`는 startup 시 레지스트리에서 자동 populate — 별도 작업 불필요

> archive HTML과 index.html 회차 목록 (`<!-- AR_LIST_START -->` ~ `END -->` 사이)은 절대 손으로 수정하지 말 것 — 다음 sync 실행 시 덮어쓰임. 변경은 `data/elections/{id}.json` 또는 `scripts/build/sync_archive_html.py` 템플릿에서.

## 3. 결과 (`data/results/{id}.json`)

**청크 분할** — 새 schema 파일은 `scripts/build/chunk_results.py` 가 두 파일로 분리:
- `{id}.json` — `_meta` + nation/sido/district race만 (`_meta.chunked: true` 표시)
- `{id}.sigungu.json` — sigungu/district_sigungu/sigungu_part race (drill-down용)

archive 페이지는 main race만 사용 (300 KB 이하). history 페이지는 chunked 감지 시 자동으로 sigungu 파일도 fetch + merge.

```json
{
  "_meta": { "election", "election_id", "election_date",
             "fetched_at", "is_final", "n_rows",
             "chunked": true },
  "races": [
    {
      "scope": "nation" | "sido" | "sigungu" | "district" | "district_sigungu" | "sigungu_part",
      "sg_typecode": "1" | "2" | "3" | "4" | "7" | "11",
      "sido": "서울특별시" | "",
      "sigungu": "종로구" | "",
      "district": "종로구" | "",                  // 지역구 (총선)
      "electors": int, "voters": int,
      "valid_votes": int, "invalid_votes": int, "abstain": int,
      "candidates": [
        { "name", "party", "votes", "pct",
          "rank": 1..N, "won": true (1위만) }
      ]
    }
  ]
}
```

### scope × sg_typecode 매트릭스 (회차 종류별 실측)

| 종류 | sg_typecode | 의미 | scope |
|---|---|---|---|
| **대선** | `1` | 대통령 | `nation` (1), `sido` (17), `sigungu` (~250) |
| **총선** | `2` | 지역구 국회의원 | `district` (~254), `district_sigungu` (분할구 ~330) |
| 총선 | `7` | 비례대표 | `nation` (1), `sido` (17), `sigungu` (~250) |
| **지선** | `3` | 광역단체장 | `sido` (17), `sigungu` (~250) |
| 지선 | `4` | 기초단체장 | `sigungu` (~220), `sigungu_part` (분할) |
| 지선 | `11` | 교육감 | `sido` (17), `sigungu` (~250) |

> 5·6·7회 지선의 `sigungu` × `3`/`11`이 같은 시군구를 두 번 카운트 — 한 race가 광역(`3`)·교육감(`11`)으로 중복됨. filter 시 sg_typecode 함께 봐야 함.

### 페이지에서 filter 패턴

```js
// 대선 전국
results.races.find(r => r.scope === 'nation' && r.sg_typecode === '1')
// 총선 지역구
results.races.filter(r => r.scope === 'district' && r.sg_typecode === '2')
// 지선 광역단체장
results.races.filter(r => r.scope === 'sido' && r.sg_typecode === '3')
// 총선 비례 (정당별 nation 득표)
results.races.find(r => r.scope === 'nation' && r.sg_typecode === '7')
```

candidates.party는 위성정당(국민의미래·더불어민주연합) 원본 그대로. 의석 합산하려면 `SATELLITE_TO_MAIN` 매핑 적용 — archive.js 참고.

## 4. 여론조사 (`data/polls/aggregated_{회차}.json`)

```json
{
  "_meta": { ... },
  "polls": [
    {
      "ntt_id": "NESDC 등록번호",
      "source_url": "NESDC view URL",
      "agency": "리얼미터 등",
      "co_agency", "requester",
      "is_self_poll": bool,                        // 정당·후보 자기조사 (표시 제외)
      "method": "ARS·전화면접·인터넷",
      "sample_size": int, "response_rate": float,
      "sample_error": "95% 신뢰수준에 ±2.2%P",
      "period_start": "YYYY-MM-DD",
      "period_end": "YYYY-MM-DD",
      "reg_date": "YYYY-MM-DD",
      "sido": "" | "서울특별시",
      "sigungu": "" | "종로구",
      "office_level": "대통령" | "광역단체장" | "기초단체장" | "교육감" | "정당지지",
      "office_label": "표시용 라벨 (예: 서울특별시장)",
      "metric_type": "후보지지" | "정당지지",
      "table_title": "원문 표 제목",
      "candidates": [
        { "name", "party", "pct" }                  // 정당지지 row는 name 비고 party만
      ]
    }
  ]
}
```

> `office_level === '정당지지'` 행은 후보 polls가 아닌 정당 polls — `metric_type`과 사실상 중복. archive.js Trend 함수는 `metric_type` 기준으로 분기.

### 회차별 파일

- `aggregated.json` — 9회 지선 (현재 active)
- `aggregated_8th.json` — 8회 지선
- `aggregated_21pres.json` — 21대 대선
- `aggregated_22nd.json` (예정) — 22대 총선
- `byelection.json` — 재보궐 통합

`pollsWindow`(window.__ARCHIVE__) 또는 회차 메타로 filter — `period_start`가 window 안.

## 5. 출구조사 (`data/exit_polls/{id}.json`)

```json
{
  "id": "21st-pres-2025",
  "election_name": "제21대 대통령선거",
  "election_date": "2025-06-03",
  "sources": [
    {
      "key": "kep_3sa" | "jtbc" | "channel_a" | "mbn",
      "name": "표시명",
      "released_at": "ISO8601",                      // 발표 시각
      "quote_after": "ISO8601",                      // 인용 보도 가능 시각 (KEP는 18:15)
      "office": "광역단체장" | "대통령",
      "results": {
        "전국": [{ "name", "party", "pct" }, ...],   // 대선만 (지선은 없음)
        "서울특별시": [{ ... }, ...],
        ...
      }
    }
  ]
}
```

- archive.js가 `now < quote_after`면 표시 안 함
- key가 일치하는 source는 갱신(`upsert_source`), 없으면 추가 — `released_at`·`quote_after`는 기존 값 보존
- 신규 회차는 `scripts/fetch/fetch_exit_polls.py SOURCES` dict에 page 매핑 추가

## 6. 타임라인 (`data/timeline.json`)

```json
{
  "events": [
    {
      "id", "kind": "presidential|general|local|byelection",
      "n": 21, "name", "date",
      "result": { "winner_party", "winner_name", "margin_pp" },
      "presCandidates": [{ name, party, votes, pct }],  // 대선만
      "partySeats": { "더불어민주당": 175, ... }         // 총선만
    }
  ]
}
```

`scripts/build/build_timeline.py`가 results에서 derive. 위성정당 합산 적용.

## 7. 재보궐 (`data/byelection_reasons.json`)

NEC API가 사유(rsn)·전임자(trprNm)·정당(plprNm)·발생일(rsnOcrnYmd)·선거구(elpcNm) 등 제공. `elctKndCd` ∈ {`2`=국회의원, `3`=광역, `4`=기초}.

## 8. 지리 (`data/geo/`)

- `sigungu_simple.json` — 250개 시군구 GeoJSON
- `district_22_geojson.json` — 22대 지역구 254곳
- hex 레이아웃은 [hex-layout.md] 참조

## 9. 정당 색·메타 (`assets/parties.js`)

```js
const PARTY_COLORS = { "더불어민주당": "#152484", "국민의힘": "#E61E2B", ... }
function partyColor(party) { ... }   // 위성정당도 본정당 색으로
```

신규 정당 등장 시 추가. **위성정당 → 본정당 매핑**은 `data/parties/satellites.json` 단일 출처 — Python `build_timeline.py`는 JSON 직접 read, JS는 `scripts/build/sync_satellites_js.py`가 `assets/parties.js`에 `SATELLITE_TO_MAIN` const 블록을 sync (마커 사이 자동 갱신).

## 10. 출처 (`data/sources.json`)

NEC·NESDC·OhmyNews·위키 등 모든 외부 데이터 출처 단일 레지스트리. 페이지 footer·sitemap image meta가 참조.

---

## 신규 회차 추가 워크플로 요약

1. `data/elections/{id}.json` 메타 작성
2. `data/elections/index.json` active/archive 갱신
3. **결과**: `scripts/fetch/fetch_nec_results.py --id {id}` → `data/results/{id}.json`
4. **폴**: NESDC CSV → `scripts/build/build_polls.py --csv ... --out data/polls/aggregated_{회차}.json`
5. **출구조사**: `scripts/fetch/fetch_exit_polls.py SOURCES`에 매핑 추가 → `data/exit_polls/{id}.json`
6. **타임라인**: `scripts/build/build_timeline.py` 재실행
7. **archive 페이지**: `archive/{id}/index.html` (모드별 템플릿) + `index.html` 목록 + `history.js` ARCHIVE_PAGES

각 단계가 어떤 스크립트·디렉토리에 있는지는 [cycle-workflow.md] 참조.
