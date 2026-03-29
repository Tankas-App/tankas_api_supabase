"""
auth_service.py — User authentication with email OTP + refresh tokens
"""

from app.database import get_connection
from app.utils.hashing import PasswordHasher
from app.utils.validators import DataValidator
from app.utils.jwt_handler import JWTHandler
from app.services.email_service import EmailService
from app.services.otp_service import OTPService


class AuthService:

    def __init__(self):
        self.email_service = EmailService()
        self.otp_service = OTPService()

    # ------------------------------------------------------------------
    # Signup
    # ------------------------------------------------------------------

    async def signup(
        self,
        email: str,
        username: str,
        password: str,
        display_name: str = None,
    ):
        # Validate input
        is_valid, error_msg = DataValidator.validate_signup_input(
            email, username, password
        )
        if not is_valid:
            raise ValueError(error_msg)

        async with get_connection() as conn:

            # Check uniqueness
            if await conn.fetchrow("SELECT id FROM users WHERE username=$1", username):
                raise ValueError("Username already taken")
            if await conn.fetchrow("SELECT id FROM users WHERE email=$1", email):
                raise ValueError("Email already registered")

            # Hash password
            hashed_password = PasswordHasher.hash_password(password)

            # Insert user
            user = await conn.fetchrow(
                """
                INSERT INTO users (
                    email, username, password_hash, display_name,
                    email_verified, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, FALSE, NOW(), NOW())
                RETURNING id, email, username, display_name, avatar_url,
                          total_points, badge_tier, role, created_at
                """,
                email,
                username,
                hashed_password,
                display_name or username,
            )

            user_id = str(user["id"])

            # Store refresh token
            refresh_token = JWTHandler.create_refresh_token(user_id, username)
            await conn.execute(
                "UPDATE users SET refresh_token=$1 WHERE id=$2",
                refresh_token,
                user_id,
            )

        # Create access token
        access_token = JWTHandler.create_token(user_id, username)

        # Send OTP for email verification
        try:
            await self.otp_service.request_otp(
                email=email,
                user_id=user_id,
                username=username,
            )
        except Exception as e:
            print(f"[AUTH] OTP send failed: {e}")

        # Send welcome email
        try:
            self.email_service.send_welcome(email, username)
        except Exception as e:
            print(f"[AUTH] Welcome email failed: {e}")

        return {
            **self._build_auth_response(user, access_token),
            "refresh_token": refresh_token,
            "email_verified": False,
            "message": "Account created! Check your email for a verification code.",
        }

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, username: str, password: str):

        async with get_connection() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE username=$1", username
            )
            if not user:
                user = await conn.fetchrow(
                    "SELECT * FROM users WHERE email=$1", username
                )
            if not user:
                raise ValueError("Username or email not found")

            if not PasswordHasher.verify_password(password, user["password_hash"]):
                raise ValueError("Invalid password")

            user_id = str(user["id"])
            access_token = JWTHandler.create_token(user_id, user["username"])
            refresh_token = JWTHandler.create_refresh_token(user_id, user["username"])

            await conn.execute(
                "UPDATE users SET refresh_token=$1, updated_at=NOW() WHERE id=$2",
                refresh_token,
                user_id,
            )

        return {
            **self._build_auth_response(user, access_token),
            "refresh_token": refresh_token,
            "email_verified": user["email_verified"],
        }

    # ------------------------------------------------------------------
    # Refresh token
    # ------------------------------------------------------------------

    async def refresh_access_token(self, refresh_token: str) -> dict:
        """Exchange a valid refresh token for a new access token."""

        if not JWTHandler.is_refresh_token(refresh_token):
            raise ValueError("Invalid refresh token")

        payload = JWTHandler.verify_token(refresh_token)
        user_id = payload.get("user_id")

        async with get_connection() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE id=$1 AND refresh_token=$2",
                user_id,
                refresh_token,
            )
            if not user:
                raise ValueError("Refresh token is invalid or has been revoked")

            new_access = JWTHandler.create_token(user_id, user["username"])
            new_refresh = JWTHandler.create_refresh_token(user_id, user["username"])

            await conn.execute(
                "UPDATE users SET refresh_token=$1, updated_at=NOW() WHERE id=$2",
                new_refresh,
                user_id,
            )

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
        }

    # ------------------------------------------------------------------
    # Get user by ID
    # ------------------------------------------------------------------

    async def get_user_by_id(self, user_id: str) -> dict:
        async with get_connection() as conn:
            user = await conn.fetchrow(
                """
                SELECT id, email, username, display_name, avatar_url,
                       total_points, badge_tier, role, email_verified, created_at
                FROM users WHERE id=$1
                """,
                user_id,
            )
        if not user:
            raise ValueError("User not found")
        return {
            "id": str(user["id"]),
            "email": user["email"],
            "username": user["username"],
            "display_name": user["display_name"],
            "avatar_url": user["avatar_url"],
            "total_points": user["total_points"] or 0,
            "badge_tier": user["badge_tier"] or "bronze",
            "role": user["role"] or "user",
            "email_verified": user["email_verified"],
            "created_at": str(user["created_at"]),
        }

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _build_auth_response(self, user, token: str) -> dict:
        return {
            "user": {
                "id": str(user["id"]),
                "email": user["email"],
                "username": user["username"],
                "display_name": user["display_name"],
                "avatar_url": user["avatar_url"],
                "total_points": user["total_points"] or 0,
                "badge_tier": user["badge_tier"] or "bronze",
                "role": user["role"] or "user",
                "created_at": str(user["created_at"]),
            },
            "token": token,
            "token_type": "bearer",
        }
