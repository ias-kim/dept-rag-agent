#!/usr/bin/env bash
# 현재 커밋을 서버에 올려 빌드·기동한다. 사용: infra/deploy.sh <서버 IP> <도메인>
# 서버 .env는 없을 때만 만든다 — 덮어쓰면 JWT_SECRET이 바뀌어 전원 로그아웃되고, DB_PASSWORD가 바뀌어 DB 접속이 끊긴다.
set -euo pipefail

HOST="ubuntu@${1:?서버 IP 필요}"
DOMAIN="${2:?도메인 필요}"
SSH=(ssh -i "${SSH_KEY:-$HOME/.ssh/ksg-key.pem}" -o StrictHostKeyChecking=accept-new "$HOST")

# 작업 트리가 아니라 커밋을 올린다 — 무엇이 배포됐는지 커밋 해시로 말할 수 있어야 한다
git archive HEAD | "${SSH[@]}" 'tar -x -C ~/dept-rag'
git rev-parse --short HEAD | "${SSH[@]}" 'cat > ~/dept-rag/REVISION'

"${SSH[@]}" DOMAIN="$DOMAIN" bash -s <<'REMOTE'
set -euo pipefail
cd ~/dept-rag
if [ ! -f .env ]; then
  umask 077
  cat > .env <<EOF
DOMAIN=$DOMAIN
DB_PASSWORD=$(openssl rand -hex 24)
JWT_SECRET=$(openssl rand -hex 32)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
EOF
fi
docker compose -f docker/docker-compose.prod.yml --env-file .env up -d --build --wait
REMOTE
