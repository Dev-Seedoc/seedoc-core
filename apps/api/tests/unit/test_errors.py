from seedoc.errors import ERROR_STATUS, AppError, ErrorCode


def test_every_error_code_has_a_status() -> None:
    assert set(ERROR_STATUS) == set(ErrorCode)


def test_app_error_body_matches_contract() -> None:
    error = AppError(ErrorCode.PUBLISH_BLOCKED, details={"can_publish": False})

    assert error.status_code == 409
    assert error.to_body() == {
        "error": {"code": "publish_blocked", "message": "publish blocked", "details": {"can_publish": False}}
    }
