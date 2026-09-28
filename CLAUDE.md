@AGENTS.md

## Claude Code 전용

- 여러 파일을 훑는 조사는 `explorer` 서브에이전트에 맡기고 요약만 받는다.
- PR 전에는 `reviewer` 서브에이전트로 게이트 2를 돌린다. 작성한 세션이 스스로 통과 판정을 내리지 않는다.
- `.env`는 `.claude/settings.json`에서 Read 도구만 차단돼 있다. Bash(`cat` 등)로도 열지 않는다.
