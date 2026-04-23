from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .autoscholar_path import AUTOSCHOLAR_ROOT, BACKEND_ROOT, PROJECT_ROOT


def _resolve_codex_command() -> str:
    configured = os.environ.get("AUTOSCHOLAR_CODEX_COMMAND")
    if configured:
        return configured

    discovered = shutil.which("codex")
    if discovered:
        return discovered

    candidate_roots = [
        Path.home() / ".vscode-server" / "extensions",
        Path.home() / ".vscode" / "extensions",
    ]
    for root in candidate_roots:
        for binary in sorted(root.glob("openai.chatgpt-*/bin/linux-x86_64/codex"), reverse=True):
            if binary.is_file():
                return str(binary)

    return "codex"


@dataclass(frozen=True)
class AppSettings:
    project_root: Path = PROJECT_ROOT
    backend_root: Path = BACKEND_ROOT
    autoscholar_root: Path = AUTOSCHOLAR_ROOT
    runtime_root: Path = BACKEND_ROOT / "runtime"
    jobs_root: Path = BACKEND_ROOT / "runtime" / "jobs"
    state_root: Path = BACKEND_ROOT / "runtime" / "state"
    config_root: Path = BACKEND_ROOT / "config"
    codex_command: str = _resolve_codex_command()
    codex_model: str | None = os.environ.get("AUTOSCHOLAR_CODEX_MODEL")
    codex_timeout_seconds: int = int(os.environ.get("AUTOSCHOLAR_CODEX_TIMEOUT_SECONDS", "1800"))
    allow_origins_raw: str = os.environ.get("AUTOSCHOLAR_BACKEND_ALLOW_ORIGINS", "*")

    @property
    def allow_origins(self) -> list[str]:
        return [item.strip() for item in self.allow_origins_raw.split(",") if item.strip()]


SETTINGS = AppSettings()
SETTINGS.jobs_root.mkdir(parents=True, exist_ok=True)
SETTINGS.state_root.mkdir(parents=True, exist_ok=True)
SETTINGS.config_root.mkdir(parents=True, exist_ok=True)
