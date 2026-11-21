"""The web app: API under /api, the built frontend everywhere else.

    uvicorn callintel.main:app --reload
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import settings
from .db import engine
from .routers import actions, admin, analytics, assistant, auth, calls, home, people

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = FastAPI(title="Sia Listen", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

for r in (auth.router, home.router, calls.router, analytics.router, people.router, actions.router, assistant.router,
          admin.router, admin.brief_router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/ready")
def ready():
    try:
        with engine().connect() as conn:
            conn.execute(text("select 1"))
        return {"ok": True}
    except Exception as e:                       # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=503)


dist = Path(settings().frontend_dir).resolve()
if (dist / "index.html").is_file():
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        f = (dist / path).resolve()
        if path and str(f).startswith(str(dist)) and f.is_file():
            return FileResponse(f)
        return FileResponse(dist / "index.html")
