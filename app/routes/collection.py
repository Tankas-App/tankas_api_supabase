from fastapi import APIRouter, HTTPException, status, Request, UploadFile, File, Form
from typing import Optional, List
from app.services.collection_service import CollectionsService
from app.utils.jwt_handler import JWTHandler

# Create router
router = APIRouter(tags=["collections"])

# Initialize service
collections_service = CollectionsService()


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


# ============ DESTINATION ENDPOINTS ============

@router.post(
    "/destinations",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"}
    }
)
async def create_destination(
    request: Request,
    name: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    address: str = Form(...),
    description: Optional[str] = Form(None),
    contact_person: Optional[str] = Form(None),
    contact_phone: Optional[str] = Form(None),
    operating_hours: Optional[str] = Form(None)
):
    """
    Create a new collection destination (Admin only)
    
    **Authorization:** Bearer token required
    
    **Request (Form Data):**
    - **name**: Destination name (required)
    - **latitude**: GPS latitude (required)
    - **longitude**: GPS longitude (required)
    - **address**: Physical address (required)
    - **description**: Description of destination (optional)
    - **contact_person**: Contact person name (optional)
    - **contact_phone**: Contact phone number (optional)
    - **operating_hours**: Operating hours (optional)
    
    **Response:**
    - Created destination details with ID
    """
    try:
        user_id = await get_current_user_id(request)
        
        result = await collections_service.create_destination(
            name=name,
            latitude=latitude,
            longitude=longitude,
            address=address,
            description=description,
            contact_person=contact_person,
            contact_phone=contact_phone,
            operating_hours=operating_hours
        )
        
        return {
            "success": True,
            "data": result
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


@router.get(
    "/destinations/nearby",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"}
    }
)
async def get_nearby_destinations(
    request: Request,
    latitude: float,
    longitude: float,
    radius_km: float = 5.0
):
    """
    Get collection destinations near a location
    
    **Authorization:** Bearer token required
    
    **Query Parameters:**
    - **latitude**: Issue latitude (required)
    - **longitude**: Issue longitude (required)
    - **radius_km**: Search radius in km (optional, default: 5.0)
    
    **Response:**
    - List of nearby destinations sorted by distance with distance_km field
    """
    try:
        user_id = await get_current_user_id(request)
        
        result = await collections_service.get_nearby_destinations(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km
        )
        
        return {
            "success": True,
            "data": result
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/issues/{issue_id}/assign-destination",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        404: {"description": "Not found"},
        500: {"description": "Server error"}
    }
)
async def assign_destination_to_issue(
    request: Request,
    issue_id: str,
    destination_id: str = Form(...)
):
    """
    Assign a destination to a resolved issue (Admin only)
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **issue_id**: UUID of the issue (required)
    
    **Request (Form Data):**
    - **destination_id**: UUID of the destination (required)
    
    **Response:**
    - Confirmation with issue and destination details
    """
    try:
        user_id = await get_current_user_id(request)
        
        result = await collections_service.assign_destination_to_issue(
            issue_id=issue_id,
            destination_id=destination_id
        )
        
        return {
            "success": True,
            "data": result
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


# ============ COLLECTION WORKFLOW ENDPOINTS ============

@router.post(
    "/start/{issue_id}",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        404: {"description": "Not found"},
        500: {"description": "Server error"}
    }
)
async def start_collection(
    request: Request,
    issue_id: str
):
    """
    Start collecting garbage from a resolved issue
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **issue_id**: UUID of the issue to collect from (required)
    
    **Process:**
    1. Verify issue exists and is resolved
    2. Verify issue has destination assigned
    3. Create collection record with status "in_progress"
    
    **Response:**
    - Collection ID and confirmation message
    """
    try:
        user_id = await get_current_user_id(request)
        
        result = await collections_service.start_collection(
            user_id=user_id,
            issue_id=issue_id
        )
        
        return {
            "success": True,
            "data": result
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


@router.post(
    "/submit/{issue_id}",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        404: {"description": "Not found"},
        500: {"description": "Server error"}
    }
)
async def submit_collection(
    request: Request,
    issue_id: str,
    destination_id: str = Form(...),
    photo: UploadFile = File(...),
    notes: Optional[str] = Form(None),
    quantity_kg: Optional[float] = Form(None)
):
    """
    Submit collected garbage with photo and notes
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **issue_id**: UUID of the issue (required)
    
    **Request (Form Data):**
    - **destination_id**: UUID of destination (required)
    - **photo**: Photo file of collected garbage (required, JPEG/PNG/GIF)
    - **notes**: Notes about collection (optional)
    - **quantity_kg**: Estimated weight in kg (optional)
    
    **Process:**
    1. Find active collection record
    2. Upload photo to Cloudinary
    3. Update collection with photo, notes, quantity
    4. Set status to "submitted"
    
    **Response:**
    - Collection details with photo URL and confirmation message
    """
    try:
        user_id = await get_current_user_id(request)
        
        # Read photo file
        photo_bytes = await photo.read()
        
        # Validate file
        if len(photo_bytes) > 10 * 1024 * 1024:  # 10MB limit
            raise ValueError("File too large. Maximum 10MB")
        
        if not photo_bytes[:3] in [b'\xff\xd8\xff', b'\x89PN', b'\x47IF']:
            raise ValueError("Invalid file type. Please upload JPEG, PNG, or GIF")
        
        result = await collections_service.submit_collection(
            user_id=user_id,
            issue_id=issue_id,
            destination_id=destination_id,
            photo_bytes=photo_bytes,
            notes=notes,
            quantity_kg=quantity_kg
        )
        
        return {
            "success": True,
            "data": result
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


@router.post(
    "/verify/{collection_id}",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        404: {"description": "Not found"},
        500: {"description": "Server error"}
    }
)
async def verify_delivery(
    request: Request,
    collection_id: str,
    destination_id: str = Form(...),
    proof_photo: UploadFile = File(...),
    verified: bool = Form(True),
    notes: Optional[str] = Form(None),
    quantity_kg: Optional[float] = Form(None)
):
    """
    Verify delivery and calculate payment (Destination staff/Admin only)
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **collection_id**: UUID of collection to verify (required)
    
    **Request (Form Data):**
    - **destination_id**: UUID of destination (required)
    - **proof_photo**: Delivery proof photo (required, JPEG/PNG/GIF)
    - **verified**: Whether to approve (optional, default: true)
    - **quantity_kg**: Actual measured weight in kg (optional)
    - **notes**: Verification notes or rejection reason (optional)
    
    **Process:**
    1. Upload proof photo to Cloudinary
    2. If verified:
       - Calculate payment: quantity_kg × PAYMENT_PER_KG
       - Calculate points: quantity_kg × POINTS_PER_KG
       - Award points to collector
       - Set status to "verified"
    3. If rejected:
       - Set status to "rejected"
       - No payment or points awarded
    
    **Response:**
    - Payment confirmation with amount, points, and delivery proof
    """
    try:
        user_id = await get_current_user_id(request)
        
        # Read proof photo file
        photo_bytes = await proof_photo.read()
        
        # Validate file
        if len(photo_bytes) > 10 * 1024 * 1024:  # 10MB limit
            raise ValueError("File too large. Maximum 10MB")
        
        if not photo_bytes[:3] in [b'\xff\xd8\xff', b'\x89PN', b'\x47IF']:
            raise ValueError("Invalid file type. Please upload JPEG, PNG, or GIF")
        
        result = await collections_service.verify_delivery(
            collection_id=collection_id,
            destination_id=destination_id,
            photo_bytes=photo_bytes,
            verified=verified,
            notes=notes,
            quantity_kg=quantity_kg
        )
        
        return {
            "success": True,
            "data": result
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


# ============ RETRIEVAL ENDPOINTS ============

@router.get(
    "/collections/{collection_id}",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthorized"},
        404: {"description": "Not found"},
        500: {"description": "Server error"}
    }
)
async def get_collection(
    request: Request,
    collection_id: str
):
    """
    Get details of a specific collection
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **collection_id**: UUID of collection (required)
    
    **Response:**
    - Full collection details with issue, destination, and collector info
    """
    try:
        user_id = await get_current_user_id(request)
        
        result = await collections_service.get_collection_by_id(collection_id)
        
        return {
            "success": True,
            "data": result
        }
    
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


@router.get(
    "/collectors/{user_id}/statistics",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"}
    }
)
async def get_collector_stats(
    request: Request,
    user_id: str
):
    """
    Get collection statistics for a specific collector
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **user_id**: UUID of collector (required)
    
    **Response:**
    - Total collections, verified count, kg collected, earnings (GHS), points earned
    - Breakdown by status (in_progress, submitted, verified, rejected)
    """
    try:
        current_user_id = await get_current_user_id(request)
        
        result = await collections_service.get_collector_statistics(user_id)
        
        return {
            "success": True,
            "data": result
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/destinations/{destination_id}/collections",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"}
    }
)
async def get_destination_collections(
    request: Request,
    destination_id: str,
    status: Optional[str] = None
):
    """
    Get all collections for a destination
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **destination_id**: UUID of destination (required)
    
    **Query Parameters:**
    - **status**: Filter by status (optional) - submitted, verified, rejected, in_progress
    
    **Response:**
    - List of collections with enriched collector information
    """
    try:
        user_id = await get_current_user_id(request)
        
        result = await collections_service.get_destination_collections(
            destination_id=destination_id,
            status_filter=status
        )
        
        return {
            "success": True,
            "data": result
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/destinations/{destination_id}/pending-verifications",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"}
    }
)
async def get_pending_verifications(
    request: Request,
    destination_id: str
):
    """
    Get collections awaiting verification at a destination
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **destination_id**: UUID of destination (required)
    
    **Response:**
    - List of submitted collections awaiting verification, ordered by submission time (oldest first)
    - Includes collector name and issue title for each collection
    """
    try:
        user_id = await get_current_user_id(request)
        
        result = await collections_service.get_pending_verifications(destination_id)
        
        return {
            "success": True,
            "data": result
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============ MANAGEMENT ENDPOINTS ============

@router.delete(
    "/collections/{collection_id}/cancel",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        404: {"description": "Not found"},
        500: {"description": "Server error"}
    }
)
async def cancel_collection(
    request: Request,
    collection_id: str
):
    """
    Cancel an in-progress collection
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **collection_id**: UUID of collection to cancel (required)
    
    **Process:**
    1. Verify user owns the collection
    2. Verify collection is "in_progress" status
    3. Mark collection as "cancelled"
    
    **Response:**
    - Cancellation confirmation
    """
    try:
        user_id = await get_current_user_id(request)
        
        result = await collections_service.cancel_collection(
            collection_id=collection_id,
            user_id=user_id
        )
        
        return {
            "success": True,
            "data": result
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


@router.delete(
    "/destinations/{destination_id}",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        404: {"description": "Not found"},
        500: {"description": "Server error"}
    }
)
async def delete_destination(
    request: Request,
    destination_id: str
):
    """
    Delete a destination (Admin only, no active collections allowed)
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **destination_id**: UUID of destination to delete (required)
    
    **Validation:**
    - Cannot delete if destination has active collections (in_progress or submitted status)
    
    **Response:**
    - Deletion confirmation
    """
    try:
        user_id = await get_current_user_id(request)
        
        result = await collections_service.delete_destination(destination_id)
        
        return {
            "success": True,
            "data": result
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