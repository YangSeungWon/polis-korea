# 상시 tracker 파이프라인 (국정평가·정당지지·차기주자)

선거와 무관하게 **연속**으로 차오르는 여론 추이 — 대통령 국정평가, 정당지지도,
차기주자 선호 — 의 수집·추출·갱신 구조. 선거 사이클 빌드(`docs/cycle-workflow.md`)와
별개로 도는 **주간 파이프라인**이다.

## 1. 데이터 소스 — NESDC VT012 "기타"

NESDC(여심위 선거여론조사심의위)는 폴을 `pollGubuncd`로 분류한다. 선거별 코드
(VT025=22대총선, VT027=21대대선 …) 외에 **VT012 = "기타"** 가 선거에 묶이지 않는
**전국 정기조사**(갤럽·리얼미터·NBS·한국리서치 등의 주/월 단위 정례조사)를 담는다.

- 약 2,600건(2015~현재), 매주 수십 건씩 누적 → tracker의 **상시 소스**.
- 메타 CSV: `data/raw/nesdc_etc_polls.csv` (gitignore, 2,600여 행).
- 스크랩: `scripts/fetch/scrape_nesdc.py --gubun VT012 --csv data/raw/nesdc_etc_polls.csv`
  (증분 — `load_existing_ids`로 CSV에 없는 nttId만 신규 다운로드).

> 코드 맵은 메모리 `nesdc_gubun_codes` / `scrape_nesdc --gubun` 참고.

## 2. 추출기 6종

PDF를 **직접** 읽어(fitz/pdfplumber) 표를 파싱한다. `parse_pdf.py`(라우틴 파서)의
출력이 아니라 원본 PDF에서 바로 뽑는다. 모두 `extract_approval.load_meta()`(per-gubun
CSV)에 의존.

| 스크립트 | 출력 | 대상 | 비고 |
|---|---|---|---|
| `extract_approval_gallup.py` | `approval_gallup.json` | 갤럽 국정평가 | 월별 통합표 달 매칭 |
| `extract_approval_realmeter.py` | `approval_realmeter.json` | 리얼미터 | ASCII 괘선표 '전체' 행 |
| `extract_approval_nbs.py` | `approval_nbs.json` | NBS(전국지표) | 윤석열기 커버 핵심 |
| `extract_approval_hrc.py` | `approval_hrc.json` | 한국리서치 | |
| `extract_approval_general.py` | `approval_general.json` | 나머지 전 기관 | consensus 컷(4기관 월평균 ±20%p 초과 drop) |
| `extract_party_support.py` | `aggregated_etc.json` | 정당지지(VT012) | `{polls:[...]}` 구조 |

- **subject(어느 대통령 평가인가)** = 조사일 기준 현직(`extract_approval.president_on`,
  `PRESIDENT_TERMS`). 직무정지(탄핵소추~파면/기각) 기간 제외. 현재 테이블은
  **이재명 2025-06-04 ~ 2030-12-31** 까지 커버.
- 출력 구조: approval은 `{"_meta":{...}, "records":[...]}`, 정당지지는 `{"polls":[...]}`.
- 차기주자: `aggregated_etc.json` + tracker.js의 다자대결 필터(≥4명, 합 70~106,
  max<55, 양자/적합도 제외)로 프런트에서 산출.

### house effect (기관 lean)

각 기관 측정치 − 커널 평활 추세 의 평균 잔차(538/Economist 방식). 공유 모듈
`assets/poll-stats.js`(`PollStats.kernelSmooth/houseEffects`)에 있고 tracker 페이지에서
lean 표 + 보정 토글로 노출. **데이터 품질 탐지기**도 겸한다(큰 lean = 오독 의심).

## 3. `--incremental` — CI의 핵심 전제

**CI엔 과거 선거 PDF가 없다.** raw-bundle Release엔 9회 지선 + VT012 일부만 있고,
22대총선·21대대선 등 과거 코퍼스는 **로컬에만** 존재. 따라서 CI에서 full 재추출하면
과거 데이터가 **소실**된다.

`--incremental` 플래그가 이를 막는다:

```python
prev, done = [], set()
if args.incremental and OUT.exists():
    prev = json.loads(OUT.read_text()).get("records", [])   # 정당지지는 "polls"
    done = {r["ntt_id"] for r in prev}
# 루프: if nid in done: continue        ← 이미 추출된 건 skip
records = prev + records                  # 신규만 병합
records.sort(...)
```

→ **커밋된 JSON(전체 history)을 보존하고 새 VT012 폴만 추가.** 6종 모두 지원.
검증: `extract_approval_gallup.py --incremental --dry-run` → "266건 (신규 0)".

## 4. 워크플로 — `.github/workflows/tracker-refresh.yml`

```
일요일 KST 06:47 (또는 workflow_dispatch 수동) →
  scrape_nesdc --gubun VT012           # 신규 폴 목록 + PDF
  refresh_pending_pdfs                  # 늦게 첨부된 결과표 회수(아래 주의)
  extract_approval_{gallup,realmeter,nbs,hrc,general} --incremental
  extract_party_support --incremental
  → (cold run이면) Release 체크포인트 갱신
  → approval_*.json·aggregated_etc.json 변경 시 commit·push
```

- `concurrency: data-pipeline` — daily-refresh와 같은 그룹(raw 동시접근 방지·큐잉).
- `timeout-minutes: 300` — 첫 cold run(Release 복원 + VT012 전체 재스크랩)이 길 수 있음.
- 캐시 `data/raw/pdf` + `nesdc_etc_polls.csv`, key `rawdata-tracker-<run_id>`,
  restore-keys `rawdata-tracker-`·`rawdata-`(daily와 공유).
- cache miss 시 Release `raw-bundle-v1` 복원(9회 base).

> **NESDC 늦은 PDF 첨부**: 폴 목록(메타)은 먼저 등록되고 결과표 PDF는 며칠 뒤
> 붙는 경우가 많다(주간집계 등). 그래서 `scrape` 직후엔 PDF가 없어 추출 0건일 수
> 있고, `refresh_pending_pdfs`(최근 30일 pending 재시도)가 다음 run에서 회수한다.
> → 한 번에 안 잡혀도 **다음 주 run이 자동 보충**. 데이터 손실 아님.

### 왜 daily가 아니라 주간·별도인가

VT012는 주간 cadence면 충분하고, 추출기가 무거워(full ~75분) daily 60분 타임아웃을
넘긴다. 그래서 분리.

## 5. 저장 계층 — 무엇이 쌓이고 무엇이 안 쌓이나

| 계층 | 누적? | 손실 위험 | 역할 |
|---|---|---|---|
| **커밋된 JSON** (`data/polls/approval_*·aggregated_etc`) | ✓ git | 없음 | **진짜 자산** — tracker source of truth |
| **Actions 캐시** (`rawdata-`) | △ 임시 7일 TTL / repo 10GB cap | evict돼도 incremental이 흡수 | raw PDF·CSV 운반 |
| **Release** (`raw-bundle-v1`) | ✗ (워크플로 ⑤가 cold run에만 갱신) | 읽기 위주 | cache miss 복구 base |
| **로컬 raw** (`data/raw/*`) | ✓ 전체 ~6.8GB | 없음(gitignore) | 과거 코퍼스·full 재추출용 |

로컬 ↔ CI 동기화는 오직 **커밋된 JSON**.

### Release 체크포인트 (워크플로 스텝 ⑤)

cold run(cache miss)이면 NESDC 전체를 새로 받은 상태 → 그 코퍼스를 raw-bundle에
재업로드(`--clobber`)해 다음 복구를 가볍게. **가드: pdf < 1000이면 부분 코퍼스로
의심해 갱신 skip**(daily의 9회 복구 base 보호).

## 6. 1년 CI-only 정상상태 (로컬 미개입 가정)

### ✅ 건강
- 커밋 JSON이 매주 증분 누적 → 1년이면 수백~천 건↑. `done` skip이라 **손실·중복 0**.
- 대통령 subject는 이재명 2030까지 하드코딩 → 1년 내 경계 문제 없음.

### ⚠️ 흔들리나 자가복구
- Actions 캐시 7일 TTL은 주간 cadence와 경계선 → 가끔 miss → Release fallback →
  VT012 전체 재스크랩(cold, 길지만 `done` skip이라 **결과 동일**). "느린 run"이지
  "틀린 run" 아님.
- 10GB cap을 daily와 공유 → 1년 후 evict 잦아져 cold run 빈도↑(비용=시간만).

### ❌ CI가 못 하는 것 (진짜 한계)
- **CI는 ADD만, 과거 FIX 불가.** 파서 버그를 고쳐 과거를 다시 뽑으려면 전체 PDF
  코퍼스가 필요한데 그건 로컬에만 있음. 1년간 로컬 미개입이면 과거 데이터 품질은
  **"마지막 로컬 추출 시점"에 동결**.
- 새 인물/신당 등장 시 `scripts/poll_terms.py`(PARTY_NAMES)·`PRESIDENT_TERMS` 갱신은
  **수동**. 안 하면 라벨 누락.

> 한 줄: **데이터 양·신선도는 자동으로 잘 자라고 잃지 않는다. 다만 복구 run이 점점
> 무거워지고(Release 갱신으로 완화), 품질 개선의 소급 적용은 로컬 없이는 불가능.**

## 7. 유지보수 권장

- **분기 1회 로컬 full 재추출** → 누적된 파서 개선을 과거에 소급, 품질 재동기화:
  ```bash
  python scripts/fetch/scrape_nesdc.py --gubun VT012 --csv data/raw/nesdc_etc_polls.csv
  for s in gallup realmeter nbs hrc general; do python scripts/parse/extract_approval_$s.py; done   # incremental 없이 전수
  python scripts/parse/extract_party_support.py
  ```
- **새 대통령 취임 시** `PRESIDENT_TERMS`에 임기 추가(현재 ~2030 커버).
- **신당 출현 시** `poll_terms.py` PARTY_NAMES 갱신.
- 첫 배포 후 Actions 탭 → tracker-refresh → **Run workflow**로 수동 1회 검증 권장.

## 관련 문서·메모리

- `docs/cycle-workflow.md` — 선거 사이클 빌드(별개 daily 파이프라인).
- `docs/raw-data.md` — `data/raw/` 카탈로그·재다운로드.
- 메모리: `polls_pipeline`, `nesdc_gubun_codes`, `parsed_cache_caveat`(재파싱은
  `parse_pdf.py` hybrid로, `parse_pdf_v2` 단독 금지).
