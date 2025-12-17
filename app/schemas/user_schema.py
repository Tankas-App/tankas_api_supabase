from pydantic import BaseModel
from typing import Optional

# REQUEST SCHEMAS (what comes from frontend)

class SignupRequest(BaseModel):
    """Schema for user signup request"""
    email: str
    username: str
    password: str
    display_name: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "john@example.com",
                "username": "john123",
                "password": "SecurePass123",
                "display_name": "John Doe"
            }
        }


class LoginRequest(BaseModel):
    """Schema for user login request"""
    username: str  # Can be username or email
    password: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "john123",
                "password": "SecurePass123"
            }
        }


# RESPONSE SCHEMAS (what goes back to frontend)

class UserResponse(BaseModel):
    """Schema for returning user data (without sensitive info)"""
    id: str
    email: str
    username: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    total_points: int
    badge_tier: str
    role: str
    created_at: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "john@example.com",
                "username": "john123",
                "display_name": "John Doe",
                "avatar_url": None,
                "total_points": 0,
                "badge_tier": "bronze",
                "role": "user",
                "created_at": "2024-01-15T10:30:00"
            }
        }


class AuthResponse(BaseModel):
    """Schema for authentication response (signup/login success)"""
    user: UserResponse
    token: str
    token_type: str = "bearer"
    
    class Config:
        json_schema_extra = {
            "example": {
                "user": {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "email": "john@example.com",
                    "username": "john123",
                    "display_name": "John Doe",
                    "avatar_url": None,
                    "total_points": 0,
                    "badge_tier": "bronze",
                    "role": "user",
                    "created_at": "2024-01-15T10:30:00"
                },
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer"
            }
        }


class ErrorResponse(BaseModel):
    """Schema for error responses"""
    error: str
    message: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "validation_error",
                "message": "Invalid email format"
            }
        }