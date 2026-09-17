from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ved_backend.config import settings
from ved_backend.schemas import HealthStatus

app = FastAPI(title="Ved backend", version=settings.version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> HealthStatus:
    return HealthStatus(status="ok", version=settings.version)
