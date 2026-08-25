"""
routes/rewards.py — Reward catalogue and redemption endpoints
"""

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from typing import Optional
from app.services.reward_service import RewardService
from app.utils.jwt_handler import JWTHandler

router = APIRouter(tags=["rewards"])
reward_service = RewardService()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateRewardRequest(BaseModel):
    name: str
    description: Optional[str] = None
    cost_in_points: int
    reward_type: Optional[str] = "merch"  # merch, airtime, voucher, other


class RedeemRewardRequest(BaseModel):
    quantity: int = 1


class SetAvailabilityRequest(BaseModel):
    is_available: bool


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
# Catalogue
# ---------------------------------------------------------------------------


@router.get("/rewards")
async def list_rewards(
    available_only: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List the reward catalogue, cheapest first.
    No auth required — public endpoint.
    """
    try:
        result = await reward_service.list_rewards(
            available_only=available_only, limit=limit, offset=offset
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rewards/me/redemptions")
async def get_my_redemptions(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get the caller's redemption history."""
    user_id = await get_current_user_id(request)
    try:
        result = await reward_service.get_my_redemptions(
            user_id=user_id, limit=limit, offset=offset
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rewards/{reward_id}")
async def get_reward(reward_id: str):
    """Get a single reward. No auth required."""
    try:
        result = await reward_service.get_reward(reward_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Redemption
# ---------------------------------------------------------------------------


@router.post("/rewards/{reward_id}/redeem", status_code=status.HTTP_201_CREATED)
async def redeem_reward(request: Request, reward_id: str, body: RedeemRewardRequest):
    """
    Redeem a catalogue reward using points.

    Distinct from /payments/redeem-points, which converts points to cash.
    """
    user_id = await get_current_user_id(request)
    try:
        result = await reward_service.redeem_reward(
            user_id=user_id, reward_id=reward_id, quantity=body.quantity
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


@router.post("/rewards", status_code=status.HTTP_201_CREATED)
async def create_reward(request: Request, body: CreateRewardRequest):
    """Create a reward. Admin only."""
    user_id = await get_current_user_id(request)
    try:
        result = await reward_service.create_reward(
            user_id=user_id,
            name=body.name,
            description=body.description,
            cost_in_points=body.cost_in_points,
            reward_type=body.reward_type,
        )
        return {"success": True, "data": result}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/rewards/{reward_id}/availability")
async def set_availability(
    request: Request, reward_id: str, body: SetAvailabilityRequest
):
    """Enable or disable a reward. Admin only."""
    user_id = await get_current_user_id(request)
    try:
        result = await reward_service.set_availability(
            user_id=user_id, reward_id=reward_id, is_available=body.is_available
        )
        return {"success": True, "data": result}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
