from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.search_supervisor import load_search_retry_config, retry_search_until_clear
from app.autoscholar_path import AUTOSCHOLAR_SRC  # noqa: F401

from autoscholar.citation.config import SearchConfig
from autoscholar.io import read_yaml
from autoscholar.workspace import Workspace


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retry AutoScholar search until failures clear.")
    parser.add_argument("--workspace", required=True, help="Workspace directory")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "search_retry.yaml"),
        help="Supervisor config YAML path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Workspace.load(Path(args.workspace))
    search_config = SearchConfig.model_validate(read_yaml(workspace.require_path("configs", "search")))
    retry_config = load_search_retry_config(Path(args.config))

    def progress(stage: str, message: str) -> None:
        print(f"[{stage}] {message}", flush=True)

    summary = retry_search_until_clear(
        workspace=workspace,
        search_config=search_config,
        retry_config=retry_config,
        progress_callback=progress,
    )
    print(summary, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
