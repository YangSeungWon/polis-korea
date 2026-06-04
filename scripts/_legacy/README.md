# scripts/_legacy/

1회용 grid·hex layout iteration 도구. 한 번 만든 후엔 다시 안 돌림.
신규 작업 시 참조용으로만 — 의도적으로 main 디렉토리에서 분리.

| 스크립트 | 작업 |
|---|---|
| `apply_capital_layout.py`·`apply_korea_layout.py` | 수도권·전국 hex 초기 배치 |
| `compact_korea_layout.py` | 전국 압축 |
| `refine_capital.py`·`refine_district_hex.py`·`refine_hex.py`·`refine_sigungu_hex.py` | hex iter 개선 |
| `build_district_hex_22.py`·`build_district_hex_v2.py` | 22대 지역구 hex (build_zone_hex로 대체됨) |
| `build_sigungu_hex.py` | 시군구 hex (build_zone_hex로 대체됨) |
| `gen_district_hex_semantic.py` | semantic 그룹 hex |
| `extract_grids.py` | OCR 그리드 추출 |
| `fill_holes.py` | hex 빈칸 메움 후처리 (build_district_hex_v2·22가 import) |

현재 hex는 `data/geo/*hex*.json`로 영구. 재생성은 `scripts/build/build_zone_hex.py`.
