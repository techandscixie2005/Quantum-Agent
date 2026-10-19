"""Authenticated teacher decisions and bounded subsequent teaching directives."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FollowUpAction = Literal["continue", "request_revision", "revisit_prerequisite"]


class TeacherReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_turn_id: UUID
    decision: Literal["confirmed", "revise", "needs_follow_up"]
    reason: str = Field(min_length=1, max_length=2000)
    follow_up: FollowUpAction
    probe: str = Field(default="", max_length=1000)
    criterion_ratings: dict[
        str, Literal["meets", "partial", "needs_revision", "not_assessed"]
    ] = Field(default_factory=dict, max_length=20)

    @field_validator("reason", "probe")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def reason_and_directive_are_actionable(self) -> TeacherReviewRequest:
        if not self.reason:
            raise ValueError("teacher reviews require an auditable reason")
        if self.follow_up != "continue" and not self.probe:
            raise ValueError("a revision or prerequisite follow-up requires a concrete probe")
        if self.follow_up == "continue" and self.probe:
            raise ValueError("a continue directive does not carry a probe")
        return self


class TeacherFollowUp(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    review_id: UUID
    follow_up: FollowUpAction
    probe: str = Field(default="", max_length=1000)


class TeacherReviewRecord(TeacherReviewRequest):
    model_config = ConfigDict(extra="forbid", frozen=True)

    review_id: UUID
    conversation_id: UUID
    student_user_id: UUID
    reviewer_user_id: UUID
    created_at: datetime
    course_package: dict[str, object] | None = None
