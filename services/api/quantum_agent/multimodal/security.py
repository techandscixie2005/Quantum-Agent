"""Bounded, content-based validation for untrusted student uploads."""

from __future__ import annotations

import importlib
import io
import struct
import unicodedata
import zipfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Protocol

from quantum_agent.db_models import AttachmentKind


class AsyncUpload(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


class UploadValidationError(ValueError):
    """A safe validation failure with a stable machine-readable code."""

    def __init__(self, code: str, detail: str, *, http_status: int = 422) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.http_status = http_status


@dataclass(frozen=True, slots=True)
class UploadValidationPolicy:
    max_bytes: int = 25 * 1024 * 1024
    max_image_pixels: int = 40_000_000
    max_image_dimension: int = 16_384
    max_document_pages: int = 500
    max_archive_entries: int = 5_000
    max_archive_uncompressed_bytes: int = 250 * 1024 * 1024
    max_archive_compression_ratio: float = 100.0
    max_filename_characters: int = 255
    allow_legacy_office: bool = False


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    content: bytes
    safe_filename: str
    extension: str
    detected_media_type: str
    kind: AttachmentKind
    content_sha256: str
    metadata: dict[str, int | float | str | bool]

    @property
    def byte_size(self) -> int:
        return len(self.content)


_MEDIA_TYPES: dict[str, tuple[str, AttachmentKind, frozenset[str]]] = {
    ".png": ("image/png", AttachmentKind.IMAGE, frozenset({"image/png"})),
    ".jpg": (
        "image/jpeg",
        AttachmentKind.IMAGE,
        frozenset({"image/jpeg", "image/pjpeg"}),
    ),
    ".jpeg": (
        "image/jpeg",
        AttachmentKind.IMAGE,
        frozenset({"image/jpeg", "image/pjpeg"}),
    ),
    ".webp": ("image/webp", AttachmentKind.IMAGE, frozenset({"image/webp"})),
    ".pdf": ("application/pdf", AttachmentKind.DOCUMENT, frozenset({"application/pdf"})),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        AttachmentKind.DOCUMENT,
        frozenset({"application/vnd.openxmlformats-officedocument.presentationml.presentation"}),
    ),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        AttachmentKind.DOCUMENT,
        frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    ),
    ".doc": (
        "application/msword",
        AttachmentKind.DOCUMENT,
        frozenset({"application/msword", "application/vnd.ms-word"}),
    ),
    ".ppt": (
        "application/vnd.ms-powerpoint",
        AttachmentKind.DOCUMENT,
        frozenset(
            {
                "application/vnd.ms-powerpoint",
                "application/mspowerpoint",
                "application/x-mspowerpoint",
            }
        ),
    ),
    ".txt": ("text/plain", AttachmentKind.TEXT, frozenset({"text/plain"})),
    ".md": (
        "text/markdown",
        AttachmentKind.TEXT,
        frozenset({"text/markdown", "text/plain", "text/x-markdown"}),
    ),
}

_CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_CFB_FREE_SECTOR = 0xFFFFFFFF
_CFB_END_OF_CHAIN = 0xFFFFFFFE
_CFB_FAT_SECTOR = 0xFFFFFFFD
_CFB_DIFAT_SECTOR = 0xFFFFFFFC
_CFB_SPECIAL_SECTORS = {
    _CFB_FREE_SECTOR,
    _CFB_END_OF_CHAIN,
    _CFB_FAT_SECTOR,
    _CFB_DIFAT_SECTOR,
}
_CFB_ACTIVE_NAMES = {
    "vba",
    "_vba_project",
    "macros",
    "objectpool",
    "encryptioninfo",
    "encryptedpackage",
    "encryptedsummary",
}


def safe_filename(filename: str | None, *, max_characters: int = 255) -> str:
    """Return a display-only basename with path/control characters removed."""

    normalized = unicodedata.normalize("NFC", filename or "upload")
    normalized = normalized.replace("\\", "/")
    basename = Path(normalized).name
    cleaned = "".join(
        character
        for character in basename
        if character not in {"\x00", "\r", "\n"}
        and not unicodedata.category(character).startswith("C")
    ).strip(" .")
    if not cleaned or cleaned in {".", ".."}:
        cleaned = "upload"
    if len(cleaned) <= max_characters:
        return cleaned
    suffix = Path(cleaned).suffix[:20]
    stem_limit = max(1, max_characters - len(suffix))
    return f"{cleaned[:stem_limit]}{suffix}"


async def read_bounded(upload: AsyncUpload, *, max_bytes: int) -> bytes:
    """Read at most ``max_bytes + 1`` bytes without trusting multipart metadata."""

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(min(64 * 1024, max_bytes + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise UploadValidationError(
                "ATTACHMENT_TOO_LARGE",
                "Attachment exceeds the configured byte limit",
                http_status=413,
            )
    content = b"".join(chunks)
    if not content:
        raise UploadValidationError("ATTACHMENT_EMPTY", "Attachment must not be empty")
    return content


def _png_dimensions(content: bytes) -> tuple[int, int] | None:
    if len(content) < 24 or not content.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    if content[12:16] != b"IHDR":
        raise UploadValidationError("INVALID_IMAGE", "PNG is missing its IHDR header")
    return struct.unpack(">II", content[16:24])


def _jpeg_dimensions(content: bytes) -> tuple[int, int] | None:
    if len(content) < 4 or not content.startswith(b"\xff\xd8\xff"):
        return None
    offset = 2
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 4 <= len(content):
        if content[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(content) and content[offset] == 0xFF:
            offset += 1
        if offset >= len(content):
            break
        marker = content[offset]
        offset += 1
        if marker in {0xD8, 0xD9}:
            continue
        if marker == 0xDA:
            break
        if offset + 2 > len(content):
            break
        segment_length = int.from_bytes(content[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(content):
            raise UploadValidationError("INVALID_IMAGE", "JPEG has an invalid segment")
        if marker in sof_markers:
            if segment_length < 7:
                raise UploadValidationError("INVALID_IMAGE", "JPEG frame header is truncated")
            height = int.from_bytes(content[offset + 3 : offset + 5], "big")
            width = int.from_bytes(content[offset + 5 : offset + 7], "big")
            return width, height
        offset += segment_length
    raise UploadValidationError("INVALID_IMAGE", "JPEG dimensions could not be verified")


def _webp_dimensions(content: bytes) -> tuple[int, int] | None:
    if len(content) < 30 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        return None
    chunk = content[12:16]
    if chunk == b"VP8X":
        width = int.from_bytes(content[24:27], "little") + 1
        height = int.from_bytes(content[27:30], "little") + 1
        return width, height
    if chunk == b"VP8L" and content[20] == 0x2F:
        bits = int.from_bytes(content[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 " and content[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(content[26:28], "little") & 0x3FFF
        height = int.from_bytes(content[28:30], "little") & 0x3FFF
        return width, height
    raise UploadValidationError("INVALID_IMAGE", "WebP dimensions could not be verified")


def _inspect_image(
    content: bytes,
    policy: UploadValidationPolicy,
) -> tuple[str, dict[str, int | float | str | bool]]:
    detected: tuple[str, tuple[int, int] | None]
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = (".png", _png_dimensions(content))
    elif content.startswith(b"\xff\xd8\xff"):
        detected = (".jpg", _jpeg_dimensions(content))
    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        detected = (".webp", _webp_dimensions(content))
    else:
        raise UploadValidationError(
            "UNSUPPORTED_MEDIA_TYPE",
            "File content is not an allowed image type",
            http_status=415,
        )
    width, height = detected[1] or (0, 0)
    if width < 1 or height < 1:
        raise UploadValidationError("INVALID_IMAGE", "Image dimensions must be positive")
    if width > policy.max_image_dimension or height > policy.max_image_dimension:
        raise UploadValidationError(
            "IMAGE_DIMENSIONS_EXCEEDED",
            "Image dimensions exceed the configured limit",
            http_status=413,
        )
    if width * height > policy.max_image_pixels:
        raise UploadValidationError(
            "IMAGE_PIXELS_EXCEEDED",
            "Image pixel count exceeds the configured limit",
            http_status=413,
        )
    return detected[0], {"width_pixels": width, "height_pixels": height}


def _safe_archive_name(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name:
        return False
    path = PurePosixPath(name)
    windows = PureWindowsPath(name)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and not windows.is_absolute()
        and not windows.drive
    )


def _inspect_office_archive(
    content: bytes,
    policy: UploadValidationPolicy,
) -> tuple[str, dict[str, int | float | str | bool]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (OSError, zipfile.BadZipFile) as error:
        raise UploadValidationError(
            "INVALID_ARCHIVE", "Office document is not a valid ZIP"
        ) from error
    with archive:
        entries = archive.infolist()
        if len(entries) > policy.max_archive_entries:
            raise UploadValidationError(
                "ARCHIVE_ENTRIES_EXCEEDED",
                "Office document contains too many archive entries",
                http_status=413,
            )
        total_compressed = 0
        total_uncompressed = 0
        names: set[str] = set()
        for entry in entries:
            if not _safe_archive_name(entry.filename):
                raise UploadValidationError(
                    "UNSAFE_ARCHIVE_PATH", "Office document contains an unsafe archive path"
                )
            if entry.filename in names:
                raise UploadValidationError(
                    "DUPLICATE_ARCHIVE_ENTRY",
                    "Office document contains a duplicate archive entry",
                )
            mode = (entry.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise UploadValidationError(
                    "UNSAFE_ARCHIVE_ENTRY", "Office document contains a symbolic link"
                )
            if entry.flag_bits & 0x1:
                raise UploadValidationError(
                    "ENCRYPTED_ARCHIVE", "Encrypted office documents are not supported"
                )
            lowered = entry.filename.casefold()
            if (
                lowered.endswith("vbaproject.bin")
                or "/activex/" in f"/{lowered}"
                or "/embeddings/" in f"/{lowered}"
            ):
                raise UploadValidationError(
                    "ACTIVE_CONTENT_REJECTED", "Office document contains active or embedded content"
                )
            names.add(entry.filename)
            total_compressed += entry.compress_size
            total_uncompressed += entry.file_size
            if entry.file_size > policy.max_archive_uncompressed_bytes:
                raise UploadValidationError(
                    "ARCHIVE_SIZE_EXCEEDED",
                    "An archive entry exceeds the expansion limit",
                    http_status=413,
                )
            entry_ratio = entry.file_size / max(entry.compress_size, 1)
            if entry_ratio > policy.max_archive_compression_ratio:
                raise UploadValidationError(
                    "ARCHIVE_RATIO_EXCEEDED",
                    "Office document exceeds the compression-ratio limit",
                    http_status=413,
                )
        if total_uncompressed > policy.max_archive_uncompressed_bytes:
            raise UploadValidationError(
                "ARCHIVE_SIZE_EXCEEDED",
                "Office document exceeds the expansion limit",
                http_status=413,
            )
        ratio = total_uncompressed / max(total_compressed, 1)
        if ratio > policy.max_archive_compression_ratio:
            raise UploadValidationError(
                "ARCHIVE_RATIO_EXCEEDED",
                "Office document exceeds the compression-ratio limit",
                http_status=413,
            )
        required = "[Content_Types].xml" in names
        is_docx = required and "word/document.xml" in names
        is_pptx = required and "ppt/presentation.xml" in names
        if is_docx == is_pptx:
            raise UploadValidationError(
                "UNSUPPORTED_OFFICE_DOCUMENT",
                "ZIP content is not an unambiguous DOCX or PPTX document",
                http_status=415,
            )
        extension = ".docx" if is_docx else ".pptx"
        return extension, {
            "archive_entries": len(entries),
            "archive_uncompressed_bytes": total_uncompressed,
            "archive_compression_ratio": round(ratio, 4),
        }


def _cfb_sector(
    content: bytes,
    *,
    sector_id: int,
    sector_size: int,
    sector_count: int,
) -> bytes:
    if sector_id in _CFB_SPECIAL_SECTORS or not 0 <= sector_id < sector_count:
        raise UploadValidationError(
            "INVALID_LEGACY_OFFICE",
            "Legacy Office document references an invalid compound-file sector",
        )
    start = (sector_id + 1) * sector_size
    end = start + sector_size
    if end > len(content):
        raise UploadValidationError(
            "INVALID_LEGACY_OFFICE",
            "Legacy Office compound-file sector is truncated",
        )
    return content[start:end]


def _cfb_u32_values(data: bytes) -> list[int]:
    if len(data) % 4:
        raise UploadValidationError(
            "INVALID_LEGACY_OFFICE",
            "Legacy Office compound-file table is misaligned",
        )
    return list(struct.unpack(f"<{len(data) // 4}I", data))


def _cfb_fat(
    content: bytes,
    *,
    sector_size: int,
    sector_count: int,
    fat_sector_count: int,
    first_difat_sector: int,
    difat_sector_count: int,
    max_entries: int,
) -> list[int]:
    header_difat = _cfb_u32_values(content[76:512])
    fat_sector_ids = [item for item in header_difat if item != _CFB_FREE_SECTOR]
    current = first_difat_sector
    visited: set[int] = set()
    per_difat = sector_size // 4 - 1
    if difat_sector_count > max_entries:
        raise UploadValidationError(
            "ARCHIVE_ENTRIES_EXCEEDED",
            "Legacy Office document contains too many allocation tables",
            http_status=413,
        )
    for _ in range(difat_sector_count):
        if current in visited:
            raise UploadValidationError(
                "INVALID_LEGACY_OFFICE",
                "Legacy Office DIFAT contains a cycle",
            )
        visited.add(current)
        values = _cfb_u32_values(
            _cfb_sector(
                content,
                sector_id=current,
                sector_size=sector_size,
                sector_count=sector_count,
            )
        )
        fat_sector_ids.extend(
            item for item in values[:per_difat] if item != _CFB_FREE_SECTOR
        )
        current = values[-1]
    if difat_sector_count == 0 and first_difat_sector not in {
        _CFB_END_OF_CHAIN,
        _CFB_FREE_SECTOR,
    }:
        raise UploadValidationError(
            "INVALID_LEGACY_OFFICE",
            "Legacy Office DIFAT header is inconsistent",
        )
    if difat_sector_count and current != _CFB_END_OF_CHAIN:
        raise UploadValidationError(
            "INVALID_LEGACY_OFFICE",
            "Legacy Office DIFAT chain did not terminate",
        )
    if len(fat_sector_ids) != fat_sector_count or fat_sector_count > max_entries:
        raise UploadValidationError(
            "INVALID_LEGACY_OFFICE",
            "Legacy Office FAT count is inconsistent or excessive",
        )
    if len(set(fat_sector_ids)) != len(fat_sector_ids):
        raise UploadValidationError(
            "INVALID_LEGACY_OFFICE",
            "Legacy Office FAT references duplicate sectors",
        )
    fat: list[int] = []
    for sector_id in fat_sector_ids:
        fat.extend(
            _cfb_u32_values(
                _cfb_sector(
                    content,
                    sector_id=sector_id,
                    sector_size=sector_size,
                    sector_count=sector_count,
                )
            )
        )
    return fat


def _cfb_chain(
    content: bytes,
    *,
    first_sector: int,
    fat: list[int],
    sector_size: int,
    sector_count: int,
    max_sectors: int,
) -> bytes:
    current = first_sector
    visited: set[int] = set()
    chunks: list[bytes] = []
    while current != _CFB_END_OF_CHAIN:
        if current in visited or len(visited) >= max_sectors or current >= len(fat):
            raise UploadValidationError(
                "INVALID_LEGACY_OFFICE",
                "Legacy Office compound-file chain is cyclic or excessive",
            )
        visited.add(current)
        chunks.append(
            _cfb_sector(
                content,
                sector_id=current,
                sector_size=sector_size,
                sector_count=sector_count,
            )
        )
        current = fat[current]
        if current in {_CFB_FREE_SECTOR, _CFB_FAT_SECTOR, _CFB_DIFAT_SECTOR}:
            raise UploadValidationError(
                "INVALID_LEGACY_OFFICE",
                "Legacy Office compound-file chain has an invalid terminator",
            )
    return b"".join(chunks)


def _cfb_directory_names(
    directory: bytes,
    *,
    policy: UploadValidationPolicy,
) -> tuple[set[str], int, int]:
    names: set[str] = set()
    stream_count = 0
    total_stream_bytes = 0
    entry_count = 0
    if len(directory) % 128:
        raise UploadValidationError(
            "INVALID_LEGACY_OFFICE",
            "Legacy Office directory is misaligned",
        )
    for offset in range(0, len(directory), 128):
        entry = directory[offset : offset + 128]
        object_type = entry[66]
        if object_type == 0:
            continue
        entry_count += 1
        if entry_count > policy.max_archive_entries:
            raise UploadValidationError(
                "ARCHIVE_ENTRIES_EXCEEDED",
                "Legacy Office document contains too many directory entries",
                http_status=413,
            )
        name_length = struct.unpack_from("<H", entry, 64)[0]
        if name_length < 2 or name_length > 64 or name_length % 2:
            raise UploadValidationError(
                "INVALID_LEGACY_OFFICE",
                "Legacy Office directory contains an invalid name",
            )
        try:
            name = entry[: name_length - 2].decode("utf-16le", errors="strict")
        except UnicodeDecodeError as error:
            raise UploadValidationError(
                "INVALID_LEGACY_OFFICE",
                "Legacy Office directory name is malformed",
            ) from error
        normalized = name.casefold()
        if normalized in names:
            raise UploadValidationError(
                "INVALID_LEGACY_OFFICE",
                "Legacy Office document contains duplicate directory names",
            )
        names.add(normalized)
        if (
            normalized in _CFB_ACTIVE_NAMES
            or normalized.startswith("mbd")
            or "activex" in normalized
        ):
            raise UploadValidationError(
                "ACTIVE_CONTENT_REJECTED",
                "Legacy Office document contains macros, encryption, or embedded content",
            )
        if object_type == 2:
            stream_count += 1
            stream_size = struct.unpack_from("<Q", entry, 120)[0]
            if stream_size > policy.max_archive_uncompressed_bytes:
                raise UploadValidationError(
                    "ARCHIVE_SIZE_EXCEEDED",
                    "A Legacy Office stream exceeds the configured limit",
                    http_status=413,
                )
            total_stream_bytes += stream_size
            if total_stream_bytes > policy.max_archive_uncompressed_bytes:
                raise UploadValidationError(
                    "ARCHIVE_SIZE_EXCEEDED",
                    "Legacy Office streams exceed the configured limit",
                    http_status=413,
                )
    return names, stream_count, total_stream_bytes


def _inspect_legacy_office(
    content: bytes,
    policy: UploadValidationPolicy,
) -> tuple[str, dict[str, int | float | str | bool]]:
    if not policy.allow_legacy_office:
        raise UploadValidationError(
            "LEGACY_OFFICE_CONVERTER_UNAVAILABLE",
            "Legacy .doc/.ppt uploads require a configured isolated conversion service",
            http_status=415,
        )
    if len(content) < 1_536 or not content.startswith(_CFB_MAGIC):
        raise UploadValidationError(
            "INVALID_LEGACY_OFFICE",
            "File content is not a valid Legacy Office compound document",
        )
    byte_order = struct.unpack_from("<H", content, 28)[0]
    sector_shift = struct.unpack_from("<H", content, 30)[0]
    if byte_order != 0xFFFE or sector_shift not in {9, 12}:
        raise UploadValidationError(
            "INVALID_LEGACY_OFFICE",
            "Legacy Office compound-file header is unsupported",
        )
    sector_size = 1 << sector_shift
    if len(content) < sector_size or (len(content) - sector_size) % sector_size:
        raise UploadValidationError(
            "INVALID_LEGACY_OFFICE",
            "Legacy Office compound-file length is inconsistent",
        )
    sector_count = len(content) // sector_size - 1
    fat_sector_count = struct.unpack_from("<I", content, 44)[0]
    first_directory_sector = struct.unpack_from("<I", content, 48)[0]
    first_difat_sector = struct.unpack_from("<I", content, 68)[0]
    difat_sector_count = struct.unpack_from("<I", content, 72)[0]
    fat = _cfb_fat(
        content,
        sector_size=sector_size,
        sector_count=sector_count,
        fat_sector_count=fat_sector_count,
        first_difat_sector=first_difat_sector,
        difat_sector_count=difat_sector_count,
        max_entries=policy.max_archive_entries,
    )
    directory = _cfb_chain(
        content,
        first_sector=first_directory_sector,
        fat=fat,
        sector_size=sector_size,
        sector_count=sector_count,
        max_sectors=min(sector_count, policy.max_archive_entries),
    )
    names, stream_count, total_stream_bytes = _cfb_directory_names(
        directory,
        policy=policy,
    )
    is_doc = "worddocument" in names
    is_ppt = "powerpoint document" in names
    if is_doc == is_ppt:
        raise UploadValidationError(
            "UNSUPPORTED_LEGACY_OFFICE_DOCUMENT",
            "Compound file is not an unambiguous Word .doc or PowerPoint .ppt document",
            http_status=415,
        )
    return (".doc" if is_doc else ".ppt"), {
        "cfb_directory_entries": len(names),
        "cfb_stream_count": stream_count,
        "cfb_declared_stream_bytes": total_stream_bytes,
        "legacy_office_requires_conversion": True,
    }


def _inspect_pdf(
    content: bytes,
    policy: UploadValidationPolicy,
) -> dict[str, int | float | str | bool]:
    if not content.startswith(b"%PDF-"):
        raise UploadValidationError(
            "UNSUPPORTED_MEDIA_TYPE", "File content is not a PDF", http_status=415
        )
    try:
        try:
            pdf_module = importlib.import_module("pymupdf")
        except ImportError:  # pragma: no cover - compatibility import
            pdf_module = importlib.import_module("fitz")
        document: Any = pdf_module.open(stream=content, filetype="pdf")
        try:
            page_count = int(document.page_count)
        finally:
            document.close()
    except Exception as error:
        raise UploadValidationError("INVALID_PDF", "PDF structure could not be verified") from error
    if page_count > policy.max_document_pages:
        raise UploadValidationError(
            "DOCUMENT_PAGES_EXCEEDED", "PDF exceeds the configured page limit", http_status=413
        )
    return {"page_count": page_count}


def _inspect_text(content: bytes) -> dict[str, int | float | str | bool]:
    if b"\x00" in content:
        raise UploadValidationError("INVALID_TEXT", "Text attachment contains NUL bytes")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise UploadValidationError("INVALID_TEXT", "Text attachments must be UTF-8") from error
    return {"encoding": "utf-8", "line_count": decoded.count("\n") + 1}


def validate_upload(
    *,
    content: bytes,
    filename: str | None,
    declared_media_type: str | None,
    policy: UploadValidationPolicy | None = None,
) -> ValidatedUpload:
    """Validate declared metadata against independently detected file content."""

    limits = policy or UploadValidationPolicy()
    if not content:
        raise UploadValidationError("ATTACHMENT_EMPTY", "Attachment must not be empty")
    if len(content) > limits.max_bytes:
        raise UploadValidationError(
            "ATTACHMENT_TOO_LARGE", "Attachment exceeds the configured byte limit", http_status=413
        )
    display_name = safe_filename(filename, max_characters=limits.max_filename_characters)
    requested_extension = Path(display_name).suffix.casefold()
    if requested_extension not in _MEDIA_TYPES:
        raise UploadValidationError(
            "UNSUPPORTED_EXTENSION", "Filename extension is not allowed", http_status=415
        )

    metadata: dict[str, int | float | str | bool]
    if content.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")) or (
        content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    ):
        detected_extension, metadata = _inspect_image(content, limits)
    elif content.startswith(b"%PDF-"):
        detected_extension, metadata = ".pdf", _inspect_pdf(content, limits)
    elif content.startswith(b"PK\x03\x04"):
        detected_extension, metadata = _inspect_office_archive(content, limits)
    elif content.startswith(_CFB_MAGIC):
        detected_extension, metadata = _inspect_legacy_office(content, limits)
    else:
        metadata = _inspect_text(content)
        if requested_extension not in {".txt", ".md"}:
            raise UploadValidationError(
                "UNSUPPORTED_MEDIA_TYPE",
                "File content does not match an allowed format",
                http_status=415,
            )
        detected_extension = requested_extension

    extension_matches = requested_extension == detected_extension or {
        requested_extension,
        detected_extension,
    } == {".jpg", ".jpeg"}
    if not extension_matches:
        raise UploadValidationError(
            "FILE_TYPE_MISMATCH", "Filename extension does not match file content", http_status=415
        )
    detected_media_type, kind, accepted_declared_types = _MEDIA_TYPES[requested_extension]
    normalized_declared = (declared_media_type or "").partition(";")[0].strip().casefold()
    if normalized_declared not in accepted_declared_types:
        raise UploadValidationError(
            "MIME_TYPE_MISMATCH", "Declared media type does not match file content", http_status=415
        )
    metadata = {
        **metadata,
        "declared_media_type": normalized_declared,
        "detected_by": "magic-and-structure-v1",
    }
    return ValidatedUpload(
        content=content,
        safe_filename=display_name,
        extension=requested_extension,
        detected_media_type=detected_media_type,
        kind=kind,
        content_sha256=sha256(content).hexdigest(),
        metadata=metadata,
    )


__all__ = [
    "AsyncUpload",
    "UploadValidationError",
    "UploadValidationPolicy",
    "ValidatedUpload",
    "read_bounded",
    "safe_filename",
    "validate_upload",
]
