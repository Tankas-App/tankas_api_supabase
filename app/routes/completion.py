from fastapi import APIRouter, HTTPException, status, Request, UploadFile, File, Form
from typing import Optional, List
from app.schemas.completion_schema import (
    ConfirmParticipationRequest, CompleteIssueRequest,
    VerifyVolunteerListRequest, IssueCompletionResponse, DistributionSummary
)
from app.services.completion_service import CompletionService
from app.utils.jwt_handler import JWTHandler

# Create router
router = APIRouter(tags=["completion"])

# Initialize service
completion_service = CompletionService()


# ============ HELPER FUNCTIONS ============

async def get_current_user_id(request: Request) -> str:
    """Extract user_id from JWT token"""
    auth_header = request.headers.get("authorization")
    
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header"
        )
    
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )
    
    token = parts[1]
    
    try:
        user_id = JWTHandler.get_user_id_from_token(token)
        return user_id
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )


# ============ ENDPOINTS ============

@router.post("/completion/confirm-participation")
async def confirm_participation(
    request: Request,
    confirm_request: ConfirmParticipationRequest
):
    """
    Volunteer confirms they participated in the cleanup
    
    **Authorization:** Bearer token required
    
    Args:
        issue_id: UUID of the issue they worked on
        group_id: UUID of the group they worked with
    
    Returns:
        Confirmation message
    """
    try:
        user_id = await get_current_user_id(request)
        
        result = await completion_service.confirm_participation(
            user_id=user_id,
            issue_id=confirm_request.issue_id,
            group_id=confirm_request.group_id
        )
        
        return result
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/completion/complete-issue",
    response_model=IssueCompletionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"}
    }
)
async def complete_issue(
    request: Request,
    issue_id: str = Form(...),
    group_id: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Leader marks issue as complete and uploads cleanup photo
    
    **Only the group leader can call this endpoint**
    
    **Request:**
    - **issue_id**: UUID of the issue (form data)
    - **group_id**: UUID of the group (form data)
    - **file**: Cleanup/verification photo (JPEG, PNG, or GIF)
    - **Authorization**: Bearer token in header
    
    **Process:**
    1. Verify user is group leader
    2. Upload cleanup photo to Cloudinary
    3. Run AI verification comparing original to cleanup photo
    4. Set status based on AI confidence:
       - >80% confidence → "verified"
       - 50-80% confidence → "pending_review"
       - <50% confidence → "rejected"
    5. Mark issue as resolved
    
    **Response:**
    - Issue completion details with verification status
    - List of all group volunteers awaiting verification
    """
    try:
        user_id = await get_current_user_id(request)
        
        # Read photo file
        photo_bytes = await file.read()
        
        # Validate file
        if len(photo_bytes) > 10 * 1024 * 1024:  # 10MB limit
            raise ValueError("File too large. Maximum 10MB")
        
        if not photo_bytes[:3] in [b'\xff\xd8\xff', b'\x89PN', b'\x47IF']:
            raise ValueError("Invalid file type. Please upload JPEG, PNG, or GIF")
        
        # Complete issue
        result = await completion_service.complete_issue(
            user_id=user_id,
            issue_id=issue_id,
            group_id=group_id,
            photo_bytes=photo_bytes
        )
        
        return IssueCompletionResponse(
            issue_id=result["issue_id"],
            group_id=result["group_id"],
            status=result["status"],
            verification_photo_url=result["verification_photo_url"],
            verification_status=result["verification_status"],
            ai_confidence=result["ai_confidence"],
            message=result["message"],
            volunteers=result["volunteers"]
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/completion/verify-volunteers",
    response_model=DistributionSummary,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"}
    }
)
async def verify_volunteers(
    request: Request,
    verify_request: VerifyVolunteerListRequest
):
    """
    Leader confirms which volunteers actually worked and points are distributed
    
    **Only the group leader can call this endpoint**
    
    **Request:**
    - **issue_id**: UUID of the issue
    - **group_id**: UUID of the group
    - **verified_volunteer_ids**: List of volunteer IDs who showed up and worked
    - **Authorization**: Bearer token in header
    
    **Process:**
    1. Verify user is group leader
    2. Mark specified volunteers as verified
    3. Calculate points based on number of verified volunteers
    4. Distribute points:
       - Each volunteer gets: total_points ÷ verified_count
       - Leader gets: base_points + remainder_bonus
    5. Update user accounts with new points
    6. Increment tasks_completed counter
    
    **Response:**
    - Summary of points distribution
    - Details for each volunteer (verified/not verified, points earned)
    """
    try:
        user_id = await get_current_user_id(request)
        
        result = await completion_service.verify_volunteers(
            user_id=user_id,
            issue_id=verify_request.issue_id,
            group_id=verify_request.group_id,
            verified_volunteer_ids=verify_request.verified_volunteer_ids
        )
        
        return DistributionSummary(
            issue_id=result["issue_id"],
            group_id=result["group_id"],
            total_points_available=result["total_points_available"],
            verified_volunteer_count=result["verified_volunteer_count"],
            points_per_volunteer=result["points_per_volunteer"],
            leader_bonus=result["leader_bonus"],
            distribution=result["distribution"],
            message=result["message"]
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )