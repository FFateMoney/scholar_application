from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import SETTINGS


class CodexExecutionError(RuntimeError):
    """Raised when the local Codex CLI fails."""


@dataclass(frozen=True)
class CodexRunArtifacts:
    prompt_path: Path
    stdout_path: Path
    stderr_path: Path
    last_message_path: Path


def prepare_codex_artifacts(workspace_dir: Path, label: str) -> CodexRunArtifacts:
    logs_dir = workspace_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = logs_dir / f"{label}.prompt.txt"
    stdout_path = logs_dir / f"{label}.stdout.log"
    stderr_path = logs_dir / f"{label}.stderr.log"
    last_message_path = logs_dir / f"{label}.last_message.txt"

    for path in (stdout_path, stderr_path, last_message_path):
        path.touch(exist_ok=True)

    return CodexRunArtifacts(
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        last_message_path=last_message_path,
    )


def run_codex_prompt(
    prompt: str,
    workspace_dir: Path,
    label: str,
    artifacts: CodexRunArtifacts | None = None,
) -> CodexRunArtifacts:
    artifacts = artifacts or prepare_codex_artifacts(workspace_dir, label)
    prompt_path = artifacts.prompt_path
    stdout_path = artifacts.stdout_path
    stderr_path = artifacts.stderr_path
    last_message_path = artifacts.last_message_path
    prompt_path.write_text(prompt, encoding="utf-8")

    command = [
        SETTINGS.codex_command,
        "exec",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd",
        str(workspace_dir),
        "--ephemeral",
        "--color",
        "never",
        "--output-last-message",
        str(last_message_path),
        "-",
    ]
    if SETTINGS.codex_model:
        command[2:2] = ["--model", SETTINGS.codex_model]

    with prompt_path.open("r", encoding="utf-8") as prompt_handle, stdout_path.open(
        "a",
        encoding="utf-8",
    ) as stdout_handle, stderr_path.open("a", encoding="utf-8") as stderr_handle:
        try:
            process = subprocess.Popen(
                command,
                stdin=prompt_handle,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                cwd=workspace_dir,
            )
        except FileNotFoundError as exc:
            raise CodexExecutionError(
                "Local Codex CLI was not found. "
                f"Tried command: {SETTINGS.codex_command!r}. "
                "Set AUTOSCHOLAR_CODEX_COMMAND to the absolute path of the codex binary, "
                "then restart the backend."
            ) from exc
        try:
            return_code = process.wait(timeout=SETTINGS.codex_timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise CodexExecutionError(
                f"codex exec timed out after {SETTINGS.codex_timeout_seconds} seconds"
            ) from exc

    if return_code != 0:
        snippet = ""
        if stderr_path.exists():
            snippet = stderr_path.read_text(encoding="utf-8", errors="replace").strip()[-1200:]
        if not snippet and stdout_path.exists():
            snippet = stdout_path.read_text(encoding="utf-8", errors="replace").strip()[-1200:]
        raise CodexExecutionError(f"codex exec failed with exit code {return_code}: {snippet}")

    return artifacts
