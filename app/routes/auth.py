"""
routes/auth.py — Authentication endpoints including OTP and token refresh
"""

from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional
from app.schemas.user_schema import (
    SignupRequest,
    LoginRequest,
    AuthResponse,
    ErrorResponse,
)
from app.services.auth_service import AuthService
from app.services.otp_service import OTPService

router = APIRouter(tags=["authentication"])
auth_service = AuthService()
otp_service = OTPService()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class OTPRequest(BaseModel):
    email: str


class OTPVerifyRequest(BaseModel):
    email: str
    otp_code: str


# ---------------------------------------------------------------------------
# Signup / Login
# ---------------------------------------------------------------------------


@router.post(
    "/auth/signup",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def signup(request: SignupRequest):
    """
    Register a new user.
    Sends a welcome email and OTP verification code automatically.
    """
    try:
        return await auth_service.signup(
            email=request.email,
            username=request.username,
            password=request.password,
            display_name=request.display_name,
        )
    except ValueError as e:
        error_msg = str(e)
        status_code = (
            status.HTTP_409_CONFLICT
            if "already" in error_msg.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=error_msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signup failed: {str(e)}")


@router.post(
    "/auth/login",
    responses={
        401: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
    },
)
async def login(request: LoginRequest):
    """Login with username or email. Returns access + refresh token."""
    try:
        return await auth_service.login(
            username=request.username,
            password=request.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


@router.post("/auth/refresh")
async def refresh_token(body: RefreshTokenRequest):
    """
    Exchange a refresh token for a new access token + refresh token.
    Call this when the access token expires (after 7 days).
    """
    try:
        return await auth_service.refresh_access_token(body.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# OTP endpoints
# ---------------------------------------------------------------------------


@router.post("/auth/otp/request")
async def request_otp(body: OTPRequest):
    """
    Request an email OTP verification code.
    Sends a 6-digit code to the provided email.
    Valid for 10 minutes, max 3 attempts.
    """
    try:
        return await otp_service.resend_otp(email=body.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth/otp/verify")
async def verify_otp(body: OTPVerifyRequest):
    """
    Verify an email OTP code.
    Marks the user's email as verified on success.
    """
    try:
        return await otp_service.verify_otp(
            email=body.email,
            otp_code=body.otp_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth/otp/resend")
async def resend_otp(body: OTPRequest):
    """
    Resend OTP verification code.
    Invalidates previous code and sends a fresh one.
    """
    try:
        return await otp_service.resend_otp(email=body.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
