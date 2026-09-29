# docs/generated — DO NOT EDIT

이 폴더의 파일은 전부 생성물입니다. 손으로 고치지 말고 `make generate`로 다시 만드세요.

| 파일 | 소스(SoT) | 생성기 |
|---|---|---|
| `openapi.json` | `backend/app/` FastAPI 라우트 | `backend/scripts/gen_openapi.py` |
| `eval-comparison.md` | `eval/runs/`, `eval/grading/` (로컬 전용) | `backend/evaluation/report.py` (`make eval-report`) |

일치 여부는 `backend/tests/test_openapi_snapshot.py`가 `make check`/CI에서 검사합니다.
