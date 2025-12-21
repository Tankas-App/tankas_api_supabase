from fastapi import APIRouter, HTTPException, status, Request
from typing import Optional, List
from app.schemas.volunteer_schema import (
    JoinIssueRequest, JoinIssueResponse, TransferLeadershipRequest,
    VerifyVolunteersRequest, GroupMemberListResponse, VolunteerProfileResponse
)
from app.services.volunteer_service import VolunteerService
from app.utils.jwt_handler import JWTHandler

# Create router
router = APIRouter(tags=["volunteers"])

# Initialize service
volunteer_service = VolunteerService()


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

@router.post(
    "/volunteers",
    response_model=JoinIssueResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"}
    }
)
async def join_issue(
    request: Request,
    join_request: JoinIssueRequest
):
    """
    Volunteer joins an issue
    
    **Request:**
    - **issue_id**: UUID of the issue to volunteer for
    - **solo_work**: (Optional) Whether working alone (default: false)
    - **equipment_needed**: (Optional) List of equipment IDs bringing
    - **Authorization**: Bearer token in header
    
    **Response:**
    - Volunteer ID, group ID, leader status, and message
    
    **Process:**
    1. Verify user is authenticated
    2. Check if issue exists
    3. If no group exists for issue → Create group, user becomes leader
    4. If group exists → Join as regular member
    5. Create volunteer record
    """
    try:
        # Extract user_id from token
        user_id = await get_current_user_id(request)
        
        # Join issue
        result = await volunteer_service.join_issue(
            user_id=user_id,
            issue_id=join_request.issue_id,
            solo_work=join_request.solo_work,
            equipment_needed=join_request.equipment_needed
        )
        
        return JoinIssueResponse(
            volunteer_id=result["volunteer_id"],
            issue_id=result["issue_id"],
            group_id=result["group_id"],
            is_leader=result["is_leader"],
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


@router.get("/volunteers/groups/{group_id}")
async def get_group_members(group_id: str):
    """
    Get all members of a volunteer group
    
    Args:
        group_id: UUID of the group
    
    Returns:
        Group details with list of members
    """
    try:
        result = await volunteer_service.get_group_members(group_id)
        return result
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/volunteers/profile/{user_id}", response_model=VolunteerProfileResponse)
async def get_volunteer_profile(user_id: str):
    """
    Get complete volunteer profile with history
    
    Args:
        user_id: UUID of the user
    
    Returns:
        User profile with full volunteering history
    """
    try:
        result = await volunteer_service.get_volunteer_profile(user_id)
        return result
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/volunteers/{volunteer_id}/transfer-leadership")
async def transfer_leadership(
    request: Request,
    volunteer_id: str,
    transfer_request: TransferLeadershipRequest
):
    """
    Transfer leadership to another group member
    
    **Only the current leader can transfer leadership**
    
    Args:
        volunteer_id: Current leader's volunteer ID
        transfer_request.new_leader_volunteer_id: Volunteer ID to transfer to
    
    Returns:
        Confirmation message with new leader details
    """
    try:
        # Extract user_id (verify they're authenticated)
        user_id = await get_current_user_id(request)
        
        # Transfer leadership
        result = await volunteer_service.transfer_leadership(
            current_leader_volunteer_id=volunteer_id,
            new_leader_volunteer_id=transfer_request.new_leader_volunteer_id
        )
        
        return {
            "message": result["message"],
            "new_leader_id": result["new_leader_id"],
            "new_leader_name": result["new_leader_name"]
        }
    
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


@router.post("/volunteers/my-profile")
async def get_my_profile(request: Request):
    """
    Get current user's volunteer profile
    
    **Authorization:** Bearer token required
    
    Returns:
        Current user's profile with volunteering history
    """
    try:
        # Extract user_id from token
        user_id = await get_current_user_id(request)
        
        # Get profile
        result = await volunteer_service.get_volunteer_profile(user_id)
        
        return result
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )