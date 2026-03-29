"""
otp_service.py — Email OTP management
Handles: request, verify, resend
"""

from app.database import get_connection
from app.services.email_service import EmailService
from datetime import datetime, timedelta


OTP_EXPIRY_MINUTES = 10
OTP_MAX_RETRIES = 3


class OTPService:

    def __init__(self):
        self.email_service = EmailService()

    # ------------------------------------------------------------------
    # Request OTP
    # ------------------------------------------------------------------

    async def request_otp(self, email: str, user_id: str, username: str) -> dict:
        otp_code = EmailService.generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

        async with get_connection() as conn:

            # Invalidate existing OTPs for this email
            await conn.execute(
                "DELETE FROM otp_sessions WHERE email=$1",
                email,
            )

            # Create new OTP session
            session = await conn.fetchrow(
                """
                INSERT INTO otp_sessions
                    (user_id, email, otp_code, otp_type, expires_at, created_at)
                VALUES ($1, $2, $3, 'email_verification', $4, NOW())
                RETURNING id
                """,
                user_id,
                email,
                otp_code,
                expires_at,
            )

        # Send email
        sent = self.email_service.send_otp(email, otp_code, username)

        return {
            "session_id": str(session["id"]),
            "email": email,
            "expires_in": f"{OTP_EXPIRY_MINUTES} minutes",
            "sent": sent,
            "message": (
                f"OTP sent to {email}"
                if sent
                else "OTP generated but email failed — check server logs"
            ),
        }

    # ------------------------------------------------------------------
    # Verify OTP
    # ------------------------------------------------------------------

    async def verify_otp(self, email: str, otp_code: str) -> dict:

        async with get_connection() as conn:

            session = await conn.fetchrow(
                """
                SELECT * FROM otp_sessions
                WHERE email=$1 AND is_used=FALSE
                ORDER BY created_at DESC
                LIMIT 1
                """,
                email,
            )

            if not session:
                raise ValueError(
                    "No active OTP found for this email. Please request a new one."
                )

            # Check expiry
            if datetime.utcnow() > session["expires_at"]:
                await conn.execute(
                    "DELETE FROM otp_sessions WHERE id=$1", str(session["id"])
                )
                raise ValueError("OTP has expired. Please request a new one.")

            # Check max retries
            if session["retry_count"] >= OTP_MAX_RETRIES:
                await conn.execute(
                    "DELETE FROM otp_sessions WHERE id=$1", str(session["id"])
                )
                raise ValueError(
                    "Too many incorrect attempts. Please request a new OTP."
                )

            # Check code
            if session["otp_code"] != otp_code:
                await conn.execute(
                    "UPDATE otp_sessions SET retry_count = retry_count + 1 WHERE id=$1",
                    str(session["id"]),
                )
                remaining = OTP_MAX_RETRIES - (session["retry_count"] + 1)
                raise ValueError(f"Incorrect OTP. {remaining} attempt(s) remaining.")

            # Mark as used
            await conn.execute(
                "UPDATE otp_sessions SET is_used=TRUE WHERE id=$1",
                str(session["id"]),
            )

            # Mark user as email verified
            await conn.execute(
                "UPDATE users SET email_verified=TRUE, updated_at=NOW() WHERE id=$1",
                str(session["user_id"]),
            )

            # Clean up
            await conn.execute("DELETE FROM otp_sessions WHERE email=$1", email)

        return {
            "verified": True,
            "email": email,
            "message": "Email verified successfully!",
        }

    # ------------------------------------------------------------------
    # Resend OTP
    # ------------------------------------------------------------------

    async def resend_otp(self, email: str) -> dict:

        async with get_connection() as conn:
            user = await conn.fetchrow(
                "SELECT id, username, email_verified FROM users WHERE email=$1",
                email,
            )

        if not user:
            raise ValueError("No account found with this email.")

        if user["email_verified"]:
            raise ValueError("This email is already verified.")

        return await self.request_otp(
            email=email,
            user_id=str(user["id"]),
            username=user["username"],
        )
