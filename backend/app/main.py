import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api.connection import router as connection_router
from backend.app.api.tables import router as tables_router
from backend.app.api.records import router as records_router
from backend.app.api.query import router as query_router
from backend.app.api.views import router as views_router
from backend.app.core.security import LocalRequestGuard

app = FastAPI(
    title="vg-data-visor",
    description="Local SQLite, PostgreSQL and MongoDB viewer and editor",
    version="0.1.0",
)

# The UI is served from this same origin, so no CORS is needed. The guard
# blocks other web pages (CSRF) and DNS-rebinding hosts from using the API.
app.add_middleware(LocalRequestGuard)

# Include API routers
app.include_router(connection_router)
app.include_router(tables_router)
app.include_router(records_router)
app.include_router(query_router)
app.include_router(views_router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "vg-data-visor", "version": "0.1.0"}


# Mount static files if the frontend folder exists
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
