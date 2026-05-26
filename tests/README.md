# tests/

의존성 없는 순수 파이썬 테스트 (pytest 불필요).

```bash
.venv/bin/python tests/test_parser_golden.py
```

- **test_parser_golden.py** — `parse_pdf`가 까다로운 PDF 양식의 후보를 계속 맞히는지 회귀 검증.
  골든 케이스: 평택을(조국·황교안)·부산북구갑(한동훈 무소속) 등 정당조각·직책·노이즈가 섞인 양식.
  PDF(`data/raw/pdf/`, gitignore)가 없는 케이스는 SKIP. 실패 시 exit 1.

파서 수정·리팩토링 후 이걸 돌려 회귀 없는지 확인.
