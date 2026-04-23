# AutoScholar Service Design

## 1. Goal

This document defines the first external-service version of AutoScholar.

The target is to expose only two user-facing capabilities:

1. `idea generation`
   The user provides domain, research direction, and innovation requirements.
   The system returns a research idea report in `Markdown`, with `PDF` as an optional later-stage export.

2. `reference lookup`
   The user uploads a paper source file in `TeX` or `PDF`.
   The system returns a generated `references.bib`.

The service will run locally and use the local `codex` CLI as the agent layer.

## 2. Current Project Fit

AutoScholar is already well aligned with this plan:

- It is a local, workspace-based system.
- Core logic is implemented as Python functions, not only CLI wrappers.
- Outputs are already structured into `artifacts/` and rendered reports.
- Citation and report workflows already exist.

This means the service layer should:

- keep AutoScholar as the workflow engine
- add FastAPI as the HTTP interface
- use local Codex for generation and extraction tasks that AutoScholar does not already automate

## 3. Scope For V1

### Included

- FastAPI backend
- local workspace/job creation per request
- local Codex invocation through command line
- Markdown output for idea report
- BibTeX output for reference lookup
- basic job status polling

### Deferred

- multi-user auth
- distributed queue
- database persistence
- advanced frontend editing
- guaranteed PDF export in first implementation
- open-ended chat interface

## 4. Product Definition

### 4.1 Idea Generation

Input:

- research domain
- research direction
- innovation requirements
- optional constraints
- optional language preference

Output:

- a generated idea report in `Markdown`
- optional structured artifacts used to support the report

Recommended product framing:

This should not be implemented as pure brainstorming only.
It should be implemented as a `research idea report generation` workflow:

1. Codex drafts the idea brief
2. Codex extracts claims and search queries
3. AutoScholar runs citation workflow
4. AutoScholar performs idea assessment
5. AutoScholar renders a report

This gives the output literature support instead of only free-form LLM text.

### 4.2 Reference Lookup

Input:

- a `TeX` file or a `PDF` file

Output:

- `references.bib`

Recommended workflow:

1. save uploaded file into workspace
2. if input is PDF, extract plain text first
3. use Codex to identify claims and search intents from the paper
4. generate `claims.jsonl` and `queries.jsonl`
5. run AutoScholar citation workflow
6. export `references.bib`

This is a better fit for V1 than full idea generation because AutoScholar already has most of the downstream citation pipeline.

## 5. Architecture

### 5.1 Main Components

1. `FastAPI service`
   Receives requests, creates jobs, returns status and artifacts.

2. `Workspace manager`
   Creates one isolated AutoScholar workspace per job.

3. `Codex runner`
   Invokes local `codex` CLI with tightly scoped prompts.

4. `AutoScholar workflow runner`
   Calls Python functions from AutoScholar modules directly.

5. `Artifact delivery layer`
   Returns generated `Markdown`, `BibTeX`, and optional report metadata.

### 5.2 Design Principle

Do not call `autoscholar` CLI from FastAPI unless necessary.

Preferred order:

1. FastAPI request
2. create workspace
3. call local Codex for generation or extraction
4. call AutoScholar Python functions
5. return artifact paths and downloadable content

This is more stable than chaining shell commands together end-to-end.

## 6. Workspace Strategy

Each request should map to one isolated workspace directory.

Suggested layout:

```text
runtime/
  jobs/
    <job_id>/
      workspace.yaml
      inputs/
      configs/
      artifacts/
      reports/
```

Rules:

- never reuse a workspace across unrelated requests
- never let concurrent jobs write to the same workspace
- treat workspace directory as the unit of job state

## 7. Codex Integration Strategy

## 7.1 Why Codex Is Needed

AutoScholar already handles:

- search
- prescreen
- correction
- shortlist
- bib generation
- idea assessment
- report rendering

AutoScholar does not yet fully automate:

- generating a research idea from a user brief
- extracting structured claims and queries from arbitrary `TeX` or `PDF`

That is where local Codex should be used.

## 7.2 Recommended Role Of Codex

Codex should be treated as a bounded file-producing agent, not as an unrestricted chat backend.

For example, Codex should be prompted to write only:

- `inputs/idea_source.md`
- `artifacts/claims.jsonl`
- `artifacts/queries.jsonl`

This is important because shell-based agent invocation is much more reliable when the expected output contract is narrow.

## 7.3 Output Contract

Avoid depending on free-form stdout parsing.

Preferred contract:

1. backend prepares workspace
2. backend invokes Codex with explicit instructions
3. Codex writes files into the workspace
4. backend validates files using existing Pydantic models

If validation fails, the job should stop and return an actionable error.

## 7.4 Prompting Constraints

Prompts should instruct Codex to:

- operate only inside the provided workspace
- write exact target files
- produce valid JSONL structures matching AutoScholar models
- avoid extra files unless requested
- preserve UTF-8 text

## 8. Backend API Shape

V1 should keep the API intentionally small.

### 8.1 Idea Report

`POST /jobs/idea-report`

Request body:

```json
{
  "domain": "medical image analysis",
  "direction": "failure-aware segmentation",
  "innovation_requirements": "novel but practical, suitable for a conference paper",
  "constraints": "prefer methods compatible with open datasets",
  "language": "zh"
}
```

Response:

```json
{
  "job_id": "job_123",
  "status": "queued"
}
```

### 8.2 Reference Bib

`POST /jobs/reference-bib`

Multipart form:

- `file`
- optional `language`

Response:

```json
{
  "job_id": "job_456",
  "status": "queued"
}
```

### 8.3 Job Status

`GET /jobs/{job_id}`

Response:

```json
{
  "job_id": "job_123",
  "status": "running",
  "stage": "citation_search",
  "artifacts": {}
}
```

### 8.4 Job Result

`GET /jobs/{job_id}/result`

Possible response for idea report:

```json
{
  "job_id": "job_123",
  "status": "succeeded",
  "report_markdown_path": "reports/feasibility.md",
  "download_urls": {
    "markdown": "/jobs/job_123/files/report.md"
  }
}
```

Possible response for reference lookup:

```json
{
  "job_id": "job_456",
  "status": "succeeded",
  "references_bib_path": "artifacts/references.bib",
  "download_urls": {
    "bib": "/jobs/job_456/files/references.bib"
  }
}
```

## 9. Job Execution Model

V1 should use background tasks or a local in-process job runner.

Recommended stages for idea report:

1. `workspace_init`
2. `codex_generate_idea_source`
3. `codex_generate_claims_queries`
4. `citation_search`
5. `citation_prescreen`
6. `citation_correct`
7. `citation_shortlist`
8. `idea_assess`
9. `report_render`
10. `completed`

Recommended stages for reference lookup:

1. `workspace_init`
2. `save_input_file`
3. `pdf_to_text_if_needed`
4. `codex_generate_claims_queries`
5. `citation_search`
6. `citation_prescreen`
7. `citation_correct`
8. `citation_shortlist`
9. `bib_generate`
10. `completed`

## 10. Frontend Direction

Frontend should remain lightweight in V1.

Recommended pages:

1. idea report submission page
2. reference lookup submission page
3. job status page
4. result page

The first version does not need a heavy dashboard.

The most important frontend behavior is:

- submit job
- poll status
- preview markdown or bib
- download output

## 11. PDF Export

Markdown should be the default V1 output for idea generation.

Reason:

- Markdown already fits AutoScholar report generation
- PDF generation adds another dependency layer
- PDF rendering quality can become a separate engineering task

Recommended V1.5 options:

- `pandoc`
- browser-based print rendering
- a dedicated markdown-to-pdf step

## 12. Reliability And Risk Control

### 12.1 Main Risks

1. shell-based Codex invocation may be brittle if prompts are too open-ended
2. arbitrary PDF extraction quality may vary
3. long-running searches need observable job status
4. filesystem-backed workspaces need strict isolation
5. external Semantic Scholar availability can affect job success

### 12.2 Controls

- keep Codex output scope narrow
- validate generated artifacts before continuing
- use per-job workspace isolation
- record stage-level status and errors
- preserve raw generated files for debugging
- make retries explicit only for network-dependent stages

## 13. Implementation Recommendation

Recommended delivery order:

1. build backend job model and workspace runtime layout
2. implement `reference lookup` first
3. validate `references.bib` end-to-end
4. implement `idea report` on top of the same execution framework
5. add optional PDF export after Markdown flow is stable

Reason:

`reference lookup` is closer to existing AutoScholar strengths and is the safer MVP.

## 14. Non-Goals For V1

- fine-grained human-in-the-loop editing
- collaborative workspace sharing
- persistent user accounts
- cloud-native scaling
- replacing AutoScholar's internal workflow model

## 15. Summary

The proposed plan is feasible.

The strongest version of the plan is:

- FastAPI as the service layer
- local Codex as a bounded generation and extraction agent
- AutoScholar as the workflow engine
- one workspace per job
- Markdown and BibTeX as the primary V1 outputs

The recommended MVP priority is:

1. `reference lookup`
2. `idea report generation`
3. optional `PDF export`
