"""
routes/pledges.py — Pledging endpoints
"""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from typing import Optional
from app.services.pledge_service import PledgeService
from app.utils.jwt_handler import JWTHandler

router = APIRouter(tags=["pledges"])
pledge_service = PledgeService()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreatePledgeRequest(BaseModel):
    pledge_type: str  # money, equipment, volunteer, other
    description: str  # "GHS 20", "10 trash bags", "I'll bring my truck"
    quantity: int = 1
    amount: Optional[float] = None  # required for money pledges


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


@router.post("/issues/{issue_id}/pledges", status_code=status.HTTP_201_CREATED)
async def create_pledge(
    request: Request,
    issue_id: str,
    body: CreatePledgeRequest,
):
    """
    Pledge money or equipment toward resolving an issue.

    pledge_type options:
    - **money** — GHS donation (requires amount)
    - **equipment** — tools, bags, gloves etc (use description + quantity)
    - **volunteer** — offer to volunteer (description = what you'll do)
    - **other** — anything else
    """
    user_id = await get_current_user_id(request)
    try:
        result = await pledge_service.create_pledge(
            user_id=user_id,
            issue_id=issue_id,
            pledge_type=body.pledge_type,
            description=body.description,
            quantity=body.quantity,
            amount=body.amount,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/issues/{issue_id}/pledges")
async def get_issue_pledges(issue_id: str):
    """
    Get all pledges for an issue.
    Returns summary totals + individual pledge list.
    No auth required — public endpoint.
    """
    try:
        result = await pledge_service.get_issue_pledges(issue_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pledges/{pledge_id}")
async def get_pledge(request: Request, pledge_id: str):
    """Get a single pledge by ID."""
    await get_current_user_id(request)
    try:
        result = await pledge_service.get_pledge(pledge_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pledges/{pledge_id}/fulfil")
async def fulfil_pledge(request: Request, pledge_id: str):
    """
    Mark a pledge as fulfilled.
    Can be done by the pledger themselves or an admin.
    """
    user_id = await get_current_user_id(request)
    try:
        result = await pledge_service.fulfil_pledge(pledge_id, user_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pledges/{pledge_id}")
async def cancel_pledge(request: Request, pledge_id: str):
    """Cancel a pending pledge. Only the pledger can cancel."""
    user_id = await get_current_user_id(request)
    try:
        result = await pledge_service.cancel_pledge(pledge_id, user_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/me/pledges")
async def get_my_pledges(
    request: Request,
    status: Optional[str] = None,
):
    """
    Get current user's pledge history.
    Optional filter: ?status=pending|fulfilled|cancelled
    """
    user_id = await get_current_user_id(request)
    try:
        result = await pledge_service.get_user_pledges(user_id, status)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
