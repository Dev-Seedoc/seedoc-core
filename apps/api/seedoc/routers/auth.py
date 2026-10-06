from typing import NoReturn

from fastapi import APIRouter, status

from seedoc.errors import AppError, ErrorCode
from seedoc.schemas.auth import (
    AcceptInvitationRequest,
    InvitationPreview,
    LoginRequest,
    MeRead,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ReauthenticateRequest,
    TotpSetupResponse,
    VerifyTotpRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _not_implemented() -> NoReturn:
    raise AppError(ErrorCode.INTERNAL_ERROR, "not implemented")


@router.post("/login", response_model=MeRead)
async def login(body: LoginRequest) -> MeRead:
    _not_implemented()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> None:
    _not_implemented()


@router.get("/me", response_model=MeRead)
async def get_me() -> MeRead:
    _not_implemented()


@router.post("/reauth", status_code=status.HTTP_204_NO_CONTENT)
async def reauthenticate(body: ReauthenticateRequest) -> None:
    _not_implemented()


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(body: PasswordResetRequest) -> None:
    _not_implemented()


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(body: PasswordResetConfirmRequest) -> None:
    _not_implemented()


@router.get("/invitations/{token}", response_model=InvitationPreview)
async def get_invitation(token: str) -> InvitationPreview:
    _not_implemented()


@router.post("/invitations/{token}/accept", response_model=MeRead)
async def accept_invitation(token: str, body: AcceptInvitationRequest) -> MeRead:
    _not_implemented()


@router.post("/totp/setup", response_model=TotpSetupResponse)
async def setup_totp() -> TotpSetupResponse:
    _not_implemented()


@router.post("/totp/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify_totp(body: VerifyTotpRequest) -> None:
    _not_implemented()
