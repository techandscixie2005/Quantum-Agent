from __future__ import annotations

import io
import struct
import zipfile

import pytest

from quantum_agent.multimodal.security import (
    UploadValidationError,
    UploadValidationPolicy,
    validate_upload,
)


def _office_archive(*, document_entry: str, extra: dict[str, bytes] | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr(document_entry, b"<document/>")
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return output.getvalue()


def _cfb_directory_entry(name: str, object_type: int) -> bytes:
    entry = bytearray(128)
    encoded = name.encode("utf-16le") + b"\x00\x00"
    entry[: len(encoded)] = encoded
    struct.pack_into("<H", entry, 64, len(encoded))
    entry[66] = object_type
    entry[67] = 1
    struct.pack_into("<III", entry, 68, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
    struct.pack_into("<I", entry, 116, 0xFFFFFFFE)
    return bytes(entry)


def _legacy_office_cfb(*names: str) -> bytes:
    header = bytearray(512)
    header[:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<H", header, 24, 0x003E)
    struct.pack_into("<H", header, 26, 3)
    struct.pack_into("<H", header, 28, 0xFFFE)
    struct.pack_into("<H", header, 30, 9)
    struct.pack_into("<H", header, 32, 6)
    struct.pack_into("<I", header, 44, 1)
    struct.pack_into("<I", header, 48, 1)
    struct.pack_into("<I", header, 56, 4096)
    struct.pack_into("<I", header, 60, 0xFFFFFFFE)
    struct.pack_into("<I", header, 68, 0xFFFFFFFE)
    struct.pack_into("<109I", header, 76, 0, *([0xFFFFFFFF] * 108))

    fat = bytearray(b"\xff" * 512)
    struct.pack_into("<I", fat, 0, 0xFFFFFFFD)
    struct.pack_into("<I", fat, 4, 0xFFFFFFFE)
    entries = [_cfb_directory_entry("Root Entry", 5)]
    entries.extend(_cfb_directory_entry(name, 2) for name in names)
    directory = b"".join(entries).ljust(512, b"\x00")
    return bytes(header) + bytes(fat) + directory


def test_forged_declared_mime_and_extension_are_rejected() -> None:
    with pytest.raises(UploadValidationError) as caught:
        validate_upload(
            content=b"%PDF-1.4\nnot an image",
            filename="derivation.png",
            declared_media_type="image/png",
        )

    assert caught.value.code == "INVALID_PDF" or caught.value.code == "FILE_TYPE_MISMATCH"


def test_attachment_byte_limit_is_checked_on_actual_content() -> None:
    with pytest.raises(UploadValidationError) as caught:
        validate_upload(
            content=b"a" * 33,
            filename="notes.txt",
            declared_media_type="text/plain",
            policy=UploadValidationPolicy(max_bytes=32),
        )

    assert caught.value.code == "ATTACHMENT_TOO_LARGE"
    assert caught.value.http_status == 413


def test_office_archive_rejects_traversal_entry() -> None:
    archive = _office_archive(
        document_entry="word/document.xml",
        extra={"../outside.txt": b"escape"},
    )

    with pytest.raises(UploadValidationError) as caught:
        validate_upload(
            content=archive,
            filename="attempt.docx",
            declared_media_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        )

    assert caught.value.code == "UNSAFE_ARCHIVE_PATH"


def test_office_archive_rejects_excessive_compression_ratio() -> None:
    archive = _office_archive(
        document_entry="ppt/presentation.xml",
        extra={"ppt/slides/slide1.xml": b"0" * 100_000},
    )

    with pytest.raises(UploadValidationError) as caught:
        validate_upload(
            content=archive,
            filename="slides.pptx",
            declared_media_type=(
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ),
            policy=UploadValidationPolicy(max_archive_compression_ratio=5),
        )

    assert caught.value.code == "ARCHIVE_RATIO_EXCEEDED"


def test_legacy_office_is_explicitly_unavailable_without_converter() -> None:
    with pytest.raises(UploadValidationError) as caught:
        validate_upload(
            content=_legacy_office_cfb("WordDocument"),
            filename="attempt.doc",
            declared_media_type="application/msword",
        )

    assert caught.value.code == "LEGACY_OFFICE_CONVERTER_UNAVAILABLE"
    assert caught.value.http_status == 415


def test_legacy_office_magic_type_and_active_content_are_validated() -> None:
    validated = validate_upload(
        content=_legacy_office_cfb("WordDocument"),
        filename="attempt.doc",
        declared_media_type="application/msword",
        policy=UploadValidationPolicy(allow_legacy_office=True),
    )
    assert validated.extension == ".doc"
    assert validated.detected_media_type == "application/msword"
    assert validated.metadata["legacy_office_requires_conversion"] is True

    with pytest.raises(UploadValidationError) as mismatched:
        validate_upload(
            content=_legacy_office_cfb("PowerPoint Document"),
            filename="attempt.doc",
            declared_media_type="application/msword",
            policy=UploadValidationPolicy(allow_legacy_office=True),
        )
    assert mismatched.value.code == "FILE_TYPE_MISMATCH"

    with pytest.raises(UploadValidationError) as active:
        validate_upload(
            content=_legacy_office_cfb("WordDocument", "VBA"),
            filename="attempt.doc",
            declared_media_type="application/msword",
            policy=UploadValidationPolicy(allow_legacy_office=True),
        )
    assert active.value.code == "ACTIVE_CONTENT_REJECTED"
