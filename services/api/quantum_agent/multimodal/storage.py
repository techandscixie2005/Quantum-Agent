"""Boundary-safe local storage for immutable student attachments."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from uuid import UUID, uuid4

import anyio


class AttachmentStorageError(RuntimeError):
    pass


class AttachmentStorageBoundaryError(AttachmentStorageError):
    pass


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SUFFIX_RE = re.compile(r"^\.[a-z0-9]{1,8}$")


@dataclass(frozen=True, slots=True)
class LocalAttachmentStorage:
    """Store bytes beneath one explicit root using generated relative keys."""

    root: Path

    def __post_init__(self) -> None:
        root = self.root.expanduser().resolve()
        if root == Path(root.anchor):
            raise AttachmentStorageBoundaryError("attachment root cannot be a filesystem root")
        object.__setattr__(self, "root", root)

    def storage_key(
        self,
        *,
        course_id: UUID,
        curriculum_edition_id: UUID,
        owner_user_id: UUID,
        content_sha256: str,
        extension: str,
    ) -> str:
        if not _SHA256_RE.fullmatch(content_sha256):
            raise AttachmentStorageBoundaryError("invalid attachment SHA-256")
        extension = extension.casefold()
        if not _SUFFIX_RE.fullmatch(extension):
            raise AttachmentStorageBoundaryError("invalid attachment extension")
        return "/".join(
            (
                str(course_id),
                str(curriculum_edition_id),
                str(owner_user_id),
                content_sha256[:2],
                f"{content_sha256}{extension}",
            )
        )

    def resolve(self, storage_key: str, *, require_file: bool = False) -> Path:
        if not storage_key or "\x00" in storage_key or "\\" in storage_key:
            raise AttachmentStorageBoundaryError("invalid attachment storage key")
        relative = Path(storage_key)
        windows = PureWindowsPath(storage_key)
        if (
            relative.is_absolute()
            or windows.is_absolute()
            or windows.drive
            or ".." in relative.parts
        ):
            raise AttachmentStorageBoundaryError("attachment storage key is not relative")
        target = (self.root / relative).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as error:
            raise AttachmentStorageBoundaryError("attachment storage key escapes root") from error
        if require_file and (not target.exists() or not target.is_file()):
            raise AttachmentStorageError("attachment file is unavailable")
        return target

    async def store(self, *, storage_key: str, content: bytes, expected_sha256: str) -> Path:
        if not content:
            raise AttachmentStorageError("cannot store an empty attachment")
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise AttachmentStorageError("attachment bytes do not match the validated SHA-256")
        target = self.resolve(storage_key)

        def write() -> Path:
            target.parent.mkdir(parents=True, exist_ok=True)
            resolved_parent = target.parent.resolve()
            try:
                resolved_parent.relative_to(self.root)
            except ValueError as error:
                raise AttachmentStorageBoundaryError("attachment directory escapes root") from error
            if target.exists():
                if not target.is_file():
                    raise AttachmentStorageError("attachment target is not a regular file")
                existing_hash = hashlib.sha256(target.read_bytes()).hexdigest()
                if existing_hash != expected_sha256:
                    raise AttachmentStorageError("existing attachment failed integrity validation")
                return target
            temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
            try:
                with temporary.open("xb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
            finally:
                if temporary.exists():
                    temporary.unlink()
            return target

        return await anyio.to_thread.run_sync(write)

    async def delete(self, storage_key: str) -> None:
        target = self.resolve(storage_key)

        def unlink() -> None:
            try:
                target.unlink()
            except FileNotFoundError:
                return
            except IsADirectoryError as error:
                raise AttachmentStorageError("attachment target is not a regular file") from error

        await anyio.to_thread.run_sync(unlink)


__all__ = [
    "AttachmentStorageBoundaryError",
    "AttachmentStorageError",
    "LocalAttachmentStorage",
]
