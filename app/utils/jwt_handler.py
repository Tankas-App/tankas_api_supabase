"""
jwt_handler.py — JWT token creation and verification
Access token:  7 days
Refresh token: 30 days
"""

from datetime import datetime, timedelta
from jose import JWTError, jwt
from app.config import config

ACCESS_TOKEN_EXPIRY_DAYS = 7
REFRESH_TOKEN_EXPIRY_DAYS = 30


class JWTHandler:

    @staticmethod
    def create_token(user_id: str, username: str) -> str:
        """Create a 7-day access token."""
        expires_at = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRY_DAYS)
        payload = {
            "user_id": user_id,
            "username": username,
            "type": "access",
            "exp": expires_at,
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

    @staticmethod
    def create_refresh_token(user_id: str, username: str) -> str:
        """Create a 30-day refresh token."""
        expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRY_DAYS)
        payload = {
            "user_id": user_id,
            "username": username,
            "type": "refresh",
            "exp": expires_at,
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

    @staticmethod
    def verify_token(token: str) -> dict:
        """Verify and decode a token."""
        try:
            return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        except JWTError as e:
            raise JWTError(f"Invalid token: {str(e)}")

    @staticmethod
    def get_user_id_from_token(token: str) -> str:
        """Extract user_id from a token."""
        payload = JWTHandler.verify_token(token)
        return payload.get("user_id")

    @staticmethod
    def is_refresh_token(token: str) -> bool:
        """Check if a token is a refresh token."""
        try:
            payload = JWTHandler.verify_token(token)
            return payload.get("type") == "refresh"
        except Exception:
            return False
