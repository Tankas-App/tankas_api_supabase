"""
routes/admin.py — Admin dashboard endpoints
All routes require admin role.
"""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from typing import Optional
from app.services.admin_service import AdminService
from app.utils.jwt_handler import JWTHandler
from app.database import get_connection

router = APIRouter(tags=["admin"])
admin_service = AdminService()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BanUserRequest(BaseModel):
    reason: str


class VerifyIssueRequest(BaseModel):
    approved: bool
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Admin auth middleware
# ---------------------------------------------------------------------------


async def require_admin(request: Request) -> str:
    """Extract user_id from token and verify admin role."""
    auth = request.headers.get("authorization", "")
    parts = auth.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization header"
        )

    try:
        user_id = JWTHandler.get_user_id_from_token(parts[1])
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    async with get_connection() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE id=$1", user_id)

    if not user or user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required. Contact support to request admin privileges.",
        )

    return user_id


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


@router.get("/admin/overview")
async def get_overview(request: Request):
    """System-wide stats: users, issues, collections, payments."""
    await require_admin(request)
    try:
        return {"success": True, "data": await admin_service.get_overview()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


@router.get("/admin/users")
async def list_users(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    search: Optional[str] = None,
    role: Optional[str] = None,
):
    """Paginated user list. Filter by search term or role."""
    await require_admin(request)
    try:
        result = await admin_service.list_users(
            limit=limit, offset=offset, search=search, role=role
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/users/{user_id}")
async def get_user_detail(request: Request, user_id: str):
    """Full user profile including activity, badges, payments."""
    await require_admin(request)
    try:
        return {"success": True, "data": await admin_service.get_user_detail(user_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/users/{user_id}/ban")
async def ban_user(request: Request, user_id: str, body: BanUserRequest):
    """Ban a user. Requires a reason for the audit log."""
    admin_id = await require_admin(request)
    try:
        result = await admin_service.ban_user(admin_id, user_id, body.reason)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/users/{user_id}/unban")
async def unban_user(request: Request, user_id: str):
    """Restore a banned user's access."""
    admin_id = await require_admin(request)
    try:
        result = await admin_service.unban_user(admin_id, user_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/users/{user_id}/make-admin")
async def make_admin(request: Request, user_id: str):
    """Promote a user to admin role."""
    await require_admin(request)
    try:
        async with get_connection() as conn:
            user = await conn.fetchrow(
                "SELECT username FROM users WHERE id=$1", user_id
            )
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            await conn.execute(
                "UPDATE users SET role='admin', updated_at=NOW() WHERE id=$1",
                user_id,
            )
        return {
            "success": True,
            "data": {
                "user_id": user_id,
                "username": user["username"],
                "role": "admin",
                "message": f"{user['username']} is now an admin.",
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Issue moderation
# ---------------------------------------------------------------------------


@router.get("/admin/issues/pending")
async def get_pending_issues(
    request: Request,
    limit: int = 20,
    offset: int = 0,
):
    """Issues awaiting manual review."""
    await require_admin(request)
    try:
        result = await admin_service.get_pending_verifications(
            limit=limit, offset=offset
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/issues/{issue_id}/verify")
async def verify_issue(request: Request, issue_id: str, body: VerifyIssueRequest):
    """Manually approve or reject an issue report."""
    admin_id = await require_admin(request)
    try:
        result = await admin_service.verify_issue(
            admin_id=admin_id,
            issue_id=issue_id,
            approved=body.approved,
            notes=body.notes,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ClassifyIssueRequest(BaseModel):
    difficulty: str  # easy, medium, hard
    priority: str = "medium"  # low, medium, high
    approved: bool
    notes: Optional[str] = None


@router.post("/admin/issues/{issue_id}/classify")
async def classify_issue(request: Request, issue_id: str, body: ClassifyIssueRequest):
    """
    Manually classify a pending_review issue.
    Set difficulty, approve (→ open) or reject it.
    """
    admin_id = await require_admin(request)
    try:
        from app.services.issue_service import IssueService

        result = await IssueService().admin_classify_issue(
            issue_id=issue_id,
            admin_id=admin_id,
            difficulty=body.difficulty,
            priority=body.priority,
            approved=body.approved,
            notes=body.notes,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/issues/pending-review")
async def get_pending_review_issues(
    request: Request,
    limit: int = 20,
    offset: int = 0,
):
    """Issues where AI confidence was too low — need admin classification."""
    await require_admin(request)
    try:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT i.*, u.username, u.email
                FROM issues i
                JOIN users u ON u.id = i.user_id
                WHERE i.status = 'pending_review'
                ORDER BY i.created_at ASC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM issues WHERE status='pending_review'"
            )
        return {
            "success": True,
            "data": {
                "issues": [
                    {
                        "id": str(r["id"]),
                        "title": r["title"],
                        "description": r["description"],
                        "picture_url": r["picture_url"],
                        "latitude": r["latitude"],
                        "longitude": r["longitude"],
                        "priority": r["priority"],
                        "reporter": r["username"],
                        "created_at": r["created_at"].isoformat(),
                    }
                    for r in rows
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
