from datetime import datetime, timedelta
from jose import JWTError, jwt
from app.config import config

class JWTHandler:
    """Create and verify JWT tokens for authentication"""
    
    # Token expiry: 30 minutes
    TOKEN_EXPIRY_MINUTES = 30
    
    @staticmethod
    def create_token(user_id: str, username: str) -> str:
        """
        Create a JWT token for a user
        
        Args:
            user_id: The user's UUID
            username: The user's username
            
        Returns:
            A JWT token string
        """
        # Calculate expiry time
        expires_at = datetime.now() + timedelta(minutes=JWTHandler.TOKEN_EXPIRY_MINUTES)
        
        # Create the payload (the data inside the token)
        payload = {
            "user_id": user_id,
            "username": username,
            "exp": expires_at,  # Expiry timestamp
            "iat": datetime.now()  # Issued at timestamp
        }
        
        # Sign and encode the token using the secret key
        token = jwt.encode(
            payload,
            config.JWT_SECRET,
            algorithm="HS256"
        )
        
        return token
    
    @staticmethod
    def verify_token(token: str) -> dict:
        """
        Verify a JWT token and extract the payload
        
        Args:
            token: The JWT token to verify
            
        Returns:
            The decoded payload (user_id, username, etc.)
            
        Raises:
            JWTError: If token is invalid, expired, or tampered with
        """
        try:
            # Decode and verify the token
            payload = jwt.decode(
                token,
                config.JWT_SECRET,
                algorithms=["HS256"]
            )
            return payload
        except JWTError as e:
            # Token is invalid, expired, or signature doesn't match
            raise JWTError(f"Invalid token: {str(e)}")
    
    @staticmethod
    def get_user_id_from_token(token: str) -> str:
        """
        Extract user_id from a token
        
        Args:
            token: The JWT token
            
        Returns:
            The user_id from the token
            
        Raises:
            JWTError: If token is invalid
        """
        payload = JWTHandler.verify_token(token)
        return payload.get("user_id")