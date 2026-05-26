# data/polls/ — 9회 지선 (2026) 여론조사

메인 페이지 (`index.html`)가 fetch. NESDC 등록 조사 인용·재시각화.

## 파일

| 파일 | 설명 |
|---|---|
| `aggregated.json` | UI fetch 대상. 다자대결 문항 1개 = 1 레코드. |
| `byelection.json` | 재·보궐 폴 (`byelection.html`) |

## 데이터 흐름

```
NESDC 게시판 (nesdc.go.kr)
  ↓ scripts/scrape_nesdc.py — Playwright (JSF anti-scrape)
  ├ raw/nesdc_9th_polls.csv  (메타: 등록번호·기관·의뢰자·시도 등)
  └ raw/pdf/{regno}_*.pdf    (공시 PDF 첨부)
      ↓ scripts/parse_pdf.py — pdftotext + OCR fallback
      raw/parsed/{regno}_{hash}_{filename}.json  (정제 문항)
          ↓ scripts/build_polls.py — 메타 + 파싱 결과 join
          polls/aggregated.json
              ↓ assets/polls.js fetch
              UI (지도/격자 + 시도·시군구 단위 group)
```

## 원본 출처

| 출처 | 활용 | 형식 | 비고 |
|---|---|---|---|
| **NESDC** (nesdc.go.kr) | 등록 폴 메타 + 공시 PDF | HTML/PDF | `scrape_nesdc.py` (Playwright + JSF viewstate) |
| **수동 patch** | PDF 파싱 실패 케이스 | manual JSON | `raw/parsed/` 직접 편집 가능 |

## 스키마 (aggregated.json polls[])

```json
{
  "regno": "16348",
  "office_level": "광역단체장",
  "sido": "경기도",
  "sigungu": null,
  "requester": "데일리리서치",
  "agency": "데일리리서치",
  "period_start": "2025-07-04",
  "period_end": "2025-07-04",
  "sample_n": 1003,
  "response_rate": 8.4,
  "margin": 3.1,
  "candidates": [
    {"name": "김동연", "party": "더불어민주당", "pct": 51.2},
    {"name": "오세훈", "party": "국민의힘",    "pct": 38.4}
  ],
  "is_self_poll": false,         // 정당·후보 본인 의뢰 여부
  "source_url": "https://nesdc.go.kr/..."  // traceability
}
```

`office_level` 종류:
- `광역단체장`, `기초단체장`, `교육감` — 후보별 다자대결
- `정당지지`, `국정평가`, `투표의향` — 메트릭

## 법적 의무

- 인용 시 의뢰자·기관·조사기간·표본수·응답률·표본오차 표시
- 정당·후보자 본인 의뢰 (`is_self_poll=true`) → UI 제외
- **블랙아웃**: 2026-05-28 00:00 ~ 06-03 18:00, 신규 공표 금지. UI는 그 기간 5/27 이전 등록 조사만 노출.

## 수집 명령

```bash
# 1. NESDC 신규 폴 메타+PDF 다운로드
.venv/bin/python scripts/scrape_nesdc.py

# 2. PDF 파싱
.venv/bin/python scripts/parse_pdf.py

# 3. aggregated.json 빌드
.venv/bin/python scripts/build_polls.py
```

## 알려진 한계

- PDF 형식 비표준 → OCR fallback에 정확도 의존.
- NESDC가 일부 PDF 다운로드 차단 (회원 only). 그런 경우 메타만 있고 본문 못 가져옴.
- 블랙아웃 기간 신규 등록 차단 (NESDC 규정).
