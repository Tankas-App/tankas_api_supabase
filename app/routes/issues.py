from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, Request
from typing import Optional
from app.schemas.user_schema import ErrorResponse
from app.services.issue_service import IssueService
from app.utils.jwt_handler import JWTHandler
from pydantic import BaseModel

# Create router
router = APIRouter(tags=["issues"])

# Initialize issue service
issue_service = IssueService()


# ============ SCHEMAS ============


class CreateIssueRequest(BaseModel):
    """Request to create a new issue"""

    title: Optional[str] = None  # Optional, AI can generate
    description: Optional[str] = None  # Optional, AI can auto-fill
    latitude: float  # GPS coordinate
    longitude: float  # GPS coordinate
    priority: Optional[str] = "medium"  # low, medium, high


class IssueResponse(BaseModel):
    """Response when issue is created"""

    issue_id: str
    title: str
    description: str
    photo_url: str
    latitude: float
    longitude: float
    difficulty: str
    priority: str
    points_assigned: int
    ai_labels: list
    ai_confidence: float


# ============ HELPER FUNCTIONS ============


async def get_current_user_id(request: Request) -> str:
    """
    Extract user_id from JWT token in Authorization header

    Uses Request object instead of Header() for better multipart/form-data compatibility
    """
    # Get Authorization header from request
    auth_header = request.headers.get("authorization")

    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    # Expected format: "Bearer <token>"
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    token = parts[1]

    try:
        user_id = JWTHandler.get_user_id_from_token(token)
        return user_id
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {str(e)}"
        )


# ============ ENDPOINTS ============


@router.post(
    "/issues",
    response_model=IssueResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def create_issue(
    request: Request,
    file: UploadFile = File(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    priority: Optional[str] = Form("medium"),
):
    """
    Report a new environmental issue

    **Request:**
    - **file**: Photo of the issue (multipart/form-data)
    - **latitude**: GPS latitude coordinate
    - **longitude**: GPS longitude coordinate
    - **title**: (Optional) Issue title
    - **description**: (Optional) Issue description
    - **priority**: (Optional) low/medium/high
    - **Authorization**: Bearer token in header

    **Response:**
    - Created issue with AI-analyzed difficulty and assigned points

    **Process:**
    1. Extract user_id from JWT token
    2. Read photo file
    3. Upload photo to Supabase Storage
    4. Extract EXIF location (if available)
    5. Send to Google Vision for analysis
    6. Calculate difficulty and points
    7. Create issue in database
    """
    try:
        # Step 1: Extract user_id from token using Request object
        user_id = await get_current_user_id(request)

        # Step 2: Read photo file
        try:
            photo_bytes = await file.read()

            # Validate file size (max 10MB)
            if len(photo_bytes) > 10 * 1024 * 1024:
                raise ValueError("File too large. Maximum size is 10MB")

            # Validate file type (basic check)
            if not photo_bytes[:3] in [
                b"\xff\xd8\xff",
                b"\x89PN",
                b"\x47IF",
            ]:  # JPEG, PNG, GIF
                raise ValueError(
                    "Invalid file type. Please upload a JPEG, PNG, or GIF image"
                )

        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # Step 3-7: Create issue (service handles all steps)
        result = await issue_service.create_issue(
            user_id=user_id,
            title=title,
            description=description,
            photo_bytes=photo_bytes,
            latitude=latitude,
            longitude=longitude,
            priority=priority,
        )

        created_issue = result["issue"]
        ai_analysis = result["ai_analysis"]

        return IssueResponse(
            issue_id=created_issue["id"],
            title=created_issue["title"],
            description=created_issue["description"],
            photo_url=created_issue["picture_url"],
            latitude=created_issue["latitude"],
            longitude=created_issue["longitude"],
            difficulty=created_issue["difficulty"],
            priority=created_issue["priority"],
            points_assigned=created_issue["points_assigned"],
            ai_labels=[label["name"] for label in ai_analysis["labels"]],
            ai_confidence=ai_analysis["confidence"],
        )

    except HTTPException as e:
        raise e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create issue: {str(e)}",
        )


@router.get("/issues/nearby")
async def get_nearby_issues(latitude: float, longitude: float, radius_km: float = 5.0):
    """
    Get environmental issues near a location

    Args:
        latitude: User's GPS latitude
        longitude: User's GPS longitude
        radius_km: Search radius in kilometers (default 5)
    """
    try:
        issues = await issue_service.get_nearby_issues(latitude, longitude, radius_km)
        return {"issues": issues, "count": len(issues)}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/issues/{issue_id}")
async def get_issue(issue_id: str):
    """
    Get details of a specific issue

    Args:
        issue_id: The issue's UUID
    """
    try:
        issue = await issue_service.get_issue(issue_id)
        return issue
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/issues/{issue_id}/resolve")
async def resolve_issue(
    issue_id: str,
    resolution_latitude: Optional[float] = Form(None),
    resolution_longitude: Optional[float] = Form(None),
    resolution_file: Optional[UploadFile] = File(None),
    authorization: Optional[str] = None,
):
    """
    Mark an issue as resolved

    Args:
        issue_id: The issue's UUID
        resolution_latitude: Location where cleanup was done
        resolution_longitude: Location where cleanup was done
        resolution_file: (Optional) Photo of the cleaned area
        Authorization: Bearer token in header
    """
    try:
        # Extract user_id from token
        user_id = await get_current_user_id(authorization)

        # Read resolution photo if provided
        resolution_photo_bytes = None
        if resolution_file:
            resolution_photo_bytes = await resolution_file.read()

        # Resolve issue
        updated_issue = await issue_service.resolve_issue(
            issue_id=issue_id,
            resolved_by_user_id=user_id,
            resolution_photo_bytes=resolution_photo_bytes,
            resolution_latitude=resolution_latitude,
            resolution_longitude=resolution_longitude,
        )

        return {"message": "Issue resolved successfully", "issue": updated_issue}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
