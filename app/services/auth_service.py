from app.database import get_connection
from app.utils.hashing import PasswordHasher
from app.utils.validators import DataValidator
from app.utils.jwt_handler import JWTHandler
from datetime import datetime


class AuthService:
    """Handle user authentication: signup, login, and user retrieval"""

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
        """
        Register a new user.

        Raises:
            ValueError: validation failure or duplicate email/username
        """
        # Step 1: Validate input
        is_valid, error_msg = DataValidator.validate_signup_input(
            email, username, password
        )
        if not is_valid:
            raise ValueError(error_msg)

        async with get_connection() as conn:

            # Step 2: Check username uniqueness
            existing_username = await conn.fetchrow(
                "SELECT id FROM users WHERE username = $1",
                username,
            )
            if existing_username:
                raise ValueError("Username already taken")

            # Step 3: Check email uniqueness
            existing_email = await conn.fetchrow(
                "SELECT id FROM users WHERE email = $1",
                email,
            )
            if existing_email:
                raise ValueError("Email already registered")

            # Step 4: Hash password
            hashed_password = PasswordHasher.hash_password(password)

            # Step 5: Insert user
            user = await conn.fetchrow(
                """
                INSERT INTO users (
                    email, username, password_hash, display_name,
                    email_verified, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, TRUE, NOW(), NOW())
                RETURNING
                    id, email, username, display_name, avatar_url,
                    total_points, badge_tier, role, created_at
                """,
                email,
                username,
                hashed_password,
                display_name or username,
            )

        # Step 6: Create JWT token
        token = JWTHandler.create_token(str(user["id"]), user["username"])

        return self._build_auth_response(user, token)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, username: str, password: str):
        """
        Login with username or email.

        Raises:
            ValueError: user not found or wrong password
        """
        async with get_connection() as conn:

            # Try username first, then email
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE username = $1",
                username,
            )
            if not user:
                user = await conn.fetchrow(
                    "SELECT * FROM users WHERE email = $1",
                    username,
                )
            if not user:
                raise ValueError("Username or email not found")

        # Verify password (outside the connection — purely CPU work)
        if not PasswordHasher.verify_password(password, user["password_hash"]):
            raise ValueError("Invalid password")

        token = JWTHandler.create_token(str(user["id"]), user["username"])
        return self._build_auth_response(user, token)

    # ------------------------------------------------------------------
    # Get user by ID
    # ------------------------------------------------------------------

    async def get_user_by_id(self, user_id: str):
        """
        Fetch a user by their UUID.

        Raises:
            ValueError: user not found
        """
        async with get_connection() as conn:
            user = await conn.fetchrow(
                """
                SELECT
                    id, email, username, display_name, avatar_url,
                    total_points, badge_tier, role, created_at
                FROM users
                WHERE id = $1
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
            "created_at": str(user["created_at"]),
        }

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _build_auth_response(self, user, token: str) -> dict:
        """Build the standard auth response dict from a user row."""
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
