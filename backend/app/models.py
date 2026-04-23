from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class JobType(str, Enum):
    IDEA_REPORT = "idea_report"
    REFERENCE_BIB = "reference_bib"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IdeaReportRequest(BaseModel):
    brief: str | None = Field(default=None, min_length=3)
    domain: str | None = Field(default=None, min_length=3)
    direction: str | None = Field(default=None, min_length=3)
    innovation_requirements: str | None = Field(default=None, min_length=3)
    constraints: str | None = None
    language: Literal["zh", "en"] = "zh"

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_strings(cls, data):
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        for key in ("brief", "domain", "direction", "innovation_requirements", "constraints"):
            value = normalized.get(key)
            if isinstance(value, str):
                stripped = value.strip()
                normalized[key] = stripped or None

        return normalized

    @model_validator(mode="after")
    def validate_request_shape(self) -> "IdeaReportRequest":
        if self.brief and self.brief.strip():
            return self

        if self.domain and self.direction and self.innovation_requirements:
            return self

        raise ValueError("Provide either a brief research description or the legacy structured fields.")


class ArtifactInfo(BaseModel):
    key: str
    relative_path: str
    download_url: str


class JobRecord(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus = JobStatus.QUEUED
    stage: str = "queued"
    message: str | None = None
    created_at: str = Field(default_factory=utc_timestamp)
    updated_at: str = Field(default_factory=utc_timestamp)
    workspace_dir: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class JobCreateResponse(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    stage: str
    detail_url: str
    result_url: str


class JobDetailResponse(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    stage: str
    message: str | None = None
    created_at: str
    updated_at: str
    error: str | None = None
    primary_artifact_key: str | None = None
    artifacts: list[ArtifactInfo] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
