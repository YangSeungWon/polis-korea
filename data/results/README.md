# data/results/

역대 선거 결과 — `/history` 페이지가 fetch.

파일명: `{type}_{n}.json`
- type: `presidential` | `national_assembly` | `local`
- n: 회차

스키마 (잠정):
```json
{
  "_meta": {
    "type": "presidential",
    "n": 21,
    "date": "2025-06-03",
    "label": "21대 대선",
    "source": "info.nec.go.kr/electioninfo"
  },
  "national": {
    "candidates": [
      {"name": "이재명", "party": "더불어민주당", "votes": 17287513, "pct": 49.42},
      {"name": "김문수", "party": "국민의힘",     "votes": 14395639, "pct": 41.15}
    ],
    "turnout": 79.4
  },
  "sigungu": [
    {
      "sido": "서울특별시",
      "name": "종로구",
      "code": "11010",
      "turnout": 80.6,
      "candidates": [
        {"name": "이재명", "party": "더불어민주당", "votes": 32154, "pct": 52.3},
        {"name": "김문수", "party": "국민의힘",     "votes": 24371, "pct": 39.6}
      ]
    }
  ]
}
```

총선(national_assembly)은 시군구 단위에 비례대표 정당투표 합산, 또는 별도 `district` 필드에 지역구별 의석 정보를 두는 방향 검토.

### 무투표 당선 (`uncontested`)

단독 출마로 개표 없이 당선된 지역구는 개표 기반 소스(WWolf TSV)에 행이 없다. `district[]`에 `"uncontested": true` + 후보 `votes/pct: null`로 추가한다. UI는 "무투표 당선 · 단독 출마"로 표시 (득표율 막대 대신).
출처: data.go.kr **무투표선거구 정보 API** (`WtvtelpcInfoInqireService`).
예) 20대 경남 통영시고성군 — 이군현(새누리당).

수집 스크립트: `scripts/fetch/scrape_results.py` (TBD).
