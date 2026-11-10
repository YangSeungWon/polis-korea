# 무인 운영: 수집에서 실제 서비스까지

2026-11-10 점검에서 수집 작업은 매일 성공했지만 서비스는 9월 3일 버전이었다.
기본 GITHUB_TOKEN으로 push한 커밋은 다른 push 워크플로를 실행하지 않는다.
그동안 쌓인 137개 커밋은 배포와 구조 검사를 거치지 않았다.

## 실행 경로

`pages.yml`은 사람의 master push, 수동 실행, 데이터 쓰기 워크플로 여섯 개의
완료 이벤트를 받는다. 원본 작업의 head_sha는 수집 전 커밋이므로 쓰지 않는다.
실행 시 master를 읽어 SHA를 고정하고 다음 순서로 진행한다.

1. 실제 서비스의 polis-build 표식과 비교한다. 이미 같은 SHA면 생략한다.
2. 고정한 SHA를 checks.yml에 전달해 구조·생성물·브라우저 검사를 실행한다.
3. 모두 통과한 동일 SHA를 빌드·배포한다. 실패하면 이전 서비스는 유지한다.
4. 실제 서비스의 SHA가 일치할 때까지 최대 12회 확인한다.

수집이 일부 커밋 후 실패할 수도 있으므로 완료 결과가 실패여도 검증 경로는 실행한다.
배포 전체를 하나의 concurrency group으로 직렬화해 오래된 배포가 새 배포를 덮지 않게 한다.
빌드 표식은 이벤트의 GITHUB_SHA가 아닌 실제 checkout HEAD를 사용한다.
배포 산출물 이름에는 run_id와 run_attempt를 넣어 실패 작업을 재시도해도 이름이 충돌하지 않게 한다.
검토용 스크린샷은 PR에서만 저장하고, 배포에서는 동일한 브라우저 검증만 실행한다.

## 독립 감시

`operations.yml`은 매일, push 없이도 실행된다. `check_operations.py`는 다음을
실패로 표시하고 Actions 요약에 이유를 남긴다. Actions 실패 알림 수신 여부는 계정 설정을 따른다.

- 사이트 접속 실패 또는 빌드 표식 누락
- 아직 서비스되지 않은 첫 커밋이 24시간보다 오래됨 (새 커밋이 계속 쌓여도 지연을 숨기지 않음)
- 정기 데이터가 overdue, fetch_failed, manual_refresh 상태
- 실제 서비스의 조사일이 저장소보다 오래됨

과거 확정 선거 결과는 갱신 대상이 아니다. 기관별 주기와 확인된 휴간은 health.py를 따른다.
지연은 원출처 발표 여부를 확인하라는 신호이며 수집기 결함의 확정 판정은 아니다.

## 자체발표 소스

갤럽은 `fetch_gallup_self.py --recent`로 공식 목록에서 최신 보고서 번호를 찾는다.
raw 캐시가 없어도 커밋된 과거 기록에 병합하므로 CI cold start가 과거 시계열을 삭제하지 않는다.
수집 장애는 해당 단계 경고와 독립 신선도 감시로 표시하며 다른 소스 갱신은 계속한다.

리얼미터는 GitHub 러너에서 0건이 반환되는 접근 제한이 아직 남아 있다.
로컬 공식 사이트 접근이 가능할 때 아래 순서로 회수한다. --limit은 필요한 기간에 맞춘다.

```sh
python scripts/fetch/fetch_realmeter_self.py --max-pages 3
python scripts/parse/extract_approval_realmeter.py --source self
python scripts/build/build_tracker_static.py
python scripts/build/build_home_capabilities.py
python scripts/build/build_sitemap.py
```

자동화만으로 해결되지 않은 소스를 정상으로 감추지 않는다. 마지막 조사일이 예정일을
넘기면 운영 감시는 실패한다. 장기 해결은 해당 공식 소스에 접근 가능한 실행 환경이 필요하다.

## Pages 공개 지연

2026-11-10 실행 42780242980은 검사·업로드 성공 후 공개 단계에서 두 번 시간 초과됐다.
첫 시도는 `syncing_files`, 재시도는 `finished_file_sync` 상태에서 기본 10분 제한에 걸렸다.
`actions/deploy-pages@v5`는 내부 `MAX_TIMEOUT=600000`으로 대기 시간을 최대 10분으로 제한한다.
1200000을 입력해도 600000으로 줄어든다. 실행 42792040978에서 이 제한을 확인했고,
효과 없는 20분 입력을 제거했다. 작업 전체의 30분 제한은 빌드·업로드·공개 확인까지의
상한이며 액션 내부 대기 시간을 연장하지 않는다.

배포 전 검사와 실제 서비스 SHA 확인은 유지한다. 공개 지연이 반복되면 성공본과 실패본의
실제 산출물을 비교하고, 운영에서 참조하는 파일을 보존하면서 불필요한 파일을 분리한다.
크기가 크다는 이유만으로 원인을 단정하거나 `data/raw` 전체를 제외하지 않는다.
검사 성공만으로 운영 반영 완료라고 판단하지 않는다.

공식 구현: https://github.com/actions/deploy-pages/blob/v5/src/internal/deployment.js
