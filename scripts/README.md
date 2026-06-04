# scripts/

68개 Python 파이프라인 — 디렉토리로 단계 분리.

```
scripts/
  _geo.py · _hex.py · _ocr.py            # 시도·시군구 정규화·hex 좌표·OCR helper
  election_meta.py · poll_terms.py       # 회차 메타 loader, 정당명·필드 사전
  fetch/    → 외부 다운로드 (NEC API · NESDC · 위키 · raw PDF)
  parse/    → raw → 중간 JSON (PDF · OCR · XLSX → parsed/*.json)
  build/    → 중간 → 사이트 JSON (data/polls · data/results · data/timeline)
  audit/    → 점검·검증 (golden test · quality report · hex 평가)
  _legacy/  → 1회용 grid/hex layout iteration (한 번 만들면 다시 안 돔)
```

## 표준 1회 사이클 (선거 직전 ~ 직후)

```bash
# 0. 회차 메타
python3 scripts/election_meta.py --id 9th-local-2026

# 1. 폴 — NESDC CSV·PDF 수집 → 파싱 → aggregate
python3 scripts/fetch/scrape_nesdc.py
python3 scripts/parse/parse_pdf.py 'data/raw/pdf/*.pdf'
python3 scripts/parse/patch_cross_tab.py
python3 scripts/build/build_polls.py

# 2. 결과 — NEC API 개표
python3 scripts/fetch/fetch_nec_results.py --election 9th-local-2026

# 3. 출구조사 — 위키 fetch
python3 scripts/fetch/fetch_exit_polls.py --id 9th-local-2026

# 4. 부가
python3 scripts/build/build_byelection.py
python3 scripts/build/build_timeline.py
python3 scripts/build/optimize_data.py

# 5. 점검
python3 scripts/audit/audit_quality.py
```

[docs/cycle-workflow.md](../docs/cycle-workflow.md) 참조.

## 경로 규약

스크립트 안에서:
```python
ROOT = Path(__file__).resolve().parents[2]                # repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/ → _geo 등 import
```

cross-subdir 호출 필요 시 (예: build/ 가 parse/ 모듈 import) sibling dir도 path 추가.
