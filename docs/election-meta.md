# election meta 스키마

`data/elections/` 내 메타 파일 구조. `scripts/election_meta.py`가 read.

## index.json

```json
{
  "active": ["9th-local-2026", "9th-byelection-2026"],
  "archive": ["21st-pres-2025", "22nd-general-2024", ...]
}
```

- `active`: 진행 중·임박 선거. `current_election()`이 가장 가까운 active 반환
- `archive`: 종료. history.html에서 시각화

## id 규칙

`{회차}{접미}-{타입}-{년도}` (kebab-case):

| 타입 | 예시 | 비고 |
|---|---|---|
| `local` | `9th-local-2026` | 전국동시지방선거 |
| `general` | `22nd-general-2024` | 국회의원선거 (총선) |
| `pres` | `21st-pres-2025` | 대통령선거 |
| `byelection` | `9th-byelection-2026` | 재보궐 (직전 지선·총선 회차) |

회차 접미: 1st·2nd·3rd·{N}th.

## 메타 파일 — {id}.json

### 필수 필드

```json
{
  "id": "9th-local-2026",
  "name": "제9회 전국동시지방선거",
  "type": "local",
  "date": "2026-06-03"
}
```

### 선택 필드

| 필드 | 용도 | 예시 |
|---|---|---|
| `blackout` | 공표금지 자동 차단 | `{"start": "2026-05-28T00:00:00+09:00", "end": "2026-06-03T18:00:00+09:00"}` |
| `nesdc` | NESDC scrape 설정 | `{"gubun": "VT026", "csv": "data/raw/nesdc/list.csv"}` |
| `nec` | NEC OpenAPI fetch | `{"sg_id": "20260603", "roster": "data/raw/nec_roster.json"}` |
| `offices` | 선거 office 정의 | `[{"level":"광역단체장","sg_typecode":"3","scope":"sido"}, ...]` |
| `sido_merge` | 통합 시도 (전남광주 등) | `[{"canonical":"전남광주특별시","merge_from":["광주광역시","전라남도"]}]` |
| `candidates_overrides` | 자체조사 후보 정당 매핑 파일 | `"data/elections/9th-local-2026-candidates.json"` |
| `results_file` | 옛 선거 — 기존 결과 파일 위치 | `"data/results/local_8.json"` |
| `districts` | byelection — 지역구별 후보·좌표 | `{"평택을": {...}}` |

### offices 정의

| level | sg_typecode | scope |
|---|---|---|
| 대통령 | 1 | nation |
| 국회의원 | 2 | district |
| 광역단체장 | 3 | sido |
| 기초단체장 | 4 | sigungu |
| 광역의원 | 5 | district |
| 기초의원 | 6 | district |
| 교육감 | 11 | sido |

`scope`는 시각화 단위:
- `sido` → 17 시도 hex
- `sigungu` → 250 시군구 chloropleth
- `district` → 지역구 hex (총선)
- `nation` → 전국 합계 (대선)

### sido_merge

선거 사이클에 따라 행정구역이 바뀌는 경우 (예: 9회 지선부터 광주+전남 = 전남광주특별시):

```json
"sido_merge": [
  {
    "canonical": "전남광주특별시",
    "merge_from": ["광주광역시", "전라남도"],
    "trigger_keyword": "전남광주통합",
    "nec_sgg": "전남광주통합특별시"
  }
]
```

- `canonical`: 통합 후 명칭 (코드에서 사용)
- `merge_from`: NEC API·PDF에서 등장하는 옛 명칭들
- `trigger_keyword`: PDF 파서가 통합 인식하는 키워드
- `nec_sgg`: NEC API의 sgg_name 필드값

## candidates overrides — {id}-candidates.json

자체조사 PDF·정당 미명기 후보의 정당 매핑 fallback:

```json
{
  "_note": "자체조사 PDF의 정당 미명기 후보 → 정당 매핑.",
  "더불어민주당": ["오중기", "김동연", ...],
  "국민의힘": ["이철우", ...],
  "조국혁신당": [...]
}
```

`load_candidates_overrides(election_id)` → `{후보명: 정당}` flat dict로 반환.

## 검증

```bash
python3 scripts/election_meta.py --list             # 전체 보기
python3 scripts/election_meta.py --current          # 오늘 active
python3 scripts/election_meta.py --id 9th-local-2026  # 단건
```
