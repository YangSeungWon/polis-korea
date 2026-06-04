# scripts/audit/

점검·검증. CI에서도 호출 (`audit_quality.py`가 핵심).

| 스크립트 | 역할 |
|---|---|
| `audit_quality.py` | poll·result quality report → `data/audits/{date}.json` |
| `audit_parse.py` | parse 결과 vs 원본 비교 |
| `eval_sigungu_hex.py` | 시군구 hex 레이아웃 평가 |
| `iter_compare.py` | 두 build 결과 diff |

CI/cron: `audit_quality.py`.
