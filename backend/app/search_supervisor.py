from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel

from .config import SETTINGS
from .autoscholar_path import AUTOSCHOLAR_ROOT  # noqa: F401

from autoscholar.citation import run_search
from autoscholar.citation.config import SearchConfig
from autoscholar.io import read_jsonl, read_yaml
from autoscholar.models import SearchFailureRecord
from autoscholar.workspace import Workspace


class SearchRetryConfig(BaseModel):
    sleep_seconds: float = 20.0
    max_rounds: int = 40
    stale_round_limit: int = 12
    require_empty_failures: bool = True


def load_search_retry_config(path: Path | None = None) -> SearchRetryConfig:
    config_path = path or (SETTINGS.config_root / "search_retry.yaml")
    if config_path.exists():
        return SearchRetryConfig.model_validate(read_yaml(config_path))
    return SearchRetryConfig()


def _failure_records(path: Path) -> list[SearchFailureRecord]:
    if not path.exists():
        return []
    if not path.read_text(encoding="utf-8").strip():
        return []
    return read_jsonl(path, SearchFailureRecord)


def retry_search_until_clear(
    workspace: Workspace,
    search_config: SearchConfig,
    retry_config: SearchRetryConfig,
    progress_callback=None,
) -> dict[str, int | bool]:
    failures_path = workspace.require_path("artifacts", "search_failures")
    last_failure_ids: tuple[str, ...] = ()
    stale_rounds = 0

    for round_index in range(1, retry_config.max_rounds + 1):
        if progress_callback is not None:
            progress_callback(
                "citation_search",
                f"Searching Semantic Scholar. Round {round_index}/{retry_config.max_rounds}.",
            )

        success_count, failure_count = run_search(workspace, search_config)
        failure_ids = tuple(sorted(record.query_id for record in _failure_records(failures_path)))

        if failure_count == 0 and not failure_ids:
            return {
                "rounds": round_index,
                "success_count": success_count,
                "failure_count": 0,
                "cleared": True,
            }

        if failure_ids == last_failure_ids:
            stale_rounds += 1
        else:
            stale_rounds = 0
        last_failure_ids = failure_ids

        if round_index >= retry_config.max_rounds:
            break
        if stale_rounds >= retry_config.stale_round_limit:
            break

        if progress_callback is not None:
            progress_callback(
                "citation_search_retry",
                (
                    f"Search round {round_index} left {len(failure_ids)} failed queries. "
                    f"Sleeping {retry_config.sleep_seconds:.0f}s before retry."
                ),
            )
        time.sleep(retry_config.sleep_seconds)

    remaining = _failure_records(failures_path)
    if remaining and retry_config.require_empty_failures:
        raise RuntimeError(
            "Search retry supervisor stopped before clearing failed queries. "
            f"remaining_failures={len(remaining)} max_rounds={retry_config.max_rounds}"
        )

    return {
        "rounds": retry_config.max_rounds,
        "success_count": 0,
        "failure_count": len(remaining),
        "cleared": len(remaining) == 0,
    }
