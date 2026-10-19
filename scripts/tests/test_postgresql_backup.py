"""Offline safety checks for the opt-in isolated backup drill; no database access."""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "validate-postgresql-backup.py"


@pytest.fixture
def backup() -> dict[str, Any]:
    return runpy.run_path(str(SCRIPT))


@pytest.mark.parametrize(
    ("url", "source"),
    [
        ("postgresql+asyncpg://user:secret@production:55432/backend_live", "allowed"),
        ("postgresql+asyncpg://user:secret@127.0.0.1:5432/backend_live", "allowed"),
        ("postgresql+asyncpg://user:secret@127.0.0.1:55432/production", "allowed"),
        ("postgresql+asyncpg://user:secret@127.0.0.1:55432/backend_live", "other_source"),
    ],
)
def test_guard_rejects_wrong_host_port_database_and_source_before_connect(
    backup: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    url: str, source: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", url)

    def forbidden_connect(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("rejected target must never connect")

    monkeypatch.setattr(backup["psycopg"], "connect", forbidden_connect)
    archive = tmp_path / "must-not-exist.dump"
    with pytest.raises(ValueError, match="^isolated_trial_database_required$"):
        backup["validate"](
            {}, source_database=backup["SOURCE"] if source == "allowed" else source,
            archive=archive,
        )
    assert not archive.exists()


def test_docker_command_keeps_credentials_inside_exact_container_and_arguments_separate(
    backup: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "never-copy-this-value")
    argument = "--dbname=literal; must-not-be-shell-code"
    command = backup["docker_command"]("pg_dump", argument)
    assert command[:4] == ["docker", "exec", "-i", backup["CONTAINER"]]
    assert command[-2:] == ["pg_dump", argument]
    assert "never-copy-this-value" not in " ".join(command)
    assert "$POSTGRES_PASSWORD" in command[6]
    assert backup["docker_command"]("pg_restore", "--version") == [
        "docker", "exec", backup["CONTAINER"], "pg_restore", "--version",
    ]
    with pytest.raises(ValueError, match="unsupported database program"):
        backup["docker_command"]("sh", "-c", "unsafe")


def test_tool_failure_is_bounded_and_does_not_expose_error_rows_or_credentials(
    backup: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def failed(command: list[str], **kwargs: Any) -> SimpleNamespace:
        seen.update(kwargs)
        return SimpleNamespace(
            returncode=1, stdout=b"private row value", stderr=b"private auth value",
        )

    monkeypatch.setattr(backup["subprocess"], "run", failed)
    with pytest.raises(RuntimeError, match="^database_tool_failed$") as failure:
        backup["run_command"](["docker", "exec", backup["CONTAINER"], "pg_dump"])
    assert seen["timeout"] == 120 and seen["check"] is False
    assert "private" not in str(failure.value)
