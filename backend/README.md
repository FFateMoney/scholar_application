# AutoScholar Backend

Local FastAPI backend for exposing two AutoScholar-powered services:

- `idea report`
- `reference bib lookup`

## Structure

```text
backend/
  app/
    main.py
    jobs.py
    codex_runner.py
    prompts.py
    models.py
    config.py
    autoscholar_path.py
    search_supervisor.py
  config/
    search_retry.yaml
  scripts/
    retry_search_until_clear.py
  runtime/
```

## Install

Run from the `backend/` directory:

```bash
python3 -m pip install -r requirements.txt
```

If your system Python is PEP 668 managed, use a virtual environment first:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

On Debian or Ubuntu, `python3 -m venv` may require installing `python3-venv` first.

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

If the backend cannot find the local Codex CLI, point it to the binary explicitly:

```bash
export AUTOSCHOLAR_CODEX_COMMAND=/absolute/path/to/codex
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints

- `GET /health`
- `POST /jobs/idea-report`
- `POST /jobs/reference-bib`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/result`
- `GET /jobs/{job_id}/files/{artifact_key}`

## Notes

- The backend creates one isolated runtime workspace per job under `backend/runtime/jobs/`.
- It invokes local `codex exec` for idea drafting and claims/query extraction.
- It retries Semantic Scholar search rounds using `config/search_retry.yaml` until failures clear or supervisor limits are hit.
- It calls local Codex a second time after evidence is collected to write the final user-facing idea report.
- It calls AutoScholar Python modules directly for citation, assessment, report, and BibTeX workflows.
- Markdown is the primary V1 report output.
