from fastapi import APIRouter, HTTPException, status
from app.schemas.user_schema import SignupRequest, LoginRequest, AuthResponse, ErrorResponse
from app.services.auth_service import AuthService

# Create a router for auth endpoints
router = APIRouter(tags=["authentication"])

# Initialize the auth service
auth_service = AuthService()


@router.post(
    "/auth/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        409: {"model": ErrorResponse, "description": "Username or email already exists"}
    }
)
async def signup(request: SignupRequest):
    """
    Register a new user
    
    - **email**: User's email address
    - **username**: Unique username (3-20 chars, alphanumeric + underscore)
    - **password**: Strong password (8+ chars, uppercase, numbers)
    - **display_name**: Optional display name (defaults to username)
    
    Returns user data and JWT token on success
    """
    try:
        result = await auth_service.signup(
            email=request.email,
            username=request.username,
            password=request.password,
            display_name=request.display_name
        )
        return result
    
    except ValueError as e:
        # Validation error or username/email already exists
        error_msg = str(e)
        
        # Determine status code based on error
        if "already" in error_msg.lower():
            status_code = status.HTTP_409_CONFLICT
        else:
            status_code = status.HTTP_400_BAD_REQUEST
        
        raise HTTPException(
            status_code=status_code,
            detail=error_msg
        )
    
    except Exception as e:
        # Unexpected error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Signup failed: {str(e)}"
        )


@router.post(
    "/auth/login",
    response_model=AuthResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid credentials"},
        401: {"model": ErrorResponse, "description": "Unauthorized"}
    }
)
async def login(request: LoginRequest):
    """
    Login with username or email
    
    - **username**: Username or email address
    - **password**: User's password
    
    Returns user data and JWT token on success
    """
    try:
        result = await auth_service.login(
            username=request.username,
            password=request.password
        )
        return result
    
    except ValueError as e:
        error_msg = str(e)
        
        # Determine status code
        if "not found" in error_msg.lower():
            status_code = status.HTTP_401_UNAUTHORIZED
        elif "invalid" in error_msg.lower():
            status_code = status.HTTP_401_UNAUTHORIZED
        else:
            status_code = status.HTTP_400_BAD_REQUEST
        
        raise HTTPException(
            status_code=status_code,
            detail=error_msg
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )