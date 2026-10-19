"""Exchange roster access plus a model credential for an opaque login session.

An operator-provisioned, one-time classroom token identifies an existing roster
member. The provider key authorizes model use independently of that identity;
sharing a provider key never merges users or grants a course role. Shared demo
identity requires explicit opt-in outside production. Institution SSO can
replace the operator provisioning flow.

Login validates the provider credential and requires a configured encrypted
vault. Plaintext keys never enter database rows, traces, or responses. Logout
revokes the login session and deletes its vault entry.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, SecretStr
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
_LOGIN_RATE_MAX_BUCKETS = 10_000
_login_attempts: dict[str, list[float]] = defaultdict(list)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr
    course_id: UUID | None = None
    classroom_access_token: SecretStr | None = None


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


def _credential_router_factory(request: Request) -> object | None:
    return getattr(request.app.state, "credential_router_factory", None)


def _check_rate_limit(bucket: str) -> None:
    now = time.monotonic()
    if bucket not in _login_attempts and len(_login_attempts) >= _LOGIN_RATE_MAX_BUCKETS:
        expired = [
            key for key, attempts in _login_attempts.items()
            if not attempts or now - attempts[-1] >= _LOGIN_RATE_WINDOW_SECONDS
        ]
        for key in expired:
            del _login_attempts[key]
        if len(_login_attempts) >= _LOGIN_RATE_MAX_BUCKETS:
            raise HTTPException(status_code=429, detail="Login rate capacity reached")
    window = _login_attempts[bucket]
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
    thinking_mode: Literal["enabled", "disabled"] | None = None,
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
    if thinking_mode is not None:
        body["thinking"] = {"type": thinking_mode}
    # An explicit 401/403 is a real rejection and fails closed immediately.
    # Timeouts / 5xx / network errors are transient stalls under load, so we
    # grant one retry before failing closed.
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, headers=headers, json=body)
        except httpx.HTTPError:
            if attempt == 0:
                await asyncio.sleep(0.5)
                continue
            return False
        if response.status_code == 200:
            return True
        if response.status_code in (401, 403):
            return False
        if response.status_code >= 500 and attempt == 0:
            await asyncio.sleep(0.5)
            continue
        return False
    return False


@router.post("/login", response_model=LoginResponse)
async def api_key_login(
    request: Request,
    body: LoginRequest,
    session: DatabaseSession,
) -> LoginResponse:
    settings = _settings(request)
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or "local"
    coarse_bucket = "ip:" + hash_session_token(client_ip)

    # A provider credential authorizes model use, never student identity or role.
    # Classroom tokens are provisioned for an existing roster member by an
    # operator/identity service and can be exchanged once. Shared demo identity
    # is available only by explicit development opt-in.
    access_session: UserSession | None = None
    if body.classroom_access_token is not None:
        access_token = body.classroom_access_token.get_secret_value().strip()
        if not 32 <= len(access_token) <= 512:
            _check_rate_limit(coarse_bucket)
            raise HTTPException(status_code=401, detail="Invalid classroom access token")
        access_digest = hash_session_token(access_token)
        access_session = await session.scalar(select(UserSession).where(
            UserSession.session_token_sha256 == access_digest,
            UserSession.status == SessionStatus.ACTIVE,
            UserSession.expires_at > datetime.now(UTC),
            UserSession.user_agent == "classroom-access",
        ).with_for_update())
        user = await session.get(User, access_session.user_id) if access_session else None
        if user is None:
            _check_rate_limit(coarse_bucket)
            raise HTTPException(status_code=401, detail="Invalid classroom access token")
        if user.status is not UserStatus.ACTIVE:
            _check_rate_limit(coarse_bucket)
            raise HTTPException(status_code=403, detail="Login account is inactive")
        # Distinct roster members behind the same classroom NAT/proxy must
        # not share a ten-attempt budget. Only a validated invitation can
        # select its own opaque bucket; fabricated tokens use the coarse one.
        _check_rate_limit("invite:" + access_digest)
    elif settings.allow_shared_demo_login and settings.environment != "production":
        _check_rate_limit(coarse_bucket)
        user = await session.scalar(select(User).where(
            User.email == settings.login_course_email,
        ).limit(1))
    else:
        _check_rate_limit(coarse_bucket)
        raise HTTPException(status_code=401, detail="Classroom access token required")
    api_key = body.api_key.get_secret_value().strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key must not be blank")
    if len(api_key) < 16 or len(api_key) > 256:
        raise HTTPException(status_code=422, detail="invalid request")
    if user is None:
        raise HTTPException(status_code=409, detail="Login account is not provisioned")
    if user.status is not UserStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Login account is inactive")

    # Validate the key against the USTC model service before minting a session.
    probe_ok = await _probe_ustc_key(
        api_key=api_key,
        base_url=settings.ustc_base_url,
        model=settings.ustc_text_model_override or settings.ustc_quick_model,
        thinking_mode=settings.ustc_text_thinking_mode,
    )
    if not probe_ok:
        raise HTTPException(
            status_code=401,
            detail="API key 被模型服务拒绝或模型服务不可用",
        )

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
    else:
        await session.rollback()
        raise HTTPException(
            status_code=503,
            detail="会话保险库未配置，拒绝创建用户凭证会话",
        )

    if access_session is not None:
        access_session.status = SessionStatus.REVOKED
        access_session.revoked_at = now
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
    if user_session is not None:
        user_session.status = SessionStatus.REVOKED
        user_session.revoked_at = datetime.now(UTC)
        factory = _credential_router_factory(request)
        forget_session = getattr(factory, "forget_session", None)
        if callable(forget_session):
            await forget_session(user_session.id)
        else:
            vault = _vault(request)
            if vault is not None:
                await vault.forget(user_session.id)
        await session.commit()
    return {"status": "ok"}


__all__ = ["router"]
