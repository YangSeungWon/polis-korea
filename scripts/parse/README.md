# scripts/parse/

raw (PDF · OCR · XLSX · CSV) → 중간 JSON (`data/raw/parsed/*.json`).

| 스크립트 | 역할 |
|---|---|
| `parse_pdf.py` | NESDC PDF parser (메인) |
| `parse_pdf_v2.py` | 다음 세대 parser (실험) |
| `parse_words.py` | word-level 분석 helper |
| `parse_district_nec.py` | NEC 지역구 페이지 parser |
| `parse_kr_stats.py` | KOSIS 통계 |
| `parse_local_xlsx.py` | 지선 legacy XLSX |
| `cid_decode.py` | PDF CID 인코딩 디코더 |
| `ocr_hybrid.py` | text+image hybrid OCR fallback |
| `run_ocr_batch.py` | OCR batch driver |
| `patch_cross_tab.py` | 여론조사꽃 cross-tab PDF 사후 fix (영구 routine) |
| `extract_pres_region.py` | 전국 대선 조사 PDF의 **권역별 후보지지 cross-tab → 시도 sidecar**. 대선은 조사가 대부분 전국이라 지역 지도가 빔 → 권역 행을 시도로 풀어 채움. `pres_region_{19,20,21}pres.json` 생성, `build_polls_pres`가 읽어 시도 행 emit. (캐시 `.pres_region_cache.json`, gitignore) |

루틴은 `parse_pdf.py` + `patch_cross_tab.py`. 대선 폴 빌드 전엔 `extract_pres_region.py <election_id>`.
