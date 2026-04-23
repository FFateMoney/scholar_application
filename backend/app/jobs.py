from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from . import autoscholar_path  # noqa: F401
from .codex_runner import CodexRunArtifacts, prepare_codex_artifacts, run_codex_prompt
from .config import SETTINGS
from .models import (
    ArtifactInfo,
    IdeaReportRequest,
    JobCreateResponse,
    JobDetailResponse,
    JobRecord,
    JobStatus,
    JobType,
    utc_timestamp,
)
from .prompts import (
    build_final_idea_report_prompt,
    build_idea_generation_prompt,
    build_reference_lookup_prompt,
    build_reviewed_idea_report_prompt,
)
from .search_supervisor import load_search_retry_config, retry_search_until_clear

from autoscholar.analysis import assess_idea
from autoscholar.citation import build_shortlist, run_correction, run_prescreen, run_search, write_bibtex
from autoscholar.citation.config import CitationRulesConfig, IdeaEvaluationConfig, RecommendationConfig, SearchConfig
from autoscholar.io import read_jsonl, read_yaml, write_text, write_yaml
from autoscholar.models import ClaimRecord, QueryRecord
from autoscholar.reporting import build_evidence_map, render_report
from autoscholar.utils import pdf_to_text
from autoscholar.workspace import Workspace


def _safe_filename_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    return suffix if suffix else ".txt"


def _job_file_path(workspace_dir: Path) -> Path:
    return SETTINGS.state_root / f"{workspace_dir.name}.json"


def _relative_to_workspace(workspace_dir: Path, artifact_path: Path) -> str:
    try:
        return artifact_path.resolve().relative_to(workspace_dir.resolve()).as_posix()
    except ValueError:
        return artifact_path.name


def _load_search_config(workspace: Workspace) -> SearchConfig:
    return SearchConfig.model_validate(read_yaml(workspace.require_path("configs", "search")))


def _load_recommendation_config(workspace: Workspace) -> RecommendationConfig:
    return RecommendationConfig.model_validate(read_yaml(workspace.require_path("configs", "recommendation")))


def _load_rules(workspace: Workspace) -> CitationRulesConfig:
    return CitationRulesConfig.model_validate(read_yaml(workspace.require_path("configs", "citation_rules")))


def _load_idea_config(workspace: Workspace) -> IdeaEvaluationConfig:
    return IdeaEvaluationConfig.model_validate(read_yaml(workspace.require_path("configs", "idea_evaluation")))


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}

    def _generate_job_id(self) -> str:
        base = datetime.now().strftime("%Y%m%d%H%M%S")
        candidate = base
        suffix = 1

        while (
            candidate in self._jobs
            or (SETTINGS.jobs_root / candidate).exists()
            or (SETTINGS.state_root / f"{candidate}.json").exists()
        ):
            candidate = f"{base}_{suffix:02d}"
            suffix += 1

        return candidate

    def create_job(self, job_type: JobType) -> JobRecord:
        with self._lock:
            job_id = self._generate_job_id()
            workspace_dir = SETTINGS.jobs_root / job_id
            record = JobRecord(
                job_id=job_id,
                job_type=job_type,
                workspace_dir=str(workspace_dir),
            )
            self._jobs[job_id] = record
        self._persist_job(record)
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def create_response(self, record: JobRecord) -> JobCreateResponse:
        return JobCreateResponse(
            job_id=record.job_id,
            job_type=record.job_type,
            status=record.status,
            stage=record.stage,
            detail_url=f"/jobs/{record.job_id}",
            result_url=f"/jobs/{record.job_id}/result",
        )

    def serialize_job(self, job_id: str) -> JobDetailResponse | None:
        record = self.get_job(job_id)
        if record is None:
            return None
        workspace_dir = Path(record.workspace_dir)
        artifacts: list[ArtifactInfo] = []
        for key, raw_path in sorted(record.artifacts.items()):
            artifact_path = Path(raw_path)
            if artifact_path.exists():
                artifacts.append(
                    ArtifactInfo(
                        key=key,
                        relative_path=_relative_to_workspace(workspace_dir, artifact_path),
                        download_url=f"/jobs/{record.job_id}/files/{key}",
                    )
                )
        return JobDetailResponse(
            job_id=record.job_id,
            job_type=record.job_type,
            status=record.status,
            stage=record.stage,
            message=record.message,
            created_at=record.created_at,
            updated_at=record.updated_at,
            error=record.error,
            primary_artifact_key=self._primary_artifact_key(record.job_type),
            artifacts=artifacts,
        )

    def resolve_artifact(self, job_id: str, artifact_key: str) -> Path | None:
        record = self.get_job(job_id)
        if record is None:
            return None
        raw_path = record.artifacts.get(artifact_key)
        if not raw_path:
            return None
        path = Path(raw_path)
        if not path.exists():
            return None
        return path

    def start_idea_report(self, job_id: str, request: IdeaReportRequest) -> None:
        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, self._run_idea_report_job, request),
            daemon=True,
        )
        thread.start()

    def start_reference_bib(self, job_id: str, filename: str, content: bytes, language: str) -> None:
        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, self._run_reference_bib_job, filename, content, language),
            daemon=True,
        )
        thread.start()

    def _run_job(self, job_id: str, task, *args) -> None:
        try:
            self._update_job(job_id, status=JobStatus.RUNNING, stage="starting", message="Job accepted.")
            task(job_id, *args)
        except Exception as exc:
            self._update_job(
                job_id,
                status=JobStatus.FAILED,
                stage="failed",
                message="Job failed.",
                error=str(exc),
            )

    def _run_idea_report_job(self, job_id: str, request: IdeaReportRequest) -> None:
        workspace = self._init_workspace(job_id, template="idea-evaluation", reports_lang=request.language)
        self._register_default_artifacts(job_id, workspace)

        self._update_job(
            job_id,
            stage="codex_generate_inputs",
            message="Generating idea brief, claims, and queries with Codex.",
        )
        codex_artifacts = prepare_codex_artifacts(workspace.root, "idea_generation")
        self._register_codex_artifacts(job_id, codex_artifacts)
        codex_artifacts = run_codex_prompt(
            build_idea_generation_prompt(workspace.root, request),
            workspace.root,
            "idea_generation",
            artifacts=codex_artifacts,
        )
        self._validate_generated_claims_and_queries(job_id, workspace)
        self._register_artifact(job_id, "idea_source", workspace.require_path("inputs", "idea_source"))

        search_config = _load_search_config(workspace)
        retry_config = load_search_retry_config()
        retry_search_until_clear(
            workspace=workspace,
            search_config=search_config,
            retry_config=retry_config,
            progress_callback=lambda stage, message: self._update_job(job_id, stage=stage, message=message),
        )
        self._register_artifact(job_id, "search_results_raw", workspace.require_path("artifacts", "search_results_raw"))
        self._register_artifact(job_id, "search_failures", workspace.require_path("artifacts", "search_failures"))

        self._update_job(job_id, stage="citation_prescreen", message="Prescreening search results.")
        run_prescreen(workspace, _load_rules(workspace))
        self._register_artifact(job_id, "query_reviews", workspace.require_path("artifacts", "query_reviews"))
        self._register_artifact(job_id, "search_results_deduped", workspace.require_path("artifacts", "search_results_deduped"))

        self._update_job(job_id, stage="citation_correct", message="Running recommendation correction.")
        run_correction(workspace, _load_rules(workspace), _load_recommendation_config(workspace))
        self._register_artifact(
            job_id,
            "recommendation_corrections",
            workspace.require_path("artifacts", "recommendation_corrections"),
        )

        self._update_job(job_id, stage="citation_shortlist", message="Building shortlisted evidence.")
        build_shortlist(workspace, _load_rules(workspace))
        self._register_artifact(job_id, "selected_citations", workspace.require_path("artifacts", "selected_citations"))

        self._update_job(job_id, stage="idea_assess", message="Assessing idea quality.")
        idea_config = _load_idea_config(workspace)
        assess_idea(workspace, idea_config)
        build_evidence_map(workspace, idea_config)
        self._register_artifact(job_id, "idea_assessment", workspace.require_path("artifacts", "idea_assessment"))
        self._register_artifact(job_id, "evidence_map", workspace.require_path("artifacts", "evidence_map"))

        self._update_job(job_id, stage="report_render", message="Rendering internal feasibility report.")
        feasibility_path = render_report(workspace, "feasibility")
        self._register_artifact(job_id, "feasibility_report", feasibility_path)

        self._update_job(job_id, stage="codex_generate_final_report", message="Writing final user report with Codex.")
        final_report_artifacts = prepare_codex_artifacts(workspace.root, "idea_final_report")
        self._register_codex_artifacts(job_id, final_report_artifacts, key_prefix="final_report")
        run_codex_prompt(
            build_final_idea_report_prompt(workspace.root, request.language),
            workspace.root,
            "idea_final_report",
            artifacts=final_report_artifacts,
        )
        final_report_path = workspace.root / "reports" / "final_idea_report.md"
        if not final_report_path.exists() or not final_report_path.read_text(encoding="utf-8").strip():
            raise RuntimeError("Final idea report was not written by Codex.")
        self._register_artifact(job_id, "final_idea_report", final_report_path)

        self._update_job(
            job_id,
            stage="codex_review_final_report",
            message="Reviewing and revising the report with an independent Codex pass.",
        )
        reviewed_report_artifacts = prepare_codex_artifacts(workspace.root, "idea_final_report_review")
        self._register_codex_artifacts(job_id, reviewed_report_artifacts, key_prefix="review")
        run_codex_prompt(
            build_reviewed_idea_report_prompt(workspace.root, request.language),
            workspace.root,
            "idea_final_report_review",
            artifacts=reviewed_report_artifacts,
        )
        reviewed_report_path = workspace.root / "reports" / "final_idea_report_reviewed.md"
        if not reviewed_report_path.exists() or not reviewed_report_path.read_text(encoding="utf-8").strip():
            raise RuntimeError("Reviewed final idea report was not written by Codex.")
        self._register_artifact(job_id, "reviewed_final_idea_report", reviewed_report_path)

        self._update_job(
            job_id,
            status=JobStatus.SUCCEEDED,
            stage="completed",
            message="Idea report completed.",
            error=None,
        )

    def _run_reference_bib_job(self, job_id: str, filename: str, content: bytes, language: str) -> None:
        workspace = self._init_workspace(job_id, template="citation-paper", reports_lang=language if language in {"zh", "en"} else "zh")
        self._register_default_artifacts(job_id, workspace)
        self._tune_reference_lookup_config(workspace)

        self._update_job(job_id, stage="save_input", message="Saving uploaded source file.")
        suffix = _safe_filename_suffix(filename)
        source_path = workspace.root / "inputs" / f"uploaded_source{suffix}"
        source_path.write_bytes(content)
        self._register_artifact(job_id, "uploaded_source", source_path)

        manuscript_path = workspace.require_path("inputs", "manuscript")
        if suffix == ".pdf":
            self._update_job(job_id, stage="pdf_extract", message="Extracting text from PDF.")
            extracted_path = pdf_to_text(source_path, workspace.root / "inputs" / "uploaded_source.txt")
            extracted_text = extracted_path.read_text(encoding="utf-8")
            write_text(manuscript_path, "# Extracted Source Text\n\n" + extracted_text)
            self._register_artifact(job_id, "uploaded_source_text", extracted_path)
        else:
            decoded = content.decode("utf-8", errors="replace")
            write_text(manuscript_path, decoded)

        self._register_artifact(job_id, "manuscript", manuscript_path)

        self._update_job(
            job_id,
            stage="codex_generate_queries",
            message="Generating reference lookup claims and queries with Codex.",
        )
        codex_artifacts = prepare_codex_artifacts(workspace.root, "reference_lookup")
        self._register_codex_artifacts(job_id, codex_artifacts)
        codex_artifacts = run_codex_prompt(
            build_reference_lookup_prompt(workspace.root, source_path, manuscript_path, language),
            workspace.root,
            "reference_lookup",
            artifacts=codex_artifacts,
        )
        self._validate_generated_claims_and_queries(job_id, workspace)

        search_config = _load_search_config(workspace)
        retry_config = load_search_retry_config()
        retry_search_until_clear(
            workspace=workspace,
            search_config=search_config,
            retry_config=retry_config,
            progress_callback=lambda stage, message: self._update_job(job_id, stage=stage, message=message),
        )
        self._register_artifact(job_id, "search_results_raw", workspace.require_path("artifacts", "search_results_raw"))
        self._register_artifact(job_id, "search_failures", workspace.require_path("artifacts", "search_failures"))

        self._update_job(job_id, stage="citation_prescreen", message="Prescreening candidate references.")
        run_prescreen(workspace, _load_rules(workspace))
        self._register_artifact(job_id, "query_reviews", workspace.require_path("artifacts", "query_reviews"))
        self._register_artifact(job_id, "search_results_deduped", workspace.require_path("artifacts", "search_results_deduped"))

        self._update_job(job_id, stage="citation_shortlist", message="Selecting best reference matches.")
        build_shortlist(workspace, _load_rules(workspace))
        self._register_artifact(job_id, "selected_citations", workspace.require_path("artifacts", "selected_citations"))

        self._update_job(job_id, stage="bib_generate", message="Generating BibTeX output.")
        write_bibtex(workspace)
        self._register_artifact(job_id, "references_bib", workspace.require_path("artifacts", "references_bib"))

        self._update_job(
            job_id,
            status=JobStatus.SUCCEEDED,
            stage="completed",
            message="Reference BibTeX completed.",
            error=None,
        )

    def _init_workspace(self, job_id: str, template: str, reports_lang: str) -> Workspace:
        workspace_dir = SETTINGS.jobs_root / job_id
        self._update_job(job_id, stage="workspace_init", message="Initializing workspace.")
        workspace = Workspace.init(workspace_dir, template=template, reports_lang=reports_lang)
        self._register_artifact(job_id, "workspace_manifest", workspace.root / "workspace.yaml")
        return workspace

    def _validate_generated_claims_and_queries(self, job_id: str, workspace: Workspace) -> None:
        claims = read_jsonl(workspace.require_path("artifacts", "claims"), ClaimRecord)
        queries = read_jsonl(workspace.require_path("artifacts", "queries"), QueryRecord)
        if not claims:
            raise RuntimeError("Codex did not produce any claims.")
        if not queries:
            raise RuntimeError("Codex did not produce any queries.")
        self._register_artifact_by_workspace(job_id, workspace, "claims", "artifacts", "claims")
        self._register_artifact_by_workspace(job_id, workspace, "queries", "artifacts", "queries")

    def _tune_reference_lookup_config(self, workspace: Workspace) -> None:
        rules_path = workspace.require_path("configs", "citation_rules")
        rules = read_yaml(rules_path)
        rules["selected_papers_limit"] = 1
        write_yaml(rules_path, rules)

        search_path = workspace.require_path("configs", "search")
        search = read_yaml(search_path)
        search["limit"] = 5
        search["mode"] = "single_thread"
        write_yaml(search_path, search)

    def _register_codex_artifacts(
        self,
        job_id: str,
        artifacts: CodexRunArtifacts,
        key_prefix: str = "generation",
    ) -> None:
        self._register_artifact(job_id, "codex_prompt", artifacts.prompt_path)
        self._register_artifact(job_id, "codex_stdout", artifacts.stdout_path)
        self._register_artifact(job_id, "codex_stderr", artifacts.stderr_path)
        self._register_artifact(job_id, "codex_last_message", artifacts.last_message_path)
        self._register_artifact(job_id, f"{key_prefix}_codex_prompt", artifacts.prompt_path)
        self._register_artifact(job_id, f"{key_prefix}_codex_stdout", artifacts.stdout_path)
        self._register_artifact(job_id, f"{key_prefix}_codex_stderr", artifacts.stderr_path)
        self._register_artifact(job_id, f"{key_prefix}_codex_last_message", artifacts.last_message_path)

    def _register_default_artifacts(self, job_id: str, workspace: Workspace) -> None:
        self._register_artifact_by_workspace(job_id, workspace, "claims", "artifacts", "claims")
        self._register_artifact_by_workspace(job_id, workspace, "queries", "artifacts", "queries")

    def _register_artifact_by_workspace(
        self,
        job_id: str,
        workspace: Workspace,
        key: str,
        section: str,
        name: str,
    ) -> None:
        path = workspace.require_path(section, name)
        self._register_artifact(job_id, key, path)

    def _register_artifact(self, job_id: str, key: str, path: Path) -> None:
        record = self.get_job(job_id)
        if record is None:
            return
        updated = record.model_copy(
            update={
                "artifacts": {
                    **record.artifacts,
                    key: str(path.resolve()),
                },
                "updated_at": utc_timestamp(),
            }
        )
        with self._lock:
            self._jobs[job_id] = updated
        self._persist_job(updated)

    def _update_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        stage: str | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> None:
        record = self.get_job(job_id)
        if record is None:
            return
        updated = record.model_copy(
            update={
                "status": status or record.status,
                "stage": stage or record.stage,
                "message": message,
                "error": error,
                "updated_at": utc_timestamp(),
            }
        )
        with self._lock:
            self._jobs[job_id] = updated
        self._persist_job(updated)

    def _persist_job(self, record: JobRecord) -> None:
        state_path = _job_file_path(Path(record.workspace_dir))
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _primary_artifact_key(self, job_type: JobType) -> str | None:
        if job_type == JobType.IDEA_REPORT:
            return "reviewed_final_idea_report"
        if job_type == JobType.REFERENCE_BIB:
            return "references_bib"
        return None


job_manager = JobManager()
