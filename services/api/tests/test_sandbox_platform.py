"""Platform and missing-isolation failures must occur before process creation."""

from __future__ import annotations

import asyncio
import shutil
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

import quantum_agent.coding.sandbox as sandbox
from quantum_agent.coding.models import CodeArtifact, CodeLanguage


def _artifact() -> CodeArtifact:
    return CodeArtifact(language=CodeLanguage.PYTHON, purpose="test only", code="print(1)")


async def test_local_execution_fails_closed_without_posix_resource_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawn = AsyncMock()
    monkeypatch.setattr(sandbox, "_resource", None)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(sandbox.SandboxError, match="POSIX resource limits"):
        await sandbox.SubprocessSandbox().execute_program(_artifact())
    spawn.assert_not_called()


async def test_required_namespace_isolation_cannot_fall_back_to_host_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawn = AsyncMock()
    monkeypatch.setattr(sandbox, "_posix_resource", lambda: ModuleType("resource"))
    monkeypatch.setenv("CODING_SANDBOX_REQUIRE_ISOLATION", "true")
    monkeypatch.setattr(shutil, "which", lambda executable: None)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(sandbox.SandboxError, match="namespace isolation is unavailable"):
        await sandbox.SubprocessSandbox().execute_program(_artifact())
    spawn.assert_not_called()
