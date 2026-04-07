from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_calendar import router as calendar_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in settings.cors_origins.split(",") if item.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def healthcheck():
    return {"status": "ok", "environment": settings.app_env}


app.include_router(auth_router)
app.include_router(calendar_router)
