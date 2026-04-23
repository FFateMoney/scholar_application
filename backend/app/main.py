from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.responses import PlainTextResponse

from .config import SETTINGS
from .jobs import job_manager
from .models import HealthResponse, IdeaReportRequest, JobStatus, JobType


app = FastAPI(
    title="AutoScholar Backend",
    version="0.1.0",
    description="Local FastAPI service for AutoScholar idea reports and reference BibTeX lookup.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/jobs/idea-report")
def create_idea_report_job(request: IdeaReportRequest):
    record = job_manager.create_job(job_type=JobType.IDEA_REPORT)
    job_manager.start_idea_report(record.job_id, request)
    return job_manager.create_response(record)


@app.post("/jobs/reference-bib")
async def create_reference_bib_job(
    file: UploadFile = File(...),
    language: str = Form("zh"),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    record = job_manager.create_job(job_type=JobType.REFERENCE_BIB)
    job_manager.start_reference_bib(record.job_id, file.filename or "uploaded_file", content, language)
    return job_manager.create_response(record)


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    payload = job_manager.serialize_job(job_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return payload


@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: str):
    payload = job_manager.serialize_job(job_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if payload.status != JobStatus.SUCCEEDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not completed yet. Current status: {payload.status}",
        )
    return payload


@app.get("/jobs/{job_id}/files/{artifact_key}")
def download_artifact(job_id: str, artifact_key: str):
    artifact_path = job_manager.resolve_artifact(job_id, artifact_key)
    if artifact_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return FileResponse(path=artifact_path, filename=artifact_path.name)


@app.get("/jobs/{job_id}/logs/{artifact_key}")
def read_log_artifact(job_id: str, artifact_key: str, tail: int = 200):
    artifact_path = job_manager.resolve_artifact(job_id, artifact_key)
    if artifact_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    content = artifact_path.read_text(encoding="utf-8", errors="replace")
    if tail > 0:
        lines = content.splitlines()
        content = "\n".join(lines[-tail:])
        if content:
            content += "\n"
    return PlainTextResponse(content)
