# 평가셋 (설계 §6)

## 파일
| 파일 | 내용 | git |
|---|---|---|
| `questions.yaml` | 평가 문항 SoT (제출용 30 + 보조 6) | 커밋 |
| `FROZEN` | 동결 시점 `questions.yaml`의 sha256 | 커밋 |
| `RUBRIC.md` | 사람 채점 기준 | 커밋 |
| `runs/`, `grading/` | 실행 결과·채점표 (강의자료 원문 포함) | **gitignore** (레포 PUBLIC) |

## 문항 형식
```yaml
- id: A01                      # 전공 M##, 학사 A##, both B##, none N##
  question: 2학기 수강신청 정정 기간이 언제야?
  intent: academic             # major | academic | both | none
  gold_sources: [{file: academic/학사일정.pdf, page: 2}]   # data/ 기준 상대 경로, none이면 []
  key_points: [9월 8일~9월 12일]                          # 답에 꼭 들어가야 할 사실, none이면 []
```
- 문항은 **적재한 PDF를 보면서** 쓴다. `file`은 `data/` 아래 상대 경로와 정확히 같아야 한다.
- 강의자료 문장을 길게 베끼지 않는다(레포 PUBLIC). `key_points`는 짧은 사실만.

## 순서
1. 36문항 작성 → `make eval-freeze` (이후 수정하면 `make check` 실패)
2. `make eval LABEL=baseline` → `grading/<실행>.csv`에 `RUBRIC.md` 기준으로 O/X
3. `make eval-report` → `docs/generated/eval-comparison.md` 커밋

## 자주 막히는 곳
- `make eval`이 FileExistsError로 멈추면: 같은 날·같은 커밋 실행 이름이 겹친 것 — `LABEL=baseline-2`처럼 다른 라벨을 쓴다(이전 채점표를 보호).
- 채점 칸에는 `O` 또는 `X`만 쓴다(전각 `Ｏ`도 인식). 다른 값이 있으면 `make eval-report`가 문항 id와 함께 멈춘다.
- 엑셀에서 저장할 때는 **CSV UTF-8** 형식으로 저장한다. 일반 CSV(cp949)는 `make eval-report`가 거부한다.
