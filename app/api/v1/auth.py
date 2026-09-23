"""
Authentication API endpoints for the frontend application.

Provides endpoints to:
  - GET /auth/config: Retrieve configuration settings (such as dev_mode)
  - POST /auth/verify: Verify a user-provided API key
"""

import hmac

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.dependencies import SettingsDep

router = APIRouter(prefix="/auth", tags=["auth"])


class VerifyRequest(BaseModel):
    """Schema for validating an API key check request."""

    api_key: str = Field(min_length=1, description="API Key provided by the user")


class VerifyResponse(BaseModel):
    """Schema for verification response."""

    valid: bool


class AuthConfigResponse(BaseModel):
    """Schema for auth configuration response."""

    dev_mode: bool
    default_api_key: str | None = None


@router.get(
    "/config",
    response_model=AuthConfigResponse,
    summary="Get authentication configuration helpers",
    description="Returns configuration details to help the frontend auto-populate keys in local/development mode.",
)
async def get_auth_config(settings: SettingsDep) -> AuthConfigResponse:
    """Return dev mode configuration helper."""
    is_dev = settings.local_offline or settings.app_env == "development"
    return AuthConfigResponse(
        dev_mode=is_dev,
        default_api_key=None,
    )


@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Verify API Key validity",
    description="Checks if a user-supplied API key is valid using a timing-safe equality comparison.",
)
async def verify_api_key(request: VerifyRequest, settings: SettingsDep) -> VerifyResponse:
    """Verify the provided API key is correct."""
    if settings.api_secret_key is None:
        return VerifyResponse(valid=False)
    expected_key = settings.api_secret_key.get_secret_value()
    valid = hmac.compare_digest(
        request.api_key.encode("utf-8"),
        expected_key.encode("utf-8"),
    )
    return VerifyResponse(valid=valid)
