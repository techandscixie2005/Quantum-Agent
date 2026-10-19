"""Seed a dedicated synthetic integration DB; never use a classroom database.

Published/approved rows below are FIXTURE STATUS to exercise visibility policy,
not an actual teacher review, approval or classroom observation.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

from quantum_agent.classroom import provision_classroom_access
from quantum_agent.db_models import (
    AgentTrace,
    ChunkExtractionStatus,
    Course,
    CourseRole,
    CourseStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    DocumentChunk,
    DocumentPublication,
    DocumentStatus,
    DocumentType,
    DocumentVersionStatus,
    Evidence,
    EvidenceStatus,
    LearningEvidence,
    LocatorType,
    PublicationStatus,
    SourceAuthority,
    SourceDocument,
    SourceDocumentVersion,
    SourceRole,
    TeachingConversation,
    TeachingConversationStatus,
    TeachingMode,
    TeachingReview,
    TeachingTurn,
)
from quantum_agent.knowledge.barrier_scope import BarrierSourceReview
from quantum_agent.science import ScientificToolbox
from quantum_agent.science.models import RectangularBarrierRequest
from quantum_agent.teaching.course_packages import FINITE_BARRIERS
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def require_fixture_database(url: str) -> None:
    if url.startswith("sqlite+aiosqlite:"):
        if "test-results/backend-live" not in url.replace("\\", "/"):
            raise ValueError("SQLite integration DB must be inside test-results/backend-live")
    elif "backend_live" not in urlparse(url).path:
        raise ValueError("PostgreSQL integration database name must contain backend_live")


async def seed(url: str) -> dict[str, object]:
    require_fixture_database(url)
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now, run_id = datetime.now(UTC), uuid4().hex[:12]
    actors: dict[str, list[dict[str, object]]] = {"student": [], "teacher": [], "ta": []}
    source_reviews: list[dict[str, object]] = []
    async with factory() as session:
        course = Course(
            code=f"BACKEND-LIVE-{run_id}",
            title="合成集成测试课程 · 非真实课堂",
            status=CourseStatus.ACTIVE,
            description="Synthetic fixture. No actual teacher approval or class outcomes.",
        )
        session.add(course)
        await session.flush()
        edition = CurriculumEdition(
            course_id=course.id,
            edition_key=run_id,
            title="Synthetic backend/browser fixture v1",
            status=CurriculumEditionStatus.PUBLISHED,
            published_at=now,
        )
        session.add(edition)
        await session.flush()
        for role_name, role in (
            ("student", CourseRole.STUDENT),
            ("teacher", CourseRole.TEACHER),
            ("ta", CourseRole.TA),
        ):
            for index in range(12):
                actor = await provision_classroom_access(
                    session,
                    email=f"{role_name}-{index}-{run_id}@synthetic.example.invalid",
                    display_name=f"SYNTHETIC {role_name} {index}",
                    course_id=course.id,
                    role=role,
                )
                request = RectangularBarrierRequest(
                    energy_eV=4,
                    barrier_height_eV=12,
                    barrier_width_m=0.12e-9,
                    particle_mass_kg=9.1093837015e-31,
                )
                value = ScientificToolbox().verify(request).metrics["T"]
                ready = TeachingConversation(
                    course_id=course.id,
                    curriculum_edition_id=edition.id,
                    student_user_id=UUID(actor["user_id"]),
                    mode=TeachingMode.LEARN_CONCEPTS,
                    status=TeachingConversationStatus.ACTIVE,
                    last_activity_at=now,
                    title="SYNTHETIC seeded transfer phase; not student achievement",
                    learning_phase_json={
                        "phase": "transfer_required",
                        "aided_transfer_verified": True,
                        "active_transfer_task_id": str(uuid4()),
                        "active_transfer_task_prompt": "Synthetic transfer task fixture.",
                        "course_package": FINITE_BARRIERS.reference().model_dump(mode="json"),
                        "pending_scientific_request": request.model_dump(mode="json"),
                        "transfer_verification": {
                            "scientific_request": request.model_dump(mode="json"),
                            "metric_name": "T",
                            "expected_value": value,
                        },
                    },
                )
                session.add(ready)
                await session.flush()
                actors[role_name].append({**actor, "solo_ready_conversation_id": str(ready.id)})
        publisher_id = UUID(str(actors["teacher"][0]["user_id"]))
        document = SourceDocument(
            course_id=course.id,
            curriculum_edition_id=edition.id,
            logical_key=f"synthetic-fixture-{run_id}",
            title="SYNTHETIC fixture finite barrier notes",
            source_filename="SYNTHETIC-fixture.txt",
            source_path="fixture-only/SYNTHETIC-fixture.txt",
            media_type="text/plain",
            document_type=DocumentType.NOTES,
            authority=SourceAuthority.COURSE_PRIMARY,
            source_role=SourceRole.LECTURE,
            status=DocumentStatus.PUBLISHED,
            bibliographic_json={"fixture_only": True, "actual_teacher_approval": False},
        )
        session.add(document)
        await session.flush()
        passages = [
            "SYNTHETIC TEST FIXTURE. 量子隧穿 finite barrier tunnelling transmission: "
            "For 0<E<V0 the forbidden region has nonzero exponential solutions; "
            "transmission is the ratio of probability currents (概率流).",
            "SYNTHETIC TEST FIXTURE. 量子隧穿 finite barrier tunnelling transmission: "
            "For fixed mass, energy and height with 0<E<V0, increasing width reduces transmission; "
            "probability current is 概率流.",
        ]
        version = SourceDocumentVersion(
            document_id=document.id,
            version_number=1,
            source_file_sha256=hashlib.sha256("\n".join(passages).encode()).hexdigest(),
            byte_size=len("\n".join(passages).encode()),
            immutable_source_path=document.source_path,
            parser_name="synthetic-integration-seeder",
            parser_version="1",
            status=DocumentVersionStatus.PUBLISHED,
            source_metadata_json={"fixture_only": True, "actual_teacher_approval": False},
        )
        session.add(version)
        await session.flush()
        for ordinal, passage in enumerate(passages):
            digest = hashlib.sha256(passage.encode()).hexdigest()
            chunk = DocumentChunk(
                document_version_id=version.id,
                ordinal=ordinal,
                locator_type=LocatorType.LINE,
                locator_start=str(ordinal + 1),
                locator_end=str(ordinal + 1),
                content=passage,
                content_sha256=digest,
                search_text=passage,
                extraction_status=ChunkExtractionStatus.APPROVED,
                parser_metadata_json={"fixture_only": True},
            )
            session.add(chunk)
            await session.flush()
            evidence = Evidence(
                source_chunk_id=chunk.id,
                evidence_snippet=passage,
                char_start=0,
                char_end=len(passage),
                evidence_sha256=digest,
                chunk_content_sha256=digest,
                status=EvidenceStatus.GROUNDED,
                locator_json={
                    "locator_type": "text_lines",
                    "line_start": ordinal + 1,
                    "line_end": ordinal + 1,
                },
            )
            session.add(evidence)
            await session.flush()
            source_reviews.append(
                BarrierSourceReview(
                    course_id=course.id,
                    curriculum_edition_id=edition.id,
                    document_version_id=version.id,
                    evidence_id=evidence.id,
                    source_file_sha256=version.source_file_sha256,
                    source_chunk_sha256=digest,
                    evidence_sha256=digest,
                    review_reference="TEST DOUBLE: harness; actual_teacher_approval=false",
                    approved_widths_m=(0.12e-9, 0.18e-9),
                    width_range_m=(0.1e-9, 0.3e-9),
                    energy_range_eV=(3, 4),
                    height_range_eV=(11, 12),
                    potential="V0 inside [0,a]; zero outside",
                    energy="0<E<V0",
                    boundaries="constant mass; psi and derivative continuous; left incidence",
                    formula="exact flux T,R; not thick-barrier approximation",
                ).model_dump(mode="json")
            )
        session.add(
            DocumentPublication(
                course_id=course.id,
                curriculum_edition_id=edition.id,
                document_version_id=version.id,
                status=PublicationStatus.PUBLISHED,
                published_by_user_id=publisher_id,
                published_at=now,
                notes="FIXTURE STATUS ONLY; no real teacher review or approval.",
            )
        )
        await session.commit()
        result: dict[str, object] = {
            "fixture_label": "synthetic-integration-fixture-not-classroom-results",
            "run_id": run_id,
            "course_id": str(course.id),
            "edition_id": str(edition.id),
            "database_mode": "sqlite" if url.startswith("sqlite") else "postgresql",
            "database_url": url,
            "actors": actors,
            "source_reviews": source_reviews,
        }
    await engine.dispose()
    return result


async def snapshot(manifest: dict[str, object], conversation_id: str | None) -> dict[str, object]:
    engine = create_async_engine(str(manifest["database_url"]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        course_id = UUID(str(manifest["course_id"]))
        turns = (
            select(TeachingTurn)
            .join(TeachingConversation)
            .where(
                TeachingConversation.course_id == course_id,
            )
        )
        if conversation_id:
            turns = turns.where(TeachingTurn.conversation_id == UUID(conversation_id))
        rows = (await session.scalars(turns.order_by(TeachingTurn.created_at))).all()
        ids = [row.id for row in rows]
        result: dict[str, object] = {
            "turns": [
                {
                    "id": str(row.id),
                    "conversation_id": str(row.conversation_id),
                    "status": row.status.value,
                    "client_request_id": row.client_request_id,
                    "sequence": row.sequence_number,
                    "hitl_decision_count": len(
                        row.scientific_results_json.get("__hitl_decisions", {})
                    ),
                }
                for row in rows
            ],
            "traces": await session.scalar(
                select(func.count(AgentTrace.id)).where(AgentTrace.teaching_turn_id.in_(ids))
            ),
            "evidence": await session.scalar(
                select(func.count(LearningEvidence.id)).where(
                    LearningEvidence.teaching_turn_id.in_(ids)
                )
            ),
            "reviews": await session.scalar(
                select(func.count(TeachingReview.id)).where(TeachingReview.course_id == course_id)
            ),
            "learning_events": [
                {
                    "turn_id": str(row.teaching_turn_id),
                    "kind": row.kind.value,
                    "observation": row.observation,
                    "payload": row.evidence_json,
                }
                for row in (
                    await session.scalars(
                        select(LearningEvidence)
                        .where(
                            LearningEvidence.teaching_turn_id.in_(ids),
                        )
                        .order_by(LearningEvidence.created_at, LearningEvidence.id)
                    )
                ).all()
            ],
        }
    await engine.dispose()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["seed", "snapshot"])
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--conversation-id")
    args = parser.parse_args()
    if args.command == "seed":
        data = asyncio.run(seed(os.environ["DATABASE_URL"]))
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"seeded": True, "fixture_label": data["fixture_label"]}))
    else:
        print(
            json.dumps(
                asyncio.run(
                    snapshot(
                        json.loads(args.manifest.read_text(encoding="utf-8")),
                        args.conversation_id,
                    )
                )
            )
        )
