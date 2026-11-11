#!/usr/bin/env bash
# 로컬 색인(documents·chunks)을 서버 DB로 복사한다. 사용: infra/restore-index.sh <서버 IP>
# users·usage_daily는 옮기지 않는다 — 로컬 시험 계정이 공개 서버에서 살아나면 안 된다.
set -euo pipefail

HOST="ubuntu@${1:?서버 IP 필요}"
SSH=(ssh -i "${SSH_KEY:-$HOME/.ssh/ksg-key.pem}" -o StrictHostKeyChecking=accept-new "$HOST")
REMOTE_PSQL='cd ~/dept-rag && docker compose -f docker/docker-compose.prod.yml --env-file .env exec -T db psql -U dept_rag -d dept_rag -v ON_ERROR_STOP=1'

# 이미 있으면 멈춘다 — 다시 넣으면 기본키 충돌로 실패하거나 서버에서 고친 색인을 덮어쓴다
existing=$("${SSH[@]}" "$REMOTE_PSQL -Atc 'select count(*) from documents'")
if [ "$existing" != "0" ]; then
  echo "서버 색인이 비어 있지 않습니다(documents=$existing). 복원하지 않습니다." >&2
  exit 1
fi

# 강의 원문이 담기므로 디스크에 파일로 남기지 않고 SSH 파이프로만 보낸다
docker exec "${LOCAL_DB_CONTAINER:-docker-db-1}" pg_dump -U dept_rag -d dept_rag --data-only --no-owner \
  -t documents -t chunks | "${SSH[@]}" "$REMOTE_PSQL -q" > /dev/null

"${SSH[@]}" "$REMOTE_PSQL -Atc 'select count(*) from documents' -c 'select count(*) from chunks'"
