from fastapi import FastAPI

from app.api.frontend import add_frontend
from app.api.routes import router
from app.core.config import get_settings

app = FastAPI(title="dept-rag-agent")
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}


# 라우트를 모두 등록한 뒤에 붙인다 — 폴백이 먼저 오면 /health까지 index.html로 답한다.
# 빌드가 없으면(테스트·개발 서버) 붙이지 않아 API만으로도 뜬다
_dist = get_settings().frontend_dist_dir
if _dist.is_dir():
    add_frontend(app, _dist)
