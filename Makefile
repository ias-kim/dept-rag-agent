# 하네스 명령 모음 — 설명은 AGENTS.md, 게이트 정의는 docs/harness/profile.md
# Python 3.12 고정 (psycopg-binary 3.2.3에 3.14 wheel 없음)

VENV ?= backend/.venv
PY   ?= $(VENV)/bin/python

.PHONY: setup lint lint-py lint-fe test generate check smoke

setup:
	@if [ -x $(PY) ] && ! $(PY) -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))'; then \
		echo "기존 $(VENV) 가 Python 3.12가 아닙니다. 지우고 다시 실행: rm -rf $(VENV) && make setup"; exit 1; fi
	@[ -x $(PY) ] || uv venv --python 3.12 $(VENV)
	uv pip install --python $(PY) -r backend/requirements.txt -r backend/requirements-dev.txt
	cd frontend && npm ci

lint: lint-py lint-fe

lint-py:
	$(PY) -m ruff check backend

lint-fe:
	cd frontend && npm run --silent lint

test:
	$(PY) -m pytest -q backend

generate:
	$(PY) backend/scripts/gen_openapi.py

# 게이트 1 전체. 로컬과 CI가 같은 명령을 쓴다.
check: lint test

# 서버를 띄운 상태에서 "고쳤다"를 직접 확인하는 스모크 테스트
smoke:
	curl -fsS http://localhost:8000/health && echo
