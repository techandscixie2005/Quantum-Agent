"""API-key login (PRD V3.1 §3).

A student enters their 词元计划/一〇七杯 API key.  The backend probes the USTC
model service to validate the key, mints an opaque session token, stores the
Fernet-encrypted key in the session vault keyed by ``session_id``, and returns
the session token + the demo student's course/edition binding.  The plaintext
key never enters PostgreSQL, logs, agent traces, or the response body.

The startup ``USTC_API`` env key remains as a dev/deploy fallback (PRD §3.3
last bullet): when the vault is disabled, the ModelGateway uses the env key
for all sessions.  This endpoint still mints a session in that case so the
frontend can proceed; the probe still validates the supplied key.

Logout revokes the session and deletes the vault entry.

This is NOT a substitute for real SSO.  It exists so a student can enter
``/agent`` with their own model-service credential.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantum_agent.auth import (
    hash_session_token,
    issue_opaque_session_token,
)
from quantum_agent.config import Settings
from quantum_agent.credential_vault import CredentialVault
from quantum_agent.database import session_dependency
from quantum_agent.db_models import (
    Course,
    CourseMembership,
    CourseStatus,
    CurriculumEdition,
    CurriculumEditionStatus,
    MembershipStatus,
    SessionStatus,
    User,
    UserSession,
    UserStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]

_LOGIN_RATE_LIMIT = 10
_LOGIN_RATE_WINDOW_SECONDS = 300
_login_attempts: dict[str, list[float]] = defaultdict(list)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr
    course_id: str | None = Field(default=None, max_length=64)


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_token: str
    course_id: str
    curriculum_edition_id: str
    user_id: str
    display_name: str
    expires_at: str


class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _settings(request: Request) -> Settings:
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise HTTPException(status_code=500, detail="server settings unavailable")
    return settings


def _vault(request: Request) -> CredentialVault | None:
    return getattr(request.app.state, "credential_vault", None)


def _check_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    window = _login_attempts[client_ip]
    window[:] = [t for t in window if now - t < _LOGIN_RATE_WINDOW_SECONDS]
    if len(window) >= _LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="登录尝试过于频繁，请稍后再试",
            headers={"Retry-After": str(_LOGIN_RATE_WINDOW_SECONDS)},
        )
    window.append(now)


async def _probe_ustc_key(
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> bool:
    """Validate the API key by sending a 1-token chat request to USTC.

    Returns True on HTTP 200, False on 401/403, and False on any other
    failure (we fail closed rather than letting an unvalidated key through).
    """

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


@router.post("/login", response_model=LoginResponse)
async def api_key_login(
    request: Request,
    body: LoginRequest,
    session: DatabaseSession,
) -> LoginResponse:
    settings = _settings(request)
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or "local"
    _check_rate_limit(client_ip)

    api_key = body.api_key.get_secret_value().strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key must not be blank")
    if len(api_key) < 16 or len(api_key) > 256:
        raise HTTPException(status_code=422, detail="invalid request")

    # Validate the key against the USTC model service before minting a session.
    probe_ok = await _probe_ustc_key(
        api_key=api_key,
        base_url=settings.ustc_base_url,
        model=settings.ustc_quick_model,
    )
    if not probe_ok:
        raise HTTPException(
            status_code=401,
            detail="API key 被模型服务拒绝或模型服务不可用",
        )

    # Find-or-create the demo student the API-key login binds to.
    email = settings.login_course_email
    user = await session.scalar(select(User).where(User.email == email).limit(1))
    if user is None:
        raise HTTPException(
            status_code=409,
            detail="登录账户未初始化；请先运行 `quantum-agent seed-login-account`",
        )
    if user.status is not UserStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="登录账户未激活")

    membership: CourseMembership | None = None
    if body.course_id is not None:
        membership = await session.scalar(
            select(CourseMembership).where(
                CourseMembership.user_id == user.id,
                CourseMembership.course_id == body.course_id,
                CourseMembership.status == MembershipStatus.ACTIVE,
            )
        )
    else:
        membership = await session.scalar(
            select(CourseMembership)
            .where(
                CourseMembership.user_id == user.id,
                CourseMembership.status == MembershipStatus.ACTIVE,
            )
            .order_by(CourseMembership.joined_at.desc())
            .limit(1)
        )
    if membership is None:
        raise HTTPException(
            status_code=409,
            detail="登录账户没有可用的课程成员资格；请先运行 `make demo-bootstrap`",
        )

    course = await session.scalar(select(Course).where(Course.id == membership.course_id))
    if course is None or course.status is not CourseStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="课程未激活")

    edition = await session.scalar(
        select(CurriculumEdition)
        .where(
            CurriculumEdition.course_id == course.id,
            CurriculumEdition.status == CurriculumEditionStatus.PUBLISHED,
        )
        .order_by(CurriculumEdition.published_at.desc())
        .limit(1)
    )
    if edition is None:
        raise HTTPException(
            status_code=409,
            detail="课程没有已发布的课程版本",
        )

    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
    raw_token = issue_opaque_session_token()
    user_session = UserSession(
        user_id=user.id,
        session_token_sha256=hash_session_token(raw_token),
        status=SessionStatus.ACTIVE,
        expires_at=expires_at,
        user_agent="quantum-agent-api-key-login",
    )
    session.add(user_session)
    await session.flush()

    # Store the Fernet-encrypted API key in the vault keyed by session_id.
    vault = _vault(request)
    if vault is not None:
        try:
            await vault.store(user_session.id, SecretStr(api_key))
        except Exception:
            logger.warning("vault store failed for session %s", user_session.id, exc_info=True)
            await session.rollback()
            raise HTTPException(status_code=500, detail="无法安全存储 API Key") from None
    elif settings.environment == "production":
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail="会话保险库未配置，生产环境拒绝保存 API Key",
        )

    await session.commit()

    return LoginResponse(
        session_token=raw_token,
        course_id=str(course.id),
        curriculum_edition_id=str(edition.id),
        user_id=str(user.id),
        display_name=user.display_name,
        expires_at=expires_at.isoformat(),
    )


@router.post("/logout")
async def api_key_logout(
    request: Request,
    session: DatabaseSession,
) -> dict[str, str]:
    """Revoke the caller's session and delete the vault entry.

    The caller supplies their bearer token; we look up the session by its
    SHA-256 digest, revoke it, and forget the vault entry.  We do not fail
    if the session is already gone (idempotent logout).
    """

    from quantum_agent.auth import bearer_credential

    try:
        credential = bearer_credential(request)
    except HTTPException:
        return {"status": "ok"}
    digest = hash_session_token(credential.token)
    user_session = await session.scalar(
        select(UserSession).where(UserSession.session_token_sha256 == digest).limit(1)
    )
    vault = _vault(request)
    if user_session is not None:
        user_session.status = SessionStatus.REVOKED
        user_session.revoked_at = datetime.now(UTC)
        if vault is not None:
            await vault.forget(user_session.id)
        await session.commit()
    return {"status": "ok"}


__all__ = ["router"]
