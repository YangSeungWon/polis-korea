# scripts/build/

중간 JSON → 사이트 fetch JSON. 페이지가 직접 fetch하는 데이터 생성.

| 스크립트 | 출력 |
|---|---|
| `build_polls.py` | `data/polls/aggregated.json` (지선·일반) |
| `build_polls_pres.py` | `data/polls/aggregated_{회차}.json` (대선) |
| `build_byelection.py` | `data/polls/byelection.json` |
| `build_timeline.py` | `data/timeline.json` |
| `build_static.py` | 카드 JSON-LD·정적 메타 |
| `build_zone_hex.py` | hex 좌표 (모든 회차) |
| `build_district_22.py`·`build_district_20.py` | 지역구 결과 가공 |
| `build_sigungu_adjacency.py`·`build_sigungu_coastal.py` | 시군구 그래프·해안 |
| `build_geojson_district_map.py` | 지역구 GeoJSON 매핑 |
| `build_roster_gen.py` | 후보 명부 generation |
| `backfill_candidate_party.py`·`backfill_uncontested.py` | 누락 필드 채움 |
| `ingest_n21.py`·`ingest_wwolf.py` | 회차별 특수 ingest |
| `merge_local_legacy_into_new.py` | legacy → 통일 schema 병합 |
| `optimize_data.py` | JSON 크기 최적화 |
| `patch_byelection.py` | 재보궐 사후 patch |
| `rebuild_manifest.py` | manifest 재생성 |
| `update_method.py` | 폴 method 갱신 |
| `build_golden.py` | tests/golden 빌드 |
| `sync_satellites_js.py` | data/parties/satellites.json → assets/parties.js SATELLITE_TO_MAIN sync |
| `sync_archive_html.py` | data/elections/ → archive/{id}/index.html 자동 생성 (kind별 template) |

핵심 루틴: `build_polls` · `build_timeline` · `build_byelection`.
