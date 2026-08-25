"""
routes/profile.py — Profile management and personal dashboard
"""

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from typing import Optional
from app.services.profile_service import ProfileService
from app.utils.jwt_handler import JWTHandler

router = APIRouter(tags=["profile"])
profile_service = ProfileService()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    username: Optional[str] = None
    phone: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


async def get_current_user_id(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    parts = auth.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization header"
        )
    try:
        return JWTHandler.get_user_id_from_token(parts[1])
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/users/me")
async def get_my_profile(request: Request):
    """Get the caller's full profile."""
    user_id = await get_current_user_id(request)
    try:
        result = await profile_service.get_profile(user_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/users/me")
async def update_my_profile(request: Request, body: UpdateProfileRequest):
    """
    Update display name, username, or phone.
    Only the fields you send are changed.
    """
    user_id = await get_current_user_id(request)
    try:
        result = await profile_service.update_profile(
            user_id=user_id,
            display_name=body.display_name,
            username=body.username,
            phone=body.phone,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/me/avatar")
async def update_my_avatar(request: Request, file: UploadFile = File(...)):
    """Upload a new avatar image (max 5 MB)."""
    user_id = await get_current_user_id(request)
    try:
        photo_bytes = await file.read()
        result = await profile_service.update_avatar(
            user_id=user_id,
            photo_bytes=photo_bytes,
            content_type=file.content_type,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/me/dashboard")
async def get_my_dashboard(request: Request):
    """
    Personal dashboard: profile summary, headline stats, recent issues,
    recent volunteering, and badges earned.
    """
    user_id = await get_current_user_id(request)
    try:
        result = await profile_service.get_dashboard(user_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
