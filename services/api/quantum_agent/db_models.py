"""PostgreSQL-first, auditable relational model for Phase 1.

PostgreSQL is the authoritative production store for source material,
provenance, review workflow, lexical/vector retrieval, and the Neo4j sync
outbox.  Portable SQLAlchemy variants allow the same invariants to be tested
with SQLite; PostgreSQL-only triggers and views live in the Alembic migration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, synonym
from sqlalchemy.sql.type_api import TypeEngine

EMBEDDING_DIMENSION = 384


def utc_now() -> datetime:
    return datetime.now(UTC)


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

UUID_TYPE = Uuid(as_uuid=True)
JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")
TSVECTOR_TYPE = Text().with_variant(TSVECTOR(), "postgresql")
VECTOR_TYPE = JSON().with_variant(Vector(EMBEDDING_DIMENSION), "postgresql")


def strict_enum[EnumT: StrEnum](enum_class: type[EnumT], name: str) -> TypeEngine[Any]:
    """Persist enum values with a database CHECK on every supported dialect."""

    return SAEnum(
        enum_class,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
        native_enum=False,
        create_constraint=True,
        length=max(len(member.value) for member in enum_class),
    )


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
        nullable=False,
    )


class CourseStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class CurriculumEditionStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class CurriculumUnitType(StrEnum):
    CHAPTER = "chapter"
    SECTION = "section"
    MODULE = "module"
    TOPIC = "topic"


class DocumentType(StrEnum):
    SYLLABUS = "syllabus"
    LECTURE_SLIDES = "lecture_slides"
    TEXTBOOK = "textbook"
    NOTES = "notes"
    EXERCISES = "exercises"
    SOLUTIONS = "solutions"
    KNOWLEDGE_EXPORT = "knowledge_export"
    OTHER = "other"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    QUARANTINED = "quarantined"


class DocumentVersionStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class SourceAuthority(StrEnum):
    COURSE_PRIMARY = "course_primary"
    COURSE_SUPPORTING = "course_supporting"
    REFERENCE = "reference"
    LEGACY = "legacy"


class SourceRole(StrEnum):
    SYLLABUS = "syllabus"
    LECTURE = "lecture"
    TEXTBOOK = "textbook"
    NOTES = "notes"
    EXERCISE = "exercise"
    SOLUTION = "solution"
    KNOWLEDGE_EXPORT = "knowledge_export"
    REFERENCE = "reference"
    OTHER = "other"


class PublicationStatus(StrEnum):
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    ARCHIVED = "archived"


class LocatorType(StrEnum):
    PAGE = "page"
    SLIDE = "slide"
    PARAGRAPH = "paragraph"
    SHEET_ROW = "sheet_row"
    LINE = "line"
    MIXED = "mixed"
    UNLOCATED = "unlocated"


class ChunkExtractionStatus(StrEnum):
    EXTRACTED = "extracted"
    REVIEW_REQUIRED = "review_required"
    OCR_REQUIRED = "ocr_required"
    APPROVED = "approved"
    REJECTED = "rejected"


class EvidenceStatus(StrEnum):
    GROUNDED = "grounded"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class EvidenceType(StrEnum):
    TEXT = "text"
    FORMULA = "formula"
    DERIVATION = "derivation"
    FIGURE = "figure"
    TABLE = "table"
    EXERCISE = "exercise"
    CLAIM = "claim"


class ExtractionRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CandidateStatus(StrEnum):
    REVIEW_REQUIRED = "review_required"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class CandidateOrigin(StrEnum):
    LLM = "llm"
    RULE = "rule"
    IMPORTED = "imported"
    MANUAL = "manual"


class CandidateKind(StrEnum):
    NODE = "node"
    RELATION = "relation"


class GraphNodeType(StrEnum):
    COURSE = "course"
    CHAPTER = "chapter"
    SECTION = "section"
    SOURCE_DOCUMENT = "source_document"
    SOURCE_CHUNK = "source_chunk"
    EVIDENCE = "evidence"
    CONCEPT = "concept"
    PRINCIPLE = "principle"
    PHYSICAL_SYSTEM = "physical_system"
    MATHEMATICAL_OBJECT = "mathematical_object"
    OPERATOR = "operator"
    QUANTUM_STATE = "quantum_state"
    APPROXIMATION = "approximation"
    FORMULA = "formula"
    SYMBOL = "symbol"
    DERIVATION = "derivation"
    EXAMPLE = "example"
    EXERCISE = "exercise"
    MISCONCEPTION = "misconception"
    HINT = "hint"
    EXPERIMENT = "experiment"
    VISUALIZATION = "visualization"
    PROJECT = "project"


class GraphRelationType(StrEnum):
    PART_OF = "part_of"
    PREREQUISITE_OF = "prerequisite_of"
    DEFINES = "defines"
    USES = "uses"
    DEPENDS_ON = "depends_on"
    DERIVES_FROM = "derives_from"
    APPLIES_TO = "applies_to"
    ACTS_ON = "acts_on"
    COMMUTES_WITH = "commutes_with"
    HAS_EIGENSTATE = "has_eigenstate"
    APPROXIMATES = "approximates"
    VALID_UNDER = "valid_under"
    CONTRASTS_WITH = "contrasts_with"
    RELATED_TO = "related_to"
    HAS_MISCONCEPTION = "has_misconception"
    REMEDIATED_BY = "remediated_by"
    VISUALIZED_BY = "visualized_by"
    VERIFIED_BY = "verified_by"
    SUPPORTED_BY = "supported_by"


class EvidenceSupportRole(StrEnum):
    PRIMARY = "primary"
    CORROBORATING = "corroborating"
    QUALIFYING = "qualifying"
    CONTRADICTING = "contradicting"


class ReviewDecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    EDIT = "edit"
    MERGE = "merge"


class GraphSyncOperation(StrEnum):
    UPSERT = "upsert"
    DELETE = "delete"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class SystemRole(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SERVICE = "service"


class UserStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class CourseRole(StrEnum):
    STUDENT = "student"
    TA = "ta"
    TEACHER = "teacher"
    ADMIN = "admin"


class MembershipStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    LEFT = "left"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class TeachingMode(StrEnum):
    LEARN_CONCEPTS = "learn_concepts"
    REVIEW_DERIVATIONS = "review_derivations"
    RUN_EXPERIMENTS = "run_experiments"
    WORK_ON_PROJECTS = "work_on_projects"


class TeachingConversationStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TeachingTaskKind(StrEnum):
    CONCEPT_QUESTION = "concept_question"
    DERIVATION_CHECK = "derivation_check"
    EXERCISE_HELP = "exercise_help"
    EXPERIMENT_HELP = "experiment_help"
    PROJECT_HELP = "project_help"


class TeachingAction(StrEnum):
    EXPLAIN_THEN_CHECK = "explain_then_check"
    ASK_DIAGNOSTIC_QUESTION = "ask_diagnostic_question"
    GIVE_PROGRESSIVE_HINT = "give_progressive_hint"
    CHECK_DERIVATION_STEP = "check_derivation_step"
    PREDICT_THEN_SIMULATE = "predict_then_simulate"
    COACH_PROJECT_MILESTONE = "coach_project_milestone"


class AnswerReleaseLevel(StrEnum):
    QUESTION_ONLY = "question_only"
    HINT = "hint"
    SCAFFOLD = "scaffold"
    FULL_EXPLANATION = "full_explanation"
    FULL_SOLUTION = "full_solution"


class TeachingTurnStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LearningEvidenceKind(StrEnum):
    STUDENT_ATTEMPT = "student_attempt"
    DIAGNOSIS_INFERENCE = "diagnosis_inference"
    CHECK_RESPONSE = "check_response"
    TOOL_OBSERVATION = "tool_observation"
    COMMITMENT = "commitment"
    CONFIDENCE = "confidence"
    TEACH_BACK = "teach_back"
    TRANSFER = "transfer"
    SOLO = "solo"
    SOLO_ATTEMPT = "solo_attempt"
    RETRIEVAL_PRACTICE = "retrieval_practice"


class AttachmentKind(StrEnum):
    IMAGE = "image"
    DOCUMENT = "document"
    TEXT = "text"


class AttachmentStatus(StrEnum):
    QUARANTINED = "quarantined"
    READY = "ready"
    REJECTED = "rejected"
    DELETED = "deleted"


class MultimodalExtractionKind(StrEnum):
    VISION = "vision"
    DOCUMENT = "document"


class MultimodalExtractionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    NEEDS_CONFIRMATION = "needs_confirmation"
    SUCCEEDED = "succeeded"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    FAILED = "failed"


class DocumentParseRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class AuditEventType(StrEnum):
    AUTH_LOGIN = "auth_login"
    AUTH_LOGOUT = "auth_logout"
    MEMBERSHIP_CHANGED = "membership_changed"
    DOCUMENT_INGESTED = "document_ingested"
    DOCUMENT_QUARANTINED = "document_quarantined"
    CANDIDATE_REVIEWED = "candidate_reviewed"
    CANDIDATE_EDITED = "candidate_edited"
    CANDIDATE_MERGED = "candidate_merged"
    GRAPH_SYNCED = "graph_synced"
    SETTINGS_CHANGED = "settings_changed"


class AuditResourceType(StrEnum):
    USER = "user"
    MEMBERSHIP = "membership"
    COURSE = "course"
    CURRICULUM_EDITION = "curriculum_edition"
    DOCUMENT = "document"
    DOCUMENT_VERSION = "document_version"
    NODE_CANDIDATE = "node_candidate"
    RELATION_CANDIDATE = "relation_candidate"
    GRAPH_OUTBOX = "graph_outbox"
    SESSION = "session"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    system_role: Mapped[SystemRole] = mapped_column(
        strict_enum(SystemRole, "system_role"),
        default=SystemRole.USER,
        server_default=SystemRole.USER.value,
        nullable=False,
    )
    status: Mapped[UserStatus] = mapped_column(
        strict_enum(UserStatus, "user_status"),
        default=UserStatus.INVITED,
        server_default=UserStatus.INVITED.value,
        nullable=False,
    )
    identity_issuer: Mapped[str | None] = mapped_column(String(500))
    identity_subject: Mapped[str | None] = mapped_column(String(500))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("length(trim(email)) >= 3", name="email_not_blank"),
        CheckConstraint(
            "(identity_issuer IS NULL AND identity_subject IS NULL) OR "
            "(identity_issuer IS NOT NULL AND identity_subject IS NOT NULL)",
            name="identity_pair_complete",
        ),
        UniqueConstraint(
            "identity_issuer",
            "identity_subject",
            name="uq_users_identity_issuer_subject",
        ),
        Index("uq_users_email_lower", func.lower(email), unique=True),
    )


class Course(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "courses"

    code: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    institution: Mapped[str] = mapped_column(String(300), nullable=False, default="USTC")
    description: Mapped[str | None] = mapped_column(Text)
    default_locale: Mapped[str] = mapped_column(String(35), default="zh-CN", nullable=False)
    status: Mapped[CourseStatus] = mapped_column(
        strict_enum(CourseStatus, "course_status"),
        default=CourseStatus.DRAFT,
        server_default=CourseStatus.DRAFT.value,
        nullable=False,
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("institution", "code", name="uq_courses_institution_code"),
        CheckConstraint("length(trim(code)) > 0", name="code_not_blank"),
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
    )


class CurriculumEdition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curriculum_editions"

    course_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    edition_key: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    academic_year: Mapped[str | None] = mapped_column(String(40))
    term: Mapped[str | None] = mapped_column(String(80))
    ontology_version: Mapped[str] = mapped_column(String(80), nullable=False, default="1.0.0")
    status: Mapped[CurriculumEditionStatus] = mapped_column(
        strict_enum(CurriculumEditionStatus, "curriculum_edition_status"),
        default=CurriculumEditionStatus.DRAFT,
        server_default=CurriculumEditionStatus.DRAFT.value,
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outline_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("course_id", "edition_key", name="uq_curriculum_course_edition_key"),
        UniqueConstraint("id", "course_id", name="uq_curriculum_editions_id_course"),
        CheckConstraint("length(trim(edition_key)) > 0", name="edition_key_not_blank"),
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name="published_has_timestamp",
        ),
        Index("ix_curriculum_editions_course_status", "course_id", "status"),
    )


class CourseMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "course_memberships"

    course_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[CourseRole] = mapped_column(
        strict_enum(CourseRole, "course_role"),
        nullable=False,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        strict_enum(MembershipStatus, "membership_status"),
        default=MembershipStatus.INVITED,
        server_default=MembershipStatus.INVITED.value,
        nullable=False,
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("course_id", "user_id", name="uq_memberships_course_user"),
        CheckConstraint(
            "status <> 'active' OR joined_at IS NOT NULL",
            name="active_has_joined_at",
        ),
        CheckConstraint(
            "status <> 'left' OR ended_at IS NOT NULL",
            name="left_has_ended_at",
        ),
        Index("ix_course_memberships_user_status", "user_id", "status"),
    )


class UserSession(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "user_sessions"

    user_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[SessionStatus] = mapped_column(
        strict_enum(SessionStatus, "session_status"),
        default=SessionStatus.ACTIVE,
        server_default=SessionStatus.ACTIVE.value,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(1000))
    ip_address_hash: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint(
            "length(session_token_sha256) = 64",
            name="token_hash_sha256_length",
        ),
        CheckConstraint("expires_at > created_at", name="expires_after_creation"),
        CheckConstraint(
            "status <> 'revoked' OR revoked_at IS NOT NULL",
            name="revoked_has_timestamp",
        ),
        CheckConstraint(
            "ip_address_hash IS NULL OR length(ip_address_hash) = 64",
            name="ip_hash_sha256_length",
        ),
        Index("ix_user_sessions_user_status_expires", "user_id", "status", "expires_at"),
    )


class UserAttachment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable student upload, isolated from teacher-published course sources."""

    __tablename__ = "user_attachments"

    course_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    curriculum_edition_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    owner_user_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[AttachmentKind] = mapped_column(
        strict_enum(AttachmentKind, "attachment_kind"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    detected_media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AttachmentStatus] = mapped_column(
        strict_enum(AttachmentStatus, "attachment_status"),
        default=AttachmentStatus.QUARANTINED,
        server_default=AttachmentStatus.QUARANTINED.value,
        nullable=False,
    )
    validation_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    rejection_code: Mapped[str | None] = mapped_column(String(160))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_user_attachments_edition_course",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "course_id",
            "curriculum_edition_id",
            "owner_user_id",
            "content_sha256",
            name="uq_user_attachments_owner_scope_hash",
        ),
        UniqueConstraint(
            "id",
            "course_id",
            "curriculum_edition_id",
            "owner_user_id",
            name="uq_user_attachments_id_scope_owner",
        ),
        CheckConstraint("length(trim(original_filename)) > 0", name="filename_not_blank"),
        CheckConstraint("byte_size > 0", name="byte_size_positive"),
        CheckConstraint("length(content_sha256) = 64", name="content_hash_sha256_length"),
        CheckConstraint(
            "status NOT IN ('ready', 'quarantined') OR storage_key IS NOT NULL",
            name="stored_status_has_key",
        ),
        CheckConstraint(
            "status <> 'rejected' OR rejection_code IS NOT NULL",
            name="rejected_has_code",
        ),
        CheckConstraint(
            "status <> 'deleted' OR deleted_at IS NOT NULL",
            name="deleted_has_timestamp",
        ),
        Index(
            "ix_user_attachments_owner_scope_created",
            "owner_user_id",
            "course_id",
            "curriculum_edition_id",
            "created_at",
        ),
        Index("ix_user_attachments_scope_status", "course_id", "curriculum_edition_id", "status"),
    )


class MultimodalExtraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Validated perception output for one student attachment."""

    __tablename__ = "multimodal_extractions"

    attachment_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    course_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    curriculum_edition_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    owner_user_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    kind: Mapped[MultimodalExtractionKind] = mapped_column(
        strict_enum(MultimodalExtractionKind, "multimodal_extraction_kind"),
        nullable=False,
    )
    pipeline_name: Mapped[str] = mapped_column(String(200), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(100), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[MultimodalExtractionStatus] = mapped_column(
        strict_enum(MultimodalExtractionStatus, "multimodal_extraction_status"),
        default=MultimodalExtractionStatus.PENDING,
        server_default=MultimodalExtractionStatus.PENDING.value,
        nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    raw_output_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    ambiguities_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    requires_confirmation: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    failure_code: Mapped[str | None] = mapped_column(String(160))

    __table_args__ = (
        ForeignKeyConstraint(
            ["attachment_id", "course_id", "curriculum_edition_id", "owner_user_id"],
            [
                "user_attachments.id",
                "user_attachments.course_id",
                "user_attachments.curriculum_edition_id",
                "user_attachments.owner_user_id",
            ],
            name="fk_multimodal_extractions_attachment_scope_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "attachment_id",
            "pipeline_name",
            "pipeline_version",
            name="uq_multimodal_extractions_attachment_pipeline",
        ),
        UniqueConstraint(
            "id",
            "attachment_id",
            name="uq_multimodal_extractions_id_attachment",
        ),
        CheckConstraint("length(trim(pipeline_name)) > 0", name="pipeline_name_not_blank"),
        CheckConstraint("length(trim(pipeline_version)) > 0", name="pipeline_version_not_blank"),
        CheckConstraint("length(trim(extraction_method)) > 0", name="method_not_blank"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="confidence_unit_interval",
        ),
        CheckConstraint(
            "status <> 'needs_confirmation' OR requires_confirmation",
            name="confirmation_status_requires_confirmation",
        ),
        CheckConstraint(
            "status <> 'confirmed' OR "
            "(confirmed_by_user_id IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="confirmed_has_actor_and_timestamp",
        ),
        CheckConstraint(
            "status <> 'failed' OR failure_code IS NOT NULL",
            name="failed_has_code",
        ),
        Index("ix_multimodal_extractions_attachment_status", "attachment_id", "status"),
        Index(
            "ix_multimodal_extractions_owner_created",
            "owner_user_id",
            "course_id",
            "created_at",
        ),
    )


class DocumentParseRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Auditable native/MinerU/OCR fallback run for a student document."""

    __tablename__ = "document_parse_runs"

    attachment_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    extraction_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    course_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    curriculum_edition_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    owner_user_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    pipeline_name: Mapped[str] = mapped_column(String(200), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(100), nullable=False)
    selected_method: Mapped[str] = mapped_column(String(100), nullable=False)
    parser_name: Mapped[str] = mapped_column(String(200), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[DocumentParseRunStatus] = mapped_column(
        strict_enum(DocumentParseRunStatus, "document_parse_run_status"),
        default=DocumentParseRunStatus.PENDING,
        server_default=DocumentParseRunStatus.PENDING.value,
        nullable=False,
    )
    page_count: Mapped[int | None] = mapped_column(Integer)
    slide_count: Mapped[int | None] = mapped_column(Integer)
    fallback_chain_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    output_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(160))

    __table_args__ = (
        ForeignKeyConstraint(
            ["attachment_id", "course_id", "curriculum_edition_id", "owner_user_id"],
            [
                "user_attachments.id",
                "user_attachments.course_id",
                "user_attachments.curriculum_edition_id",
                "user_attachments.owner_user_id",
            ],
            name="fk_document_parse_runs_attachment_scope_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["extraction_id", "attachment_id"],
            ["multimodal_extractions.id", "multimodal_extractions.attachment_id"],
            name="fk_document_parse_runs_extraction_attachment",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "attachment_id",
            "pipeline_name",
            "pipeline_version",
            name="uq_document_parse_runs_attachment_pipeline",
        ),
        CheckConstraint("length(trim(pipeline_name)) > 0", name="pipeline_name_not_blank"),
        CheckConstraint("length(trim(pipeline_version)) > 0", name="pipeline_version_not_blank"),
        CheckConstraint("length(trim(selected_method)) > 0", name="method_not_blank"),
        CheckConstraint("page_count IS NULL OR page_count >= 0", name="page_count_nonnegative"),
        CheckConstraint("slide_count IS NULL OR slide_count >= 0", name="slide_count_nonnegative"),
        CheckConstraint(
            "page_count IS NULL OR slide_count IS NULL",
            name="page_or_slide_count_not_both",
        ),
        CheckConstraint(
            "status NOT IN ('succeeded', 'partial', 'failed') OR completed_at IS NOT NULL",
            name="terminal_has_completed_at",
        ),
        CheckConstraint(
            "status <> 'failed' OR error_code IS NOT NULL",
            name="failed_has_code",
        ),
        Index("ix_document_parse_runs_attachment_created", "attachment_id", "created_at"),
        Index("ix_document_parse_runs_scope_status", "course_id", "status", "created_at"),
    )


class SourceDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_documents"

    course_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    curriculum_edition_id: Mapped[UUID | None] = mapped_column(UUID_TYPE)
    logical_key: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        strict_enum(DocumentType, "document_type"),
        nullable=False,
    )
    authority: Mapped[SourceAuthority] = mapped_column(
        strict_enum(SourceAuthority, "source_authority"),
        default=SourceAuthority.COURSE_SUPPORTING,
        server_default=SourceAuthority.COURSE_SUPPORTING.value,
        nullable=False,
    )
    source_role: Mapped[SourceRole] = mapped_column(
        strict_enum(SourceRole, "source_role"),
        default=SourceRole.OTHER,
        server_default=SourceRole.OTHER.value,
        nullable=False,
    )
    authority_priority: Mapped[int] = mapped_column(
        Integer,
        default=50,
        server_default="50",
        nullable=False,
    )
    language: Mapped[str | None] = mapped_column(String(35))
    status: Mapped[DocumentStatus] = mapped_column(
        strict_enum(DocumentStatus, "document_status"),
        default=DocumentStatus.UPLOADED,
        server_default=DocumentStatus.UPLOADED.value,
        nullable=False,
    )
    bibliographic_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_source_documents_edition_course",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("course_id", "logical_key", name="uq_documents_course_logical_key"),
        CheckConstraint("length(trim(logical_key)) > 0", name="logical_key_not_blank"),
        CheckConstraint("length(trim(source_filename)) > 0", name="filename_not_blank"),
        CheckConstraint(
            "authority_priority >= 0 AND authority_priority <= 100",
            name="authority_priority_range",
        ),
        Index("ix_source_documents_course_status", "course_id", "status"),
        Index("ix_source_documents_edition_type", "curriculum_edition_id", "document_type"),
        Index(
            "ix_source_documents_authority_priority",
            "course_id",
            "authority",
            "source_role",
            "authority_priority",
        ),
    )


class SourceDocumentVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "source_document_versions"

    document_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    immutable_source_path: Mapped[str] = mapped_column(Text, nullable=False)
    parser_name: Mapped[str | None] = mapped_column(String(200))
    parser_version: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[DocumentVersionStatus] = mapped_column(
        strict_enum(DocumentVersionStatus, "document_version_status"),
        default=DocumentVersionStatus.UPLOADED,
        server_default=DocumentVersionStatus.UPLOADED.value,
        nullable=False,
    )
    parse_diagnostics_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    source_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    ingested_by_user_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
        UniqueConstraint(
            "document_id",
            "source_file_sha256",
            "parser_name",
            name="uq_document_versions_parser_file_hash",
        ),
        CheckConstraint("version_number > 0", name="version_number_positive"),
        CheckConstraint("byte_size >= 0", name="byte_size_nonnegative"),
        CheckConstraint("length(source_file_sha256) = 64", name="source_hash_sha256_length"),
        Index("ix_document_versions_status_created", "status", "created_at"),
    )


class DocumentPublication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_publications"

    course_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    curriculum_edition_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("source_document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[PublicationStatus] = mapped_column(
        strict_enum(PublicationStatus, "publication_status"),
        default=PublicationStatus.PUBLISHED,
        server_default=PublicationStatus.PUBLISHED.value,
        nullable=False,
    )
    published_by_user_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, default=50, server_default="50", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unpublished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("course_id", "document_version_id", name="uq_publication_course_version"),
        CheckConstraint("priority >= 0 AND priority <= 100", name="priority_range"),
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name="published_has_timestamp",
        ),
        CheckConstraint(
            "status <> 'unpublished' OR unpublished_at IS NOT NULL",
            name="unpublished_has_timestamp",
        ),
        Index(
            "ix_document_publications_student_lookup",
            "course_id",
            "curriculum_edition_id",
            "status",
            "priority",
        ),
    )


class CurriculumOutlineSource(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "curriculum_outline_sources"

    curriculum_edition_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("curriculum_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_version_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("source_document_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    extracted_outline_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "curriculum_edition_id",
            "document_version_id",
            name="uq_outline_sources_edition_version",
        ),
        Index("ix_outline_sources_edition_primary", "curriculum_edition_id", "is_primary"),
    )


class ExtractionRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "extraction_runs"

    document_version_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("source_document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    pipeline_name: Mapped[str] = mapped_column(String(200), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(100), nullable=False)
    ontology_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(200))
    configuration_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ExtractionRunStatus] = mapped_column(
        strict_enum(ExtractionRunStatus, "extraction_run_status"),
        default=ExtractionRunStatus.PENDING,
        server_default=ExtractionRunStatus.PENDING.value,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    error_summary: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("length(configuration_sha256) = 64", name="config_hash_sha256_length"),
        CheckConstraint(
            "status NOT IN ('succeeded', 'failed', 'cancelled') OR completed_at IS NOT NULL",
            name="terminal_has_completed_at",
        ),
        CheckConstraint(
            "started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at",
            name="completion_after_start",
        ),
        Index("ix_extraction_runs_document_status", "document_version_id", "status"),
    )


class DocumentChunk(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "document_chunks"

    document_version_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("source_document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    extraction_run_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("extraction_runs.id", ondelete="SET NULL"),
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    locator_type: Mapped[LocatorType] = mapped_column(
        strict_enum(LocatorType, "locator_type"),
        nullable=False,
    )
    locator_start: Mapped[str | None] = mapped_column(String(160))
    locator_end: Mapped[str | None] = mapped_column(String(160))
    physical_page: Mapped[int | None] = mapped_column(Integer)
    printed_page_label: Mapped[str | None] = mapped_column(String(100))
    slide_number: Mapped[int | None] = mapped_column(Integer)
    paragraph_start: Mapped[int | None] = mapped_column(Integer)
    paragraph_end: Mapped[int | None] = mapped_column(Integer)
    section_path: Mapped[list[str]] = mapped_column(
        JSON_TYPE,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    bounding_boxes_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str | None] = mapped_column(Text)
    evidence_snippet: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR_TYPE)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR_TYPE)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer)
    embedding_model: Mapped[str | None] = mapped_column(String(300))
    extraction_quality: Mapped[float | None] = mapped_column(Float)
    extraction_status: Mapped[ChunkExtractionStatus] = mapped_column(
        strict_enum(ChunkExtractionStatus, "chunk_extraction_status"),
        default=ChunkExtractionStatus.EXTRACTED,
        server_default=ChunkExtractionStatus.EXTRACTED.value,
        nullable=False,
    )
    parser_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )

    exact_text = synonym("content")
    page_label = synonym("printed_page_label")
    checksum = synonym("content_sha256")

    __table_args__ = (
        UniqueConstraint("document_version_id", "ordinal", name="uq_chunks_version_ordinal"),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint(
            "physical_page IS NULL OR physical_page > 0", name="physical_page_positive"
        ),
        CheckConstraint("slide_number IS NULL OR slide_number > 0", name="slide_number_positive"),
        CheckConstraint(
            "paragraph_start IS NULL OR paragraph_start >= 0",
            name="paragraph_start_nonnegative",
        ),
        CheckConstraint(
            "paragraph_end IS NULL OR paragraph_end >= 0",
            name="paragraph_end_nonnegative",
        ),
        CheckConstraint(
            "paragraph_start IS NULL OR paragraph_end IS NULL OR paragraph_end >= paragraph_start",
            name="paragraph_range_ordered",
        ),
        CheckConstraint("length(content_sha256) = 64", name="content_hash_sha256_length"),
        CheckConstraint("length(content) > 0", name="content_not_empty"),
        CheckConstraint(
            "extraction_quality IS NULL OR "
            "(extraction_quality >= 0.0 AND extraction_quality <= 1.0)",
            name="extraction_quality_unit_interval",
        ),
        CheckConstraint(
            "(embedding IS NULL AND embedding_dimension IS NULL) OR "
            f"(embedding IS NOT NULL AND embedding_dimension = {EMBEDDING_DIMENSION})",
            name="embedding_fixed_dimension",
        ),
        Index(
            "ix_document_chunks_version_locator", "document_version_id", "locator_type", "ordinal"
        ),
        Index("ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )


class Evidence(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence"

    source_chunk_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_type: Mapped[EvidenceType] = mapped_column(
        strict_enum(EvidenceType, "evidence_type"),
        default=EvidenceType.TEXT,
        server_default=EvidenceType.TEXT.value,
        nullable=False,
    )
    evidence_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[EvidenceStatus] = mapped_column(
        strict_enum(EvidenceStatus, "evidence_status"),
        default=EvidenceStatus.GROUNDED,
        server_default=EvidenceStatus.GROUNDED.value,
        nullable=False,
    )
    locator_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )

    exact_quote = synonym("evidence_snippet")
    checksum = synonym("evidence_sha256")

    __table_args__ = (
        UniqueConstraint(
            "source_chunk_id",
            "char_start",
            "char_end",
            "evidence_sha256",
            name="uq_evidence_chunk_span_hash",
        ),
        CheckConstraint("char_start >= 0", name="char_start_nonnegative"),
        CheckConstraint("char_end > char_start", name="char_range_nonempty"),
        CheckConstraint("length(trim(evidence_snippet)) > 0", name="snippet_not_blank"),
        CheckConstraint("length(evidence_sha256) = 64", name="evidence_hash_sha256_length"),
        CheckConstraint("length(chunk_content_sha256) = 64", name="chunk_hash_sha256_length"),
        Index("ix_evidence_chunk_status", "source_chunk_id", "status"),
    )


class CurriculumUnit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curriculum_units"

    curriculum_edition_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("curriculum_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_unit_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("curriculum_units.id", ondelete="CASCADE"),
    )
    unit_type: Mapped[CurriculumUnitType] = mapped_column(
        strict_enum(CurriculumUnitType, "curriculum_unit_type"),
        nullable=False,
    )
    canonical_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(300))
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_evidence_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("evidence.id", ondelete="SET NULL"),
    )

    __table_args__ = (
        UniqueConstraint(
            "curriculum_edition_id",
            "canonical_path",
            name="uq_curriculum_units_edition_path",
        ),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint("parent_unit_id IS NULL OR parent_unit_id <> id", name="parent_not_self"),
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        Index("ix_curriculum_units_parent_ordinal", "parent_unit_id", "ordinal"),
    )


class GraphNodeCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "graph_node_candidates"

    course_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    curriculum_edition_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("curriculum_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    extraction_run_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("extraction_runs.id", ondelete="SET NULL"),
    )
    node_type: Mapped[GraphNodeType] = mapped_column(
        strict_enum(GraphNodeType, "graph_node_type"),
        nullable=False,
    )
    canonical_key: Mapped[str] = mapped_column(String(700), nullable=False)
    label: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    formula_latex: Mapped[str | None] = mapped_column(Text)
    properties_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    origin: Mapped[CandidateOrigin] = mapped_column(
        strict_enum(CandidateOrigin, "candidate_origin"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[CandidateStatus] = mapped_column(
        strict_enum(CandidateStatus, "candidate_status"),
        default=CandidateStatus.REVIEW_REQUIRED,
        server_default=CandidateStatus.REVIEW_REQUIRED.value,
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_node_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_node_candidates.id", ondelete="RESTRICT"),
    )

    __table_args__ = (
        UniqueConstraint(
            "curriculum_edition_id",
            "node_type",
            "canonical_key",
            "revision_number",
            name="uq_node_candidates_identity_revision",
        ),
        CheckConstraint("length(trim(canonical_key)) > 0", name="canonical_key_not_blank"),
        CheckConstraint("length(trim(label)) > 0", name="label_not_blank"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="confidence_unit_interval"),
        CheckConstraint("revision_number > 0", name="revision_number_positive"),
        CheckConstraint(
            "status NOT IN ('approved', 'rejected', 'superseded') OR "
            "(reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="terminal_status_reviewed",
        ),
        CheckConstraint(
            "status <> 'superseded' OR superseded_by_node_candidate_id IS NOT NULL",
            name="superseded_has_successor",
        ),
        CheckConstraint(
            "superseded_by_node_candidate_id IS NULL OR superseded_by_node_candidate_id <> id",
            name="successor_not_self",
        ),
        Index(
            "ix_node_candidates_review_queue",
            "course_id",
            "curriculum_edition_id",
            "status",
            "node_type",
        ),
        Index("ix_node_candidates_canonical_key", "curriculum_edition_id", "canonical_key"),
    )


class GraphRelationCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "graph_relation_candidates"

    course_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    curriculum_edition_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("curriculum_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    extraction_run_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("extraction_runs.id", ondelete="SET NULL"),
    )
    source_node_candidate_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_node_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_candidate_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_node_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[GraphRelationType] = mapped_column(
        strict_enum(GraphRelationType, "graph_relation_type"),
        nullable=False,
    )
    canonical_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    properties_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    origin: Mapped[CandidateOrigin] = mapped_column(
        strict_enum(CandidateOrigin, "candidate_origin"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[CandidateStatus] = mapped_column(
        strict_enum(CandidateStatus, "candidate_status"),
        default=CandidateStatus.REVIEW_REQUIRED,
        server_default=CandidateStatus.REVIEW_REQUIRED.value,
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_relation_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_relation_candidates.id", ondelete="RESTRICT"),
    )

    __table_args__ = (
        UniqueConstraint(
            "curriculum_edition_id",
            "canonical_key",
            "revision_number",
            name="uq_relation_candidates_identity_revision",
        ),
        CheckConstraint(
            "source_node_candidate_id <> target_node_candidate_id", name="endpoints_distinct"
        ),
        CheckConstraint("length(trim(canonical_key)) > 0", name="canonical_key_not_blank"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="confidence_unit_interval"),
        CheckConstraint("revision_number > 0", name="revision_number_positive"),
        CheckConstraint(
            "status NOT IN ('approved', 'rejected', 'superseded') OR "
            "(reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="terminal_status_reviewed",
        ),
        CheckConstraint(
            "status <> 'superseded' OR superseded_by_relation_candidate_id IS NOT NULL",
            name="superseded_has_successor",
        ),
        CheckConstraint(
            "superseded_by_relation_candidate_id IS NULL OR "
            "superseded_by_relation_candidate_id <> id",
            name="successor_not_self",
        ),
        Index(
            "ix_relation_candidates_review_queue",
            "course_id",
            "curriculum_edition_id",
            "status",
            "relation_type",
        ),
        Index(
            "ix_relation_candidates_endpoints",
            "source_node_candidate_id",
            "target_node_candidate_id",
        ),
    )


class NodeCandidateEvidenceSupport(CreatedAtMixin, Base):
    __tablename__ = "node_candidate_evidence_support"

    node_candidate_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_node_candidates.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("evidence.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    support_role: Mapped[EvidenceSupportRole] = mapped_column(
        strict_enum(EvidenceSupportRole, "evidence_support_role"),
        default=EvidenceSupportRole.PRIMARY,
        server_default=EvidenceSupportRole.PRIMARY.value,
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    extraction_span_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="confidence_unit_interval"),
        Index("ix_node_support_evidence", "evidence_id"),
    )


class RelationCandidateEvidenceSupport(CreatedAtMixin, Base):
    __tablename__ = "relation_candidate_evidence_support"

    relation_candidate_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_relation_candidates.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("evidence.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    support_role: Mapped[EvidenceSupportRole] = mapped_column(
        strict_enum(EvidenceSupportRole, "evidence_support_role"),
        default=EvidenceSupportRole.PRIMARY,
        server_default=EvidenceSupportRole.PRIMARY.value,
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    extraction_span_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="confidence_unit_interval"),
        Index("ix_relation_support_evidence", "evidence_id"),
    )


class CandidateRevision(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "candidate_revisions"

    node_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_node_candidates.id", ondelete="CASCADE"),
    )
    relation_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_relation_candidates.id", ondelete="CASCADE"),
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    diff_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    previous_revision_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("candidate_revisions.id", ondelete="RESTRICT"),
    )

    __table_args__ = (
        CheckConstraint(
            "(node_candidate_id IS NOT NULL AND relation_candidate_id IS NULL) OR "
            "(node_candidate_id IS NULL AND relation_candidate_id IS NOT NULL)",
            name="exactly_one_candidate",
        ),
        CheckConstraint("revision_number > 0", name="revision_number_positive"),
        CheckConstraint(
            "previous_revision_id IS NULL OR previous_revision_id <> id",
            name="previous_revision_not_self",
        ),
        UniqueConstraint(
            "node_candidate_id",
            "revision_number",
            name="uq_candidate_revisions_node_number",
        ),
        UniqueConstraint(
            "relation_candidate_id",
            "revision_number",
            name="uq_candidate_revisions_relation_number",
        ),
    )


class ReviewDecision(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "review_decisions"

    node_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_node_candidates.id", ondelete="CASCADE"),
    )
    relation_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_relation_candidates.id", ondelete="CASCADE"),
    )
    candidate_revision_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("candidate_revisions.id", ondelete="SET NULL"),
    )
    decision: Mapped[ReviewDecisionType] = mapped_column(
        strict_enum(ReviewDecisionType, "review_decision_type"),
        nullable=False,
    )
    reviewer_user_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    before_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    after_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)

    __table_args__ = (
        CheckConstraint(
            "(node_candidate_id IS NOT NULL AND relation_candidate_id IS NULL) OR "
            "(node_candidate_id IS NULL AND relation_candidate_id IS NOT NULL)",
            name="exactly_one_candidate",
        ),
        CheckConstraint("length(trim(rationale)) > 0", name="rationale_not_blank"),
        Index("ix_review_decisions_reviewer_created", "reviewer_user_id", "created_at"),
        Index("ix_review_decisions_node", "node_candidate_id", "created_at"),
        Index("ix_review_decisions_relation", "relation_candidate_id", "created_at"),
    )


class CandidateMergeLineage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "candidate_merge_lineage"

    merged_node_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_node_candidates.id", ondelete="RESTRICT"),
    )
    surviving_node_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_node_candidates.id", ondelete="RESTRICT"),
    )
    merged_relation_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_relation_candidates.id", ondelete="RESTRICT"),
    )
    surviving_relation_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_relation_candidates.id", ondelete="RESTRICT"),
    )
    review_decision_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("review_decisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    merged_by_user_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(merged_node_candidate_id IS NOT NULL AND "
            "surviving_node_candidate_id IS NOT NULL AND "
            "merged_relation_candidate_id IS NULL AND "
            "surviving_relation_candidate_id IS NULL) OR "
            "(merged_node_candidate_id IS NULL AND "
            "surviving_node_candidate_id IS NULL AND "
            "merged_relation_candidate_id IS NOT NULL AND "
            "surviving_relation_candidate_id IS NOT NULL)",
            name="same_kind_merge_pair",
        ),
        CheckConstraint(
            "merged_node_candidate_id IS NULL OR "
            "merged_node_candidate_id <> surviving_node_candidate_id",
            name="node_merge_distinct",
        ),
        CheckConstraint(
            "merged_relation_candidate_id IS NULL OR "
            "merged_relation_candidate_id <> surviving_relation_candidate_id",
            name="relation_merge_distinct",
        ),
        CheckConstraint("length(trim(rationale)) > 0", name="rationale_not_blank"),
        UniqueConstraint("merged_node_candidate_id", name="uq_merge_lineage_merged_node"),
        UniqueConstraint("merged_relation_candidate_id", name="uq_merge_lineage_merged_relation"),
    )


class GraphSyncOutbox(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "graph_sync_outbox"

    course_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    curriculum_edition_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("curriculum_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_node_candidates.id", ondelete="CASCADE"),
    )
    relation_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_relation_candidates.id", ondelete="CASCADE"),
    )
    operation: Mapped[GraphSyncOperation] = mapped_column(
        strict_enum(GraphSyncOperation, "graph_sync_operation"),
        nullable=False,
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    review_decision_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("review_decisions.id", ondelete="RESTRICT"),
    )
    idempotency_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    status: Mapped[OutboxStatus] = mapped_column(
        strict_enum(OutboxStatus, "outbox_status"),
        default=OutboxStatus.PENDING,
        server_default=OutboxStatus.PENDING.value,
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "(node_candidate_id IS NOT NULL AND relation_candidate_id IS NULL) OR "
            "(node_candidate_id IS NULL AND relation_candidate_id IS NOT NULL)",
            name="exactly_one_candidate",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name="published_has_timestamp",
        ),
        CheckConstraint(
            "status <> 'processing' OR (locked_at IS NOT NULL AND locked_by IS NOT NULL)",
            name="processing_has_lock",
        ),
        Index("ix_graph_outbox_dispatch", "status", "available_at", "created_at"),
    )


class AuditLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_logs"

    event_type: Mapped[AuditEventType] = mapped_column(
        strict_enum(AuditEventType, "audit_event_type"),
        nullable=False,
    )
    resource_type: Mapped[AuditResourceType] = mapped_column(
        strict_enum(AuditResourceType, "audit_resource_type"),
        nullable=False,
    )
    resource_id: Mapped[UUID | None] = mapped_column(UUID_TYPE)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    actor_session_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("user_sessions.id", ondelete="SET NULL"),
    )
    course_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="SET NULL"),
    )
    request_id: Mapped[UUID | None] = mapped_column(UUID_TYPE)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    context_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    previous_event_sha256: Mapped[str | None] = mapped_column(String(64))
    event_sha256: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint("length(trim(summary)) > 0", name="summary_not_blank"),
        CheckConstraint(
            "previous_event_sha256 IS NULL OR length(previous_event_sha256) = 64",
            name="previous_hash_sha256_length",
        ),
        CheckConstraint(
            "event_sha256 IS NULL OR length(event_sha256) = 64",
            name="event_hash_sha256_length",
        ),
        Index("ix_audit_logs_course_created", "course_id", "created_at"),
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id", "created_at"),
    )


class AnswerPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Backend-enforced release policy for one course edition and teaching mode."""

    __tablename__ = "answer_policies"

    course_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    curriculum_edition_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    mode: Mapped[TeachingMode] = mapped_column(
        strict_enum(TeachingMode, "teaching_mode"),
        nullable=False,
    )
    allow_full_solution: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    minimum_attempts_for_scaffold: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )
    minimum_attempts_for_full_solution: Mapped[int] = mapped_column(
        Integer,
        default=2,
        server_default="2",
        nullable=False,
    )
    max_hint_level: Mapped[int] = mapped_column(
        Integer,
        default=3,
        server_default="3",
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    policy_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_answer_policies_edition_course",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "curriculum_edition_id",
            "mode",
            name="uq_answer_policies_edition_mode",
        ),
        CheckConstraint(
            "minimum_attempts_for_scaffold >= 0",
            name="minimum_attempts_for_scaffold_nonnegative",
        ),
        CheckConstraint(
            "minimum_attempts_for_full_solution >= minimum_attempts_for_scaffold",
            name="full_solution_after_scaffold",
        ),
        CheckConstraint(
            "max_hint_level >= 0 AND max_hint_level <= 10",
            name="max_hint_level_range",
        ),
        Index("ix_answer_policies_scope_active", "course_id", "curriculum_edition_id", "active"),
    )


class TeachingConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A course-scoped student workflow; it is not an autonomous-agent thread."""

    __tablename__ = "teaching_conversations"

    course_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    curriculum_edition_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    student_user_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    mode: Mapped[TeachingMode] = mapped_column(
        strict_enum(TeachingMode, "teaching_conversation_mode"),
        nullable=False,
    )
    status: Mapped[TeachingConversationStatus] = mapped_column(
        strict_enum(TeachingConversationStatus, "teaching_conversation_status"),
        default=TeachingConversationStatus.ACTIVE,
        server_default=TeachingConversationStatus.ACTIVE.value,
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(500))
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_teaching_conversations_edition_course",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "title IS NULL OR length(trim(title)) > 0",
            name="title_not_blank",
        ),
        Index(
            "ix_teaching_conversations_student_activity",
            "student_user_id",
            "course_id",
            "last_activity_at",
        ),
    )


class TeachingTurn(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One immutable-input, auditable execution of the deterministic workflow."""

    __tablename__ = "teaching_turns"

    conversation_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("teaching_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    student_attempt: Mapped[str | None] = mapped_column(Text)
    task_kind: Mapped[TeachingTaskKind | None] = mapped_column(
        strict_enum(TeachingTaskKind, "teaching_task_kind")
    )
    teaching_action: Mapped[TeachingAction | None] = mapped_column(
        strict_enum(TeachingAction, "teaching_action")
    )
    release_level: Mapped[AnswerReleaseLevel | None] = mapped_column(
        strict_enum(AnswerReleaseLevel, "answer_release_level")
    )
    status: Mapped[TeachingTurnStatus] = mapped_column(
        strict_enum(TeachingTurnStatus, "teaching_turn_status"),
        default=TeachingTurnStatus.RUNNING,
        server_default=TeachingTurnStatus.RUNNING.value,
        nullable=False,
    )
    evidence_packet_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    scientific_results_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    validation_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(160))

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "sequence_number",
            name="uq_teaching_turns_conversation_sequence",
        ),
        CheckConstraint("sequence_number > 0", name="sequence_number_positive"),
        CheckConstraint("length(trim(user_message)) > 0", name="user_message_not_blank"),
        CheckConstraint(
            "status <> 'completed' OR (completed_at IS NOT NULL AND response_json IS NOT NULL)",
            name="completed_has_response",
        ),
        CheckConstraint(
            "status <> 'failed' OR (completed_at IS NOT NULL AND failure_code IS NOT NULL)",
            name="failed_has_code",
        ),
        Index("ix_teaching_turns_conversation_created", "conversation_id", "created_at"),
    )


class AgentTrace(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only execution evidence for the fixed state-machine path."""

    __tablename__ = "agent_traces"

    teaching_turn_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("teaching_turns.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    course_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    curriculum_edition_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    student_user_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_version: Mapped[str] = mapped_column(String(80), nullable=False)
    steps_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    policy_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    model_gateway_status: Mapped[str] = mapped_column(String(80), nullable=False)
    citation_validation_status: Mapped[str] = mapped_column(String(80), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_agent_traces_edition_course",
            ondelete="CASCADE",
        ),
        CheckConstraint("length(trim(workflow_version)) > 0", name="workflow_not_blank"),
        Index("ix_agent_traces_course_created", "course_id", "created_at"),
        Index("ix_agent_traces_student_created", "student_user_id", "created_at"),
    )


class LearningEvidence(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Small, observation-based student model signal; never a hidden mastery verdict."""

    __tablename__ = "learning_evidence"

    teaching_turn_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("teaching_turns.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    curriculum_edition_id: Mapped[UUID] = mapped_column(UUID_TYPE, nullable=False)
    student_user_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    concept_candidate_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("graph_node_candidates.id", ondelete="SET NULL"),
    )
    kind: Mapped[LearningEvidenceKind] = mapped_column(
        strict_enum(LearningEvidenceKind, "learning_evidence_kind"),
        nullable=False,
    )
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    mastery_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["curriculum_edition_id", "course_id"],
            ["curriculum_editions.id", "curriculum_editions.course_id"],
            name="fk_learning_evidence_edition_course",
            ondelete="CASCADE",
        ),
        CheckConstraint("length(trim(observation)) > 0", name="observation_not_blank"),
        CheckConstraint(
            "mastery_delta >= -1.0 AND mastery_delta <= 1.0",
            name="mastery_delta_unit_interval",
        ),
        Index(
            "ix_learning_evidence_student_concept",
            "student_user_id",
            "concept_candidate_id",
            "created_at",
        ),
        Index("ix_learning_evidence_course_kind", "course_id", "kind", "created_at"),
    )


# Ingestion uses the domain term SourceChunk.  The database model keeps the
# more explicit name DocumentChunk while offering a zero-cost compatibility
# alias (not a second table or mapping).
SourceChunk = DocumentChunk


__all__ = [
    "EMBEDDING_DIMENSION",
    "AgentTrace",
    "AnswerPolicy",
    "AnswerReleaseLevel",
    "AttachmentKind",
    "AttachmentStatus",
    "AuditEventType",
    "AuditLog",
    "AuditResourceType",
    "Base",
    "CandidateKind",
    "CandidateMergeLineage",
    "CandidateOrigin",
    "CandidateRevision",
    "CandidateStatus",
    "ChunkExtractionStatus",
    "Course",
    "CourseMembership",
    "CourseRole",
    "CourseStatus",
    "CurriculumEdition",
    "CurriculumEditionStatus",
    "CurriculumOutlineSource",
    "CurriculumUnit",
    "CurriculumUnitType",
    "DocumentChunk",
    "DocumentParseRun",
    "DocumentParseRunStatus",
    "DocumentPublication",
    "DocumentStatus",
    "DocumentType",
    "DocumentVersionStatus",
    "Evidence",
    "EvidenceStatus",
    "EvidenceSupportRole",
    "EvidenceType",
    "ExtractionRun",
    "ExtractionRunStatus",
    "GraphNodeCandidate",
    "GraphNodeType",
    "GraphRelationCandidate",
    "GraphRelationType",
    "GraphSyncOperation",
    "GraphSyncOutbox",
    "LearningEvidence",
    "LearningEvidenceKind",
    "LocatorType",
    "MembershipStatus",
    "MultimodalExtraction",
    "MultimodalExtractionKind",
    "MultimodalExtractionStatus",
    "NodeCandidateEvidenceSupport",
    "OutboxStatus",
    "PublicationStatus",
    "RelationCandidateEvidenceSupport",
    "ReviewDecision",
    "ReviewDecisionType",
    "SessionStatus",
    "SourceAuthority",
    "SourceChunk",
    "SourceDocument",
    "SourceDocumentVersion",
    "SourceRole",
    "SystemRole",
    "TeachingAction",
    "TeachingConversation",
    "TeachingConversationStatus",
    "TeachingMode",
    "TeachingTaskKind",
    "TeachingTurn",
    "TeachingTurnStatus",
    "User",
    "UserAttachment",
    "UserSession",
    "UserStatus",
]
