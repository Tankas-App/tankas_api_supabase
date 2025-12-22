from fastapi import APIRouter, HTTPException, status, Request
from typing import Optional
from app.services.leaderboard_service import LeaderboardService
from app.utils.jwt_handler import JWTHandler
import asyncio

# Create router
router = APIRouter(tags=["leaderboards"])

# Initialize service
leaderboard_service = LeaderboardService()


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


# ============ LEADERBOARD INFO ENDPOINTS ============

@router.get(
    "/leaderboards",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"}
    }
)
async def list_leaderboards(request: Request):
    """
    Get list of all available leaderboards
    
    **Authorization:** Bearer token required
    
    **Response:**
    - Available leaderboard types with descriptions
    """
    try:
        await get_current_user_id(request)
        
        leaderboards = LeaderboardService.get_available_leaderboards()
        
        return {
            "success": True,
            "leaderboards": leaderboards
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============ MAIN LEADERBOARD ENDPOINTS ============

@router.get(
    "/leaderboards/{leaderboard_type}",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"}
    }
)
async def get_leaderboard(
    request: Request,
    leaderboard_type: str,
    location_type: str = "global",
    location_value: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """
    Get a leaderboard with rankings
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **leaderboard_type**: Type of ranking (points, issues_reported, collections, kg_collected, volunteer_hours)
    
    **Query Parameters:**
    - **location_type**: "global", "region", or "community" (default: global)
    - **location_value**: Region name OR "lat,lng,radius_km" for community (e.g., "5.6037,-0.1870,15")
    - **limit**: Number of results (max 100, default 100)
    - **offset**: Pagination offset (default 0)
    
    **Examples:**
    - Global points: `/leaderboards/points?location_type=global`
    - Accra region: `/leaderboards/points?location_type=region&location_value=Accra%20Metropolitan`
    - Community (15km): `/leaderboards/points?location_type=community&location_value=5.6037,-0.1870,15`
    
    **Response:**
    - Leaderboard with ranked users
    """
    try:
        await get_current_user_id(request)
        
        result = await leaderboard_service.get_leaderboard(
            leaderboard_type=leaderboard_type,
            location_type=location_type,
            location_value=location_value,
            limit=limit,
            offset=offset
        )
        
        return {
            "success": True,
            "data": result
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/leaderboards/{leaderboard_type}/context",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"}
    }
)
async def get_leaderboard_context(
    request: Request,
    leaderboard_type: str,
    latitude: float,
    longitude: float,
    location_type: str = "global",
    location_value: Optional[str] = None,
    context_size: int = 5
):
    """
    Get leaderboard context for current user
    
    Returns: Top 10 global + user's current rank + neighbors
    
    **Authorization:** Bearer token required (user must be authenticated)
    
    **Path Parameters:**
    - **leaderboard_type**: Type of ranking
    
    **Query Parameters:**
    - **latitude**: User's current latitude (for real-time location)
    - **longitude**: User's current longitude (for real-time location)
    - **location_type**: "global", "region", or "community" (default: global)
    - **location_value**: Region name or "lat,lng,radius_km" for community
    - **context_size**: How many neighbors to show above/below (default 5)
    
    **Example:**
    - `/leaderboards/points/context?latitude=5.6037&longitude=-0.1870&location_type=community&location_value=5.6037,-0.1870,15&context_size=5`
    
    **Response:**
    - Top 10 global ranking
    - User's current rank
    - 5 users above + 5 users below
    - User's badge info
    """
    try:
        user_id = await get_current_user_id(request)
        
        # Use real-time GPS to determine community location if needed
        if location_type == "community" and not location_value:
            location_value = f"{latitude},{longitude},15"
        
        result = await leaderboard_service.get_leaderboard_context(
            user_id=user_id,
            leaderboard_type=leaderboard_type,
            location_type=location_type,
            location_value=location_value,
            context_size=context_size
        )
        
        return {
            "success": True,
            "data": result
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/users/{user_id}/rank",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        404: {"description": "Not found"},
        500: {"description": "Server error"}
    }
)
async def get_user_rank(
    request: Request,
    user_id: str,
    leaderboard_type: str = "points",
    location_type: str = "global",
    location_value: Optional[str] = None
):
    """
    Get a specific user's rank on a leaderboard
    
    This always returns fresh data (not cached) for accuracy
    
    **Authorization:** Bearer token required
    
    **Path Parameters:**
    - **user_id**: UUID of user to get rank for
    
    **Query Parameters:**
    - **leaderboard_type**: Type of ranking (default: points)
    - **location_type**: "global", "region", or "community" (default: global)
    - **location_value**: Region name or coordinates
    
    **Response:**
    - User's rank, percentile, and metric value
    """
    try:
        await get_current_user_id(request)
        
        result = await leaderboard_service.get_user_rank(
            user_id=user_id,
            leaderboard_type=leaderboard_type,
            location_type=location_type,
            location_value=location_value
        )
        
        return {
            "success": True,
            "data": result
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============ ADMIN ENDPOINTS ============

@router.post(
    "/admin/weekly-badges-reset",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthorized - admin only"},
        500: {"description": "Server error"}
    }
)
async def manual_weekly_badges_reset(request: Request):
    """
    Manually trigger weekly badge reset (Admin only)
    
    **Authorization:** Bearer token required (admin role only)
    
    **Process:**
    1. Invalidate all previous weekly badges
    2. Recalculate weekly badges:
       - Momentum: 100+ points this week
       - On Fire: 3+ cleanups this week
       - Rising Star: Top 10 by points + activities this week
    3. Return count of badges awarded
    
    **Response:**
    - Count of each badge type awarded
    """
    try:
        user_id = await get_current_user_id(request)
        
        # TODO: Check if user has admin role
        # For now, allow any authenticated user
        # In production, add role check here:
        # if not await is_admin(user_id):
        #     raise HTTPException(403, "Admin access required")
        
        result = await leaderboard_service.reset_weekly_badges()
        
        return {
            "success": True,
            "message": "Weekly badges reset completed",
            "data": result
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/admin/schedule-weekly-badges",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthorized - admin only"},
        500: {"description": "Server error"}
    }
)
async def schedule_weekly_badges(request: Request):
    """
    Setup automatic weekly badge reset (Admin only)
    
    **Authorization:** Bearer token required (admin role only)
    
    **Note:**
    This endpoint sets up a scheduled task that runs every Monday at 00:00 UTC.
    In production, use a task scheduler like APScheduler, Celery, or AWS Lambda.
    
    For now, this is a placeholder. Implementation depends on your deployment:
    
    **Option 1: APScheduler (if using FastAPI directly)**
    ```python
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(leaderboard_service.reset_weekly_badges, 'cron', day_of_week='mon', hour=0)
    scheduler.start()
    ```
    
    **Option 2: Celery (for distributed tasks)**
    ```python
    @app.celery.task
    def reset_weekly_badges_task():
        await leaderboard_service.reset_weekly_badges()
    
    # Schedule in celery beat
    ```
    
    **Option 3: External cron (simplest)**
    - Call the manual endpoint via cron job every Monday 00:00
    ```bash
    0 0 * * 1 curl -X POST https://api.tankas.app/api/admin/schedule-weekly-badges
    ```
    
    **Response:**
    - Confirmation that scheduling is set up
    """
    try:
        user_id = await get_current_user_id(request)
        
        # TODO: Check admin role
        
        return {
            "success": True,
            "message": "Weekly badge scheduling configured",
            "details": {
                "schedule": "Every Monday at 00:00 UTC",
                "badge_types": ["rising_star", "momentum", "on_fire"],
                "note": "Setup method depends on your deployment platform"
            }
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )