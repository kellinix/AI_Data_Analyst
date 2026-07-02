from __future__ import annotations

"""
Fail-closed execution gateway for AI-generated code.

The application must never execute model-generated Python in the API or worker
process. This module only forwards code to an explicitly configured isolated
sandbox provider and captures bounded stdout/stderr for repair attempts.
"""

import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SandboxUnavailableError(RuntimeError):
    """Raised when generated-code execution is requested without a sandbox."""


class UnsafeGeneratedCodeError(ValueError):
    """Raised when generated code asks for forbidden host capabilities."""


@dataclass(slots=True)
class SandboxExecutionRequest:
    code: str
    files: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SandboxExecutionResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    traceback: str | None = None
    artifacts: Mapping[str, str] = field(default_factory=dict)
    attempt: int = 1


RepairCallback = Callable[
    [str, str, str, str | None, int],
    str | Awaitable[str],
]


class GeneratedCodeSandbox:
    """Runs generated code only through an external isolated executor."""

    _FORBIDDEN_PATTERNS = (
        (re.compile(r"\bsubprocess\b"), "subprocess access is not allowed"),
        (re.compile(r"\bos\.system\b"), "shell execution is not allowed"),
        (re.compile(r"\bos\.popen\b"), "shell execution is not allowed"),
        (re.compile(r"\bexec\s*\("), "nested exec is not allowed"),
        (re.compile(r"\beval\s*\("), "eval is not allowed"),
        (re.compile(r"\b__import__\s*\("), "dynamic imports are not allowed"),
        (re.compile(r"\bos\.environ\b"), "environment access is not allowed"),
        (re.compile(r"\bsocket\b"), "network access is not allowed"),
        (re.compile(r"\brequests\b"), "network clients are not allowed"),
        (re.compile(r"\bhttpx\b"), "network clients are not allowed"),
        (re.compile(r"\burllib\b"), "network clients are not allowed"),
        (re.compile(r"\bboto3\b"), "cloud SDK access is not allowed"),
    )

    def __init__(self) -> None:
        self.enabled = settings.ai_code_execution_enabled
        self.provider = settings.ai_code_execution_provider
        self.endpoint = settings.ai_code_execution_endpoint
        self.api_key = settings.ai_code_execution_api_key
        self.default_timeout = settings.ai_code_execution_timeout_seconds
        self.max_repair_attempts = settings.ai_code_execution_max_repair_attempts

    async def execute(
        self,
        request: SandboxExecutionRequest,
        *,
        attempt: int = 1,
    ) -> SandboxExecutionResult:
        """Execute generated code in a configured isolated sandbox.

        This method deliberately has no local fallback. If a remote sandbox is
        not configured, callers get SandboxUnavailableError.
        """

        self._assert_configured()
        self.validate_code(request.code)

        if self.provider == "remote_http":
            return await self._execute_remote_http(request, attempt=attempt)

        raise SandboxUnavailableError(
            f"Unsupported AI code execution provider: {self.provider}"
        )

    async def execute_with_self_healing(
        self,
        initial_code: str,
        repair_callback: RepairCallback,
        *,
        files: Mapping[str, str] | None = None,
        metadata: Mapping[str, Any] | None = None,
        max_attempts: int | None = None,
    ) -> SandboxExecutionResult:
        """Retry failed sandbox executions with repaired code.

        The repair callback receives only bounded stdout/stderr/traceback from
        the sandbox. It must return replacement code for the next attempt.
        """

        attempts = max(1, max_attempts or self.max_repair_attempts + 1)
        code = initial_code
        last_result: SandboxExecutionResult | None = None

        for attempt in range(1, attempts + 1):
            request = SandboxExecutionRequest(
                code=code,
                files=files or {},
                metadata=metadata or {},
            )
            result = await self.execute(request, attempt=attempt)
            last_result = result
            if result.ok or attempt >= attempts:
                return result

            repaired = repair_callback(
                code,
                self._truncate(result.stdout),
                self._truncate(result.stderr),
                self._truncate(result.traceback) if result.traceback else None,
                attempt,
            )
            if inspect.isawaitable(repaired):
                repaired = await repaired
            if not isinstance(repaired, str) or not repaired.strip():
                logger.warning("Sandbox repair callback returned no code", attempt=attempt)
                return result
            code = repaired

        return last_result or SandboxExecutionResult(
            ok=False,
            stderr="No sandbox execution attempt was made.",
        )

    @classmethod
    def validate_code(cls, code: str) -> None:
        for pattern, reason in cls._FORBIDDEN_PATTERNS:
            if pattern.search(code):
                raise UnsafeGeneratedCodeError(reason)

    def _assert_configured(self) -> None:
        if not self.enabled or self.provider == "disabled":
            raise SandboxUnavailableError(
                "AI-generated code execution is disabled. Configure an isolated "
                "remote sandbox before enabling this feature."
            )
        if self.provider == "remote_http" and not self.endpoint:
            raise SandboxUnavailableError(
                "AI code execution provider is remote_http but no endpoint is configured."
            )

    async def _execute_remote_http(
        self,
        request: SandboxExecutionRequest,
        *,
        attempt: int,
    ) -> SandboxExecutionResult:
        timeout = request.timeout_seconds or self.default_timeout
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "code": request.code,
            "files": dict(request.files),
            "timeout_seconds": timeout,
            "network_disabled": True,
            "resource_limits": {
                "cpu_seconds": timeout,
                "memory_mb": 512,
                "processes": 1,
            },
            "metadata": dict(request.metadata),
        }

        async with httpx.AsyncClient(timeout=timeout + 5) as client:
            response = await client.post(self.endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return SandboxExecutionResult(
            ok=bool(data.get("ok")),
            stdout=self._truncate(data.get("stdout", "")),
            stderr=self._truncate(data.get("stderr", "")),
            traceback=self._truncate(data.get("traceback")) if data.get("traceback") else None,
            artifacts=data.get("artifacts") or {},
            attempt=attempt,
        )

    @staticmethod
    def _truncate(value: str | None, limit: int = 8_000) -> str:
        if not value:
            return ""
        value = str(value)
        if len(value) <= limit:
            return value
        return value[:limit] + "\n...[truncated]"


generated_code_sandbox = GeneratedCodeSandbox()
