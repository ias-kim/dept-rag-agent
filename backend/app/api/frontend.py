"""빌드된 화면(frontend/dist)을 API와 같은 출처에서 내보낸다 — 설계 §7.

같은 출처라 CORS가 필요 없다. 반드시 모든 라우터를 등록한 뒤에 붙인다: 폴백 경로 `/{path}`는
먼저 등록된 라우트가 처리하지 못한 요청만 받는다.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

API_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
# index.html이 캐시되면 새로 배포한 뒤에도 옛 assets 해시를 가리켜 빈 화면이 뜬다. assets는 파일명에 해시가 있어 캐시해도 된다
INDEX_HEADERS = {"Cache-Control": "no-cache"}


def add_frontend(app: FastAPI, dist_dir: Path) -> None:
    dist = dist_dir.resolve()
    index = dist / "index.html"
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    # 없는 API는 메서드와 무관하게 JSON 404. 아래 폴백은 GET 전용이라, 이 라우트가 없으면 POST 오타가
    # 경로만 맞아 405 "Method Not Allowed"가 되고 그 영어 문구가 학생 화면에 그대로 뜬다
    # 메서드 목록에 HEAD·OPTIONS까지, 경로에 슬래시 없는 /api까지 넣는다 — 빠지면 그 요청만 405로 샌다(게이트 3 경고)
    @app.api_route("/api", methods=API_METHODS, include_in_schema=False)
    @app.api_route("/api/{rest:path}", methods=API_METHODS, include_in_schema=False)
    def api_not_found(rest: str = ""):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (dist / path).resolve()
        # resolve 후 dist 안인지 확인 — "../"로 dist 밖 파일(.env 등)을 읽어 가는 경로 탈출을 막는다
        if path and candidate.is_relative_to(dist) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index, headers=INDEX_HEADERS)
