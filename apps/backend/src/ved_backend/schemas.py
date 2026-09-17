from typing import Literal

from pydantic import BaseModel

ServiceState = Literal["ok", "degraded", "down"]


class HealthStatus(BaseModel):
    status: ServiceState
    version: str
    database: ServiceState
