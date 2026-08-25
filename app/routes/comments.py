"""
routes/comments.py — Issue comment endpoints
"""

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from app.services.comment_service import CommentService
from app.utils.jwt_handler import JWTHandler

router = APIRouter(tags=["comments"])
comment_service = CommentService()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateCommentRequest(BaseModel):
    content: str


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


@router.post("/issues/{issue_id}/comments", status_code=status.HTTP_201_CREATED)
async def create_comment(request: Request, issue_id: str, body: CreateCommentRequest):
    """Add a comment to an issue."""
    user_id = await get_current_user_id(request)
    try:
        result = await comment_service.create_comment(
            user_id=user_id,
            issue_id=issue_id,
            content=body.content,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/issues/{issue_id}/comments")
async def get_issue_comments(
    issue_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Get comments on an issue, newest first.
    No auth required — public endpoint.
    """
    try:
        result = await comment_service.get_issue_comments(
            issue_id=issue_id, limit=limit, offset=offset
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/comments/{comment_id}")
async def delete_comment(request: Request, comment_id: str):
    """Delete a comment. Author or admin only."""
    user_id = await get_current_user_id(request)
    try:
        result = await comment_service.delete_comment(
            user_id=user_id, comment_id=comment_id
        )
        return {"success": True, "data": result}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
