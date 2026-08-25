"""
routes/public.py — Unauthenticated landing-page endpoints

Every route here is public by design. The custom OpenAPI hook in main.py marks
all operations as requiring BearerAuth by default, so these are explicitly
opted out with security=[].
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.public_service import PublicService

router = APIRouter(tags=["public"])
public_service = PublicService()


# ---------------------------------------------------------------------------
# Events — public issue feed
# ---------------------------------------------------------------------------


@router.get("/events", openapi_extra={"security": []})
async def get_events(
    status: Optional[str] = Query(None, description="Filter by issue status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Public feed of cleanup events, newest first. No auth required."""
    try:
        result = await public_service.get_events(
            status=status, limit=limit, offset=offset
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Warriors — public directory
# ---------------------------------------------------------------------------


@router.get("/warriors", openapi_extra={"security": []})
async def get_warriors(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Public directory of cleanup warriors, ranked by points. No auth required."""
    try:
        result = await public_service.get_warriors(limit=limit, offset=offset)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/warriors/{user_id}", openapi_extra={"security": []})
async def get_warrior(user_id: str):
    """Public profile for a single warrior. No auth required."""
    try:
        result = await public_service.get_warrior(user_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Stats — landing page counters
# ---------------------------------------------------------------------------


@router.get("/stats", openapi_extra={"security": []})
async def get_platform_stats():
    """Headline platform totals for the landing page. No auth required."""
    try:
        result = await public_service.get_platform_stats()
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
