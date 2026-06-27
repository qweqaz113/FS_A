from __future__ import annotations

import io
import posixpath
import shlex
import subprocess
import tarfile
import uuid

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    FILE_NOT_FOUND,
    IS_DIRECTORY,
    PERMISSION_DENIED,
)
from deepagents.backends.sandbox import BaseSandbox

from enterprise_agent.infra.config import Settings, get_settings


class DockerSandboxBackend(BaseSandbox):
    """Thin DeepAgents sandbox adapter over an existing Docker container."""

    def __init__(
        self,
        *,
        container_name: str,
        workdir: str = "/workspace",
        shell: str = "bash",
        timeout: int = 120,
        max_output_bytes: int = 100_000,
    ) -> None:
        self.container_name = container_name
        self.workdir = workdir
        self.shell = shell
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes
        self._id = f"docker-{container_name}-{uuid.uuid4().hex[:8]}"

    @property
    def id(self) -> str:
        return self._id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        if not command:
            return ExecuteResponse(
                output="Error: command must be a non-empty string.",
                exit_code=1,
                truncated=False,
            )

        cmd = self._docker_exec(self.shell, "-lc", command)
        return self._run_text(cmd, timeout=timeout or self.timeout)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        if not files:
            return []

        archive = self._build_upload_archive(files)
        cmd = self._docker_exec("tar", "-C", "/", "-xf", "-")
        result = self._run_bytes(cmd, input_bytes=archive, timeout=self.timeout)
        error = None if result.returncode == 0 else self._process_error(result)

        return [FileUploadResponse(path=path, error=error) for path, _content in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            responses.append(self._download_one(path))
        return responses

    def _docker_exec(self, *args: str) -> list[str]:
        return [
            "docker",
            "exec",
            "-i",
            "-w",
            self.workdir,
            self.container_name,
            *args,
        ]

    def _run_text(self, cmd: list[str], *, timeout: int) -> ExecuteResponse:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                output=f"Error: command timed out after {timeout} seconds.",
                exit_code=124,
                truncated=False,
            )
        except OSError as exc:
            return ExecuteResponse(
                output=f"Error launching docker command: {exc}",
                exit_code=1,
                truncated=False,
            )

        output = result.stdout or ""
        if result.stderr:
            stderr = "\n".join(f"[stderr] {line}" for line in result.stderr.splitlines())
            output = f"{output.rstrip()}\n{stderr}".strip()
        if not output:
            output = "<no output>"

        truncated = False
        output_bytes = output.encode("utf-8")
        if len(output_bytes) > self.max_output_bytes:
            output = output_bytes[: self.max_output_bytes].decode("utf-8", errors="ignore")
            output += f"\n\n... Output truncated at {self.max_output_bytes} bytes."
            truncated = True

        if result.returncode != 0:
            output = f"{output.rstrip()}\n\nExit code: {result.returncode}"

        return ExecuteResponse(
            output=output,
            exit_code=result.returncode,
            truncated=truncated,
        )

    @staticmethod
    def _run_bytes(
        cmd: list[str],
        *,
        input_bytes: bytes | None = None,
        timeout: int,
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(
                cmd,
                input=input_bytes,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=124,
                stdout=exc.stdout or b"",
                stderr=f"command timed out after {timeout} seconds".encode(),
            )
        except OSError as exc:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout=b"",
                stderr=f"Error launching docker command: {exc}".encode(),
            )

    @staticmethod
    def _build_upload_archive(files: list[tuple[str, bytes]]) -> bytes:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for path, content in files:
                arcname = _container_archive_path(path)
                info = tarfile.TarInfo(arcname)
                info.size = len(content)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(content))
        return buffer.getvalue()

    def _download_one(self, path: str) -> FileDownloadResponse:
        quoted_path = shlex.quote(path)
        rel_path = _container_archive_path(path)
        quoted_rel_path = shlex.quote(rel_path)
        command = (
            f"if [ ! -e {quoted_path} ]; then exit 2; "
            f"elif [ -d {quoted_path} ]; then exit 3; "
            f"elif [ ! -r {quoted_path} ]; then exit 4; "
            f"else tar -C / -cf - {quoted_rel_path}; fi"
        )
        result = self._run_bytes(
            self._docker_exec(self.shell, "-lc", command),
            timeout=self.timeout,
        )

        if result.returncode == 0:
            return FileDownloadResponse(
                path=path,
                content=_read_single_file_from_archive(result.stdout, rel_path),
                error=None,
            )
        if result.returncode == 2:
            return FileDownloadResponse(path=path, content=None, error=FILE_NOT_FOUND)
        if result.returncode == 3:
            return FileDownloadResponse(path=path, content=None, error=IS_DIRECTORY)
        if result.returncode == 4:
            return FileDownloadResponse(path=path, content=None, error=PERMISSION_DENIED)

        return FileDownloadResponse(
            path=path,
            content=None,
            error=self._process_error(result),
        )

    @staticmethod
    def _process_error(result: subprocess.CompletedProcess[bytes]) -> str:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        stdout = result.stdout.decode("utf-8", errors="replace").strip()
        return stderr or stdout or f"docker exec failed with exit code {result.returncode}"


def _container_archive_path(path: str) -> str:
    normalized = posixpath.normpath(path.replace("\\", "/"))
    return normalized.lstrip("/")


def _read_single_file_from_archive(data: bytes, expected_name: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        member = archive.getmember(expected_name)
        extracted = archive.extractfile(member)
        if extracted is None:
            return b""
        return extracted.read()


def build_sandbox_backend(settings: Settings | None = None) -> DockerSandboxBackend:
    settings = settings or get_settings()
    return DockerSandboxBackend(
        container_name=settings.sandbox_container_name,
        workdir=settings.sandbox_workdir,
        shell=settings.sandbox_shell,
        timeout=settings.sandbox_exec_timeout,
        max_output_bytes=settings.sandbox_max_output_bytes,
    )
