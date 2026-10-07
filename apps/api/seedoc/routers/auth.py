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
from seedoc.security.sessions import SESSION_COOKIE, revoke_session
from seedoc.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


from typing import NoReturn


def _not_implemented() -> NoReturn:
    raise AppError(ErrorCode.INTERNAL_ERROR, "not implemented")


@router.post("/login", response_model=MeRead)
async def login(body: LoginRequest, db: DbSession, ctx: Ctx, response: Response) -> MeRead:
    async with db.begin():
        token, me = await auth_service.login(db, ctx, body)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=True, samesite="lax", path="/")
    return me


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: DbSession, ctx: Ctx, response: Response) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        async with db.begin():
            await revoke_session(db, token)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=MeRead)
async def get_me(db: DbSession, ctx: Ctx) -> MeRead:
    async with db.begin():
        return await auth_service.get_me(db, ctx)


@router.post("/reauth", status_code=status.HTTP_204_NO_CONTENT)
async def reauthenticate(body: ReauthenticateRequest, db: DbSession, ctx: Ctx) -> None:
    async with db.begin():
        await auth_service.reauthenticate(db, ctx, body)


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(body: PasswordResetRequest, db: DbSession, ctx: Ctx) -> None:
    async with db.begin():
        await auth_service.request_password_reset(db, ctx, body)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(
    body: PasswordResetConfirmRequest, db: DbSession, ctx: Ctx, response: Response
) -> None:
    async with db.begin():
        await auth_service.confirm_password_reset(db, ctx, body)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/invitations/{token}", response_model=InvitationPreview)
async def get_invitation(token: str, db: DbSession) -> InvitationPreview:
    async with db.begin():
        return await auth_service.get_invitation(db, token)


@router.post("/invitations/{token}/accept", response_model=MeRead)
async def accept_invitation(
    token: str, body: AcceptInvitationRequest, db: DbSession, ctx: Ctx, response: Response
) -> MeRead:
    async with db.begin():
        session_token, me = await auth_service.accept_invitation(db, ctx, token, body)
    response.set_cookie(SESSION_COOKIE, session_token, httponly=True, secure=True, samesite="lax", path="/")
    return me


@router.post("/totp/setup", response_model=TotpSetupRead)
async def setup_totp() -> TotpSetupRead:
    _not_implemented()


@router.post("/totp/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify_totp(body: VerifyTotpRequest) -> None:
    _not_implemented()
