# raw 데이터 관리

`data/raw/` 6.8 GB 14k 파일. git에서 제외되지만 다른 머신·새 clone에서
재현 가능해야 함. `data/raw/MANIFEST.json`이 카탈로그 + 재다운로드 명령.

## 디렉토리

| 경로 | 종류 | 크기 | 출처 |
|---|---|---|---|
| `pdf/` | source | 6.2 GB · 5,528개 | NESDC 등록 폴 PDF (질문지·결과) |
| `grids/` | derived | 541 MB | OCR 그리드 추출 — `parse/run_ocr_batch.py` |
| `parsed/` | derived | 9.4 MB | PDF 파싱 결과 — `parse/parse_pdf.py` |
| `results_csv/` | result_csv | 111 MB | NEC 결과 raw (legacy 회차 수동 다운로드) |
| `nec_district/` | result_csv | 26 MB | NEC 지역구별 xlsx |
| `nesdc_*_polls.csv` | source | 6 MB | NESDC list export |
| `nec_roster_*.json` | source | 280 KB | NEC OpenAPI 후보 명부 |
| `nec_candidate_*.json` | source | 60 KB | NEC API 후보 매핑 캐시 |
| `nec_uncontested/` | source | 28 KB | NEC 무투표 당선 캐시 |
| `ohmynews_*` | reference | 1.7 MB | 오마이뉴스 분석 데이터 |
| `wwolf/` | reference | 21 MB | wwolf 비례 시군구별 데이터셋 |

**source**: 외부 다운로드 원본. 손실 시 재다운로드 필요.
**derived**: 파이프라인이 source에서 생성. source가 있으면 재생성 가능.
**result_csv / reference**: 외부 데이터셋. NEC·OhmyNews에서 수동 다운로드.

## MANIFEST.json 구조

```json
{
  "_meta": { "scanned_at", "total_files", "total_bytes", "with_hash" },
  "summary": { "<source_kind>": { "count", "bytes" } },
  "sources": [{ "path", "kind", "source_kind", "source", "regenerate", "bytes", "mtime" }],
  "nesdc_pdf_files": [{ "ntt_id", "path", "bytes", "mtime" }],
  "derived": { "<source_kind>": { "kind": "derived", "regenerate", "count", "bytes" } },
  "unknown": [...]
}
```

- `source URL`이 있는 항목은 NESDC view URL pattern 등 derivable 형태로
- PDF는 ntt_id 별로 첨부 여러 개 가능 (질문지 + 결과보고서) — list 형태

## 운영

### 신규 raw 파일 추가 후
```bash
python3 scripts/build/build_raw_manifest.py        # MANIFEST 갱신
git add data/raw/MANIFEST.json                     # 추적
```

### 새 머신·clone 후 raw 점검
```bash
python3 scripts/audit/verify_raw.py
# 누락 시 source_kind별 재다운로드 명령 출력
```

### 일부 누락 PDF 복구
```bash
python3 scripts/fetch/redownload_orphans.py        # PDF 누락분만
python3 scripts/fetch/refresh_pending_pdfs.py      # pending list 갱신
```

### SHA256 무결성 검증 (느림)
```bash
python3 scripts/build/build_raw_manifest.py --hash  # ~10분
```

## 클라우드 sync 향후

현재 manifest 기반 재다운로드(NESDC view URL)만 지원. 6 GB PDF가 영구
저장 필요할 경우 옵션:

- **rclone + R2/B2** — 월 $0.5 정도, 6 GB. `rclone sync` 1줄.
- **HF Datasets / Zenodo** — 학술 archive 무료. 공개 라이선스 필요.

지금은 NESDC 원본 사이트가 살아있고 ntt_id별 fetch 가능하므로
manifest 우선. 외부 백업은 NESDC가 회차 종료 후 PDF 제거할 때 필요.

## gitignore 예외

```
data/raw/*               # 기본 제외
!data/raw/MANIFEST.json  # 카탈로그는 추적
!data/raw/nec_uncontested/
!data/raw/nec_candidate_*.json
!data/raw/nec_roster_*.json
```

MANIFEST.json + 소량 NEC 캐시만 git tracked — 새 clone에서도 `verify_raw.py`
바로 동작.
