from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class HealthResponse(APIModel):
    status: str
    service: str
    version: str
