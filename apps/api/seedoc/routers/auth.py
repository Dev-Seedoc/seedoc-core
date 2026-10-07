from typing import NoReturn

from fastapi import APIRouter, Request, Response, status

from seedoc.deps import Ctx, DbSession
from seedoc.errors import AppError, ErrorCode
from seedoc.schemas.auth import (
    AcceptInvitationRequest,
    InvitationPreview,
    LoginRequest,
    MeRead,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ReauthenticateRequest,
    TotpSetupRead,
    VerifyTotpRequest,
)
from seedoc.security.sessions import SESSION_ABSOLUTE_TTL, SESSION_COOKIE
from seedoc.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_ABSOLUTE_TTL.total_seconds()),
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=True, samesite="lax")


def _not_implemented() -> NoReturn:
    raise AppError(ErrorCode.INTERNAL_ERROR, "not implemented")


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response, db: DbSession, ctx: Ctx) -> MeRead:
    token, me = await auth_service.login(db, ctx, body, request.headers.get("user-agent"))
    _set_session_cookie(response, token)
    return me


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, db: DbSession, ctx: Ctx) -> None:
    await auth_service.logout(db, ctx)
    _clear_session_cookie(response)


@router.get("/me")
async def get_me(db: DbSession, ctx: Ctx) -> MeRead:
    return await auth_service.get_me(db, ctx)


@router.post("/reauth", status_code=status.HTTP_204_NO_CONTENT)
async def reauthenticate(body: ReauthenticateRequest, db: DbSession, ctx: Ctx) -> None:
    await auth_service.reauthenticate(db, ctx, body)


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(body: PasswordResetRequest, db: DbSession, ctx: Ctx) -> None:
    await auth_service.request_password_reset(db, ctx, body)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(
    body: PasswordResetConfirmRequest, response: Response, db: DbSession, ctx: Ctx
) -> None:
    await auth_service.confirm_password_reset(db, ctx, body)
    _clear_session_cookie(response)


@router.get("/invitations/{token}")
async def get_invitation(token: str, db: DbSession) -> InvitationPreview:
    return await auth_service.get_invitation(db, token)


@router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str, body: AcceptInvitationRequest, request: Request, response: Response, db: DbSession, ctx: Ctx
) -> MeRead:
    session_token, me = await auth_service.accept_invitation(db, ctx, token, body, request.headers.get("user-agent"))
    _set_session_cookie(response, session_token)
    return me


@router.post("/totp/setup")
async def setup_totp() -> TotpSetupRead:
    _not_implemented()  # M0-A8


@router.post("/totp/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify_totp(body: VerifyTotpRequest) -> None:
    _not_implemented()  # M0-A8
