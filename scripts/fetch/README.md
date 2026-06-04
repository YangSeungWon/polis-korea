# scripts/fetch/

외부 데이터 다운로드 — NEC API · NESDC · 위키 · raw PDF.

| 스크립트 | 출력 |
|---|---|
| `fetch_nec_results.py --election {id}` | `data/results/{id}.json` (data.go.kr OpenAPI · 인증키 필요 · 확정/배치) |
| `fetch_nec_live.py --election {id}` | `data/results/{id}.json` (info.nec.go.kr 개표방송 · 인증키 X · 실시간 잠정 `is_final=false`) |
| `fetch_nec_byelection.py` | NEC 재보궐 raw |
| `fetch_nec_roster.py` | 후보 명부 |
| `fetch_byelection_reasons.py` | 재보궐 사유 → `data/byelection_reasons.json` |
| `fetch_district_full.py`·`fetch_districts_api.py` | 지역구 메타 |
| `fetch_local_full.py` | 지선 종합 (legacy 회차) |
| `fetch_proportional_api.py` | 비례 정당 매핑 |
| `fetch_uncontested.py` | 무경쟁 지역 |
| `fetch_exit_polls.py --id {id}` | 위키 출구조사 → `data/exit_polls/{id}.json` |
| `scrape_nesdc.py` | NESDC 등록 폴 list + PDF 다운로드 |
| `scrape_results.py` | NEC 화면 스크랩 (특수 케이스) |
| `redownload_orphans.py`·`refresh_pending_pdfs.py` | 누락 PDF 재시도 |

루틴은 `scrape_nesdc.py` 와 `fetch_nec_results.py` (워크플로 자동 — OpenAPI INFO-03 시 `fetch_nec_live.py` fallback).
