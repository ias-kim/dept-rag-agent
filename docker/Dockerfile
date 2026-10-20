# 화면 + API 단일 이미지 (설계 §7). 빌드 컨텍스트는 저장소 루트:
#   docker build -f docker/Dockerfile .
# 비밀값(.env)은 이미지에 넣지 않는다 — 실행 시 compose env_file로만 주입한다.

# 1단계: 화면 빌드 (vite 8 → Node ^20.19 || >=22.12)
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2단계: API 런타임
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    FRONTEND_DIST_DIR=/app/frontend/dist
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY --from=web /web/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
# 워커 1개: 로그인 시도 제한 상태가 프로세스 메모리에 있어 워커가 늘면 제한도 그 배수로 풀린다.
# --proxy-headers는 FORWARDED_ALLOW_IPS(기본 127.0.0.1)에 든 프록시의 X-Forwarded-For만 믿는다 — M4b에서 Caddy 주소로 설정
CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers"]
