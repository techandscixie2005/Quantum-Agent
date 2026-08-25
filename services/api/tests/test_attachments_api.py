from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from quantum_agent.api.attachments import router
from quantum_agent.auth import hash_session_token, issue_opaque_session_token
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    Base,
    Course,
    CourseMembership,
    CourseRole,
    CurriculumEdition,
    DocumentParseRun,
    MembershipStatus,
    MultimodalExtractionStatus,
    SystemRole,
    User,
    UserSession,
    UserStatus,
)
from quantum_agent.multimodal.documents import DocumentIntelligenceService
from quantum_agent.multimodal.perception import MultimodalPerceptionService
from quantum_agent.multimodal.runtime import AttachmentRuntime
from quantum_agent.multimodal.security import UploadValidationPolicy
from quantum_agent.multimodal.storage import LocalAttachmentStorage

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class LowConfidenceVision:
    async def transcribe(
        self,
        *,
        image_bytes: bytes,
        mime_type: str = "image/png",
        instruction: str,
    ) -> str:
        assert image_bytes == PNG
        assert mime_type == "image/png"
        assert "Never correct" in instruction
        return json.dumps(
            {
                "detected_text": "H|psi> = E|psi>",
                "equations": [
                    {
                        "source_text": "H|psi> = E|psi>",
                        "latex": "H|\\psi\\rangle=E|\\psi\\rangle",
                        "confidence": 0.62,
                        "bounding_boxes": [],
                        "ambiguity_ids": ["symbol-1"],
                    }
                ],
                "derivation_steps": [
                    {
                        "ordinal": 1,
                        "source_text": "H|psi> = E|psi>",
                        "latex": "H|\\psi\\rangle=E|\\psi\\rangle",
                        "confidence": 0.62,
                        "bounding_boxes": [],
                        "ambiguity_ids": ["symbol-1"],
                    }
                ],
                "diagram_interpretation": None,
                "plot_axes": [],
                "plot_interpretation": None,
                "figure_description": None,
                "confidence": 0.62,
                "bounding_boxes": [],
                "ambiguities": [
                    {
                        "ambiguity_id": "symbol-1",
                        "field_path": "derivation_steps[0].latex",
                        "reason": "The handwritten state symbol is faint.",
                        "candidates": [
                            {"value": "psi", "confidence": 0.62},
                            {"value": "phi", "confidence": 0.31},
                        ],
                        "bounding_boxes": [],
                        "requires_confirmation": True,
                    }
                ],
            }
        )


class ApiSeed:
    def __init__(
        self,
        *,
        course_id: UUID,
        edition_id: UUID,
        owner_token: str,
        other_token: str,
    ) -> None:
        self.course_id = course_id
        self.edition_id = edition_id
        self.owner_token = owner_token
        self.other_token = other_token


@pytest.fixture
async def attachment_database(
    tmp_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'attachments.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed(session: AsyncSession) -> ApiSeed:
    now = datetime.now(UTC)
    course = Course(code=f"MM-{uuid4()}", title="Quantum Physics")
    owner = User(
        email=f"owner-{uuid4()}@example.edu",
        display_name="Owner",
        system_role=SystemRole.USER,
        status=UserStatus.ACTIVE,
    )
    other = User(
        email=f"other-{uuid4()}@example.edu",
        display_name="Other student",
        system_role=SystemRole.USER,
        status=UserStatus.ACTIVE,
    )
    session.add_all([course, owner, other])
    await session.flush()
    edition = CurriculumEdition(
        course_id=course.id,
        edition_key="2026",
        title="Quantum Physics 2026",
    )
    session.add(edition)
    await session.flush()
    owner_token = issue_opaque_session_token()
    other_token = issue_opaque_session_token()
    session.add_all(
        [
            UserSession(
                user_id=owner.id,
                session_token_sha256=hash_session_token(owner_token),
                expires_at=now + timedelta(hours=1),
            ),
            UserSession(
                user_id=other.id,
                session_token_sha256=hash_session_token(other_token),
                expires_at=now + timedelta(hours=1),
            ),
            CourseMembership(
                course_id=course.id,
                user_id=owner.id,
                role=CourseRole.STUDENT,
                status=MembershipStatus.ACTIVE,
                joined_at=now,
            ),
            CourseMembership(
                course_id=course.id,
                user_id=other.id,
                role=CourseRole.STUDENT,
                status=MembershipStatus.ACTIVE,
                joined_at=now,
            ),
        ]
    )
    await session.commit()
    return ApiSeed(
        course_id=course.id,
        edition_id=edition.id,
        owner_token=owner_token,
        other_token=other_token,
    )


@pytest.mark.asyncio
async def test_upload_is_idempotent_actor_scoped_and_requires_explicit_confirmation(
    attachment_database: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    async with attachment_database() as session:
        seeded = await _seed(session)

    app = FastAPI()
    app.include_router(router)
    app.state.attachment_runtime = AttachmentRuntime(
        storage=LocalAttachmentStorage(tmp_path / "stored-attachments"),
        validation_policy=UploadValidationPolicy(),
        perception=MultimodalPerceptionService(
            vision_gateway=LowConfidenceVision(),
            model_name="qwen3.8-chat",
        ),
        documents=DocumentIntelligenceService(),
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with attachment_database() as session:
            yield session

    app.dependency_overrides[session_dependency] = override_session
    base = f"/api/v1/courses/{seeded.course_id}/editions/{seeded.edition_id}/attachments"
    owner_headers = {"Authorization": f"Bearer {seeded.owner_token}"}
    other_headers = {"Authorization": f"Bearer {seeded.other_token}"}
    upload = {"file": ("derivation.png", PNG, "image/png")}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(base, headers=owner_headers, files=upload)
        replayed = await client.post(base, headers=owner_headers, files=upload)
        attachment_id = created.json()["id"]
        cross_user = await client.get(f"{base}/{attachment_id}", headers=other_headers)
        confirmed = await client.post(
            f"{base}/{attachment_id}/confirm",
            headers=owner_headers,
            json={
                "extraction_id": created.json()["extraction"]["id"],
                "decision": "accept",
                "ambiguity_resolutions": {"symbol-1": "The symbol is psi."},
            },
        )
        duplicate_confirmation = await client.post(
            f"{base}/{attachment_id}/confirm",
            headers=owner_headers,
            json={
                "extraction_id": created.json()["extraction"]["id"],
                "decision": "accept",
            },
        )
        listed = await client.get(base, headers=owner_headers)
        deleted = await client.delete(f"{base}/{attachment_id}", headers=owner_headers)
        after_delete = await client.get(f"{base}/{attachment_id}", headers=owner_headers)

    assert created.status_code == 201
    assert created.json()["extraction"]["status"] == "needs_confirmation"
    assert created.json()["extraction"]["requires_confirmation"] is True
    assert (
        created.json()["extraction"]["evidence"]["derivation_steps"][0]["latex"]
        == "H|\\psi\\rangle=E|\\psi\\rangle"
    )
    assert replayed.status_code == 200
    assert replayed.json()["id"] == attachment_id
    assert replayed.json()["idempotent_replay"] is True
    assert cross_user.status_code == 404
    assert confirmed.status_code == 200
    assert confirmed.json()["extraction"]["status"] == "confirmed"
    assert confirmed.json()["extraction"]["requires_confirmation"] is False
    assert confirmed.json()["extraction"]["confirmation"]["original_evidence_preserved"] is True
    assert duplicate_confirmation.status_code == 409
    assert [item["id"] for item in listed.json()] == [attachment_id]
    assert deleted.status_code == 204
    assert after_delete.status_code == 404


@pytest.mark.asyncio
async def test_native_document_upload_persists_parse_provenance(
    attachment_database: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    async with attachment_database() as session:
        seeded = await _seed(session)

    app = FastAPI()
    app.include_router(router)
    app.state.attachment_runtime = AttachmentRuntime(
        storage=LocalAttachmentStorage(tmp_path / "document-attachments"),
        validation_policy=UploadValidationPolicy(),
        perception=MultimodalPerceptionService(vision_gateway=None),
        documents=DocumentIntelligenceService(),
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with attachment_database() as session:
            yield session

    app.dependency_overrides[session_dependency] = override_session
    base = f"/api/v1/courses/{seeded.course_id}/editions/{seeded.edition_id}/attachments"
    headers = {"Authorization": f"Bearer {seeded.owner_token}"}
    source = b"# Spin\n\nThe prediction is recorded before the experiment.\n"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            base,
            headers=headers,
            files={"file": ("prediction.md", source, "text/markdown")},
        )

    assert response.status_code == 201
    assert response.json()["extraction"]["status"] == "succeeded"
    async with attachment_database() as session:
        parse_run = await session.scalar(select(DocumentParseRun))
    assert parse_run is not None
    assert parse_run.status.value == "succeeded"
    assert parse_run.provenance_json["content_sha256"] == response.json()["sha256"]
    assert parse_run.output_json["units"][0]["locator"]["line_start"] == 1
    assert parse_run.output_json["original_file_reference"].startswith("attachment:")
    assert response.json()["extraction"]["status"] == MultimodalExtractionStatus.SUCCEEDED
