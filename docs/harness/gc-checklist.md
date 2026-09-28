# GC 체크리스트 (월 1회)

주기와 담당은 [`profile.md`](profile.md). 결과는 PR 하나로 묶어 올린다.

- [ ] 죽은 코드·미사용 import: `ruff check backend --select F401,F841`
- [ ] 미사용 의존성: `requirements*.txt`, `frontend/package.json`에서 import되지 않는 패키지
- [ ] SoT와 어긋난 문서: `docs/sot.md` 각 행의 경로가 실제로 존재하는가, README가 값을 복사하고 있지 않은가
- [ ] `docs/sot.md`의 "미정/예정" 행 중 이제 확정된 것 갱신
- [ ] `docs/exec-plans/active/`에 남은 완료 작업 → `done/`으로 이동
- [ ] 명명 표류: 같은 개념을 다른 이름으로 부르는 곳(예: scope/visibility, 색인/인덱스)
- [ ] `docs/harness/risk-paths.txt`가 현재 디렉터리 구조와 맞는가
- [ ] TIL: 이번 달 팀원별 편수 확인 (주 1편 이상)
