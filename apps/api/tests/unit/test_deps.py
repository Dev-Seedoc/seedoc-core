from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from seedoc.deps import RequestContext, require_fresh_auth, require_role
from seedoc.errors import AppError, ErrorCode
from seedoc.models.tenants import MemberRole

ANONYMOUS = RequestContext(
    user_id=None,
    tenant_id=None,
    role=None,
    is_staff=False,
    session_id=None,
    fresh_auth_at=None,
    portal_session_id=None,
    operator_org_ids=(),
    ip_hash=None,
    request_id="test",
)
EDITOR = replace(ANONYMOUS, user_id=uuid4(), tenant_id=uuid4(), role=MemberRole.EDITOR)


async def _error_code(coro: object) -> ErrorCode:
    with pytest.raises(AppError) as info:
        await coro  # pyright: ignore[reportGeneralTypeIssues]
    return info.value.code


async def test_require_role_anonymous_is_unauthenticated() -> None:
    assert await _error_code(require_role(MemberRole.EDITOR)(ANONYMOUS)) is ErrorCode.UNAUTHENTICATED


async def test_require_role_non_member_is_not_found() -> None:
    non_member = replace(EDITOR, role=None)

    assert await _error_code(require_role(MemberRole.EDITOR)(non_member)) is ErrorCode.NOT_FOUND


async def test_require_role_too_low_is_forbidden() -> None:
    assert await _error_code(require_role(MemberRole.ADMIN)(EDITOR)) is ErrorCode.FORBIDDEN


async def test_require_role_owner_passes_admin_check() -> None:
    owner = replace(EDITOR, role=MemberRole.OWNER)

    assert await require_role(MemberRole.ADMIN)(owner) is owner


async def test_require_fresh_auth_expires_after_30_minutes() -> None:
    stale = replace(EDITOR, fresh_auth_at=datetime.now(UTC) - timedelta(minutes=31))
    fresh = replace(EDITOR, fresh_auth_at=datetime.now(UTC) - timedelta(minutes=5))

    assert await _error_code(require_fresh_auth(stale)) is ErrorCode.FRESH_AUTH_REQUIRED
    assert await require_fresh_auth(fresh) is fresh
