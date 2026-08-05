# scripts/audit/

점검·검증. CI에서도 호출 (`audit_quality.py`가 핵심).

| 스크립트 | 역할 |
|---|---|
| `audit_quality.py` | poll·result quality report → `data/audits/{date}.json` |
| `audit_parse.py` | parse 결과 vs 원본 비교 |
| `eval_sigungu_hex.py` | 시군구 hex 레이아웃 평가 |
| `iter_compare.py` | 두 build 결과 diff |

CI/cron: `audit_quality.py`.

## full_gate.sh — 커밋 전 필수

```bash
bash scripts/audit/full_gate.sh
```

python 테스트 전부 + `regen_check` + UI 감사를 한 번에 돌린다.
**부분 테스트 성공을 커밋 허가로 간주하지 않는다.** 이 세션에서 두 번,
관련 테스트만 돌리고 커밋했다가 sitemap 검사가 깨진 채로 올라갔다.
사람 주의로 막을 종류가 아니라 gate로 만들었다.
