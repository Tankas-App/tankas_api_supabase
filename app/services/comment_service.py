"""
comment_service.py — Comments on issues

Ported from the legacy tankas_app-api. Lets users discuss an issue on its
detail page: who reported it, whether it is still there, coordination chatter.
"""

from app.database import get_connection


MAX_COMMENT_LENGTH = 2000


class CommentService:

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_comment(self, user_id: str, issue_id: str, content: str) -> dict:
        """Add a comment to an issue."""
        content = (content or "").strip()
        if not content:
            raise ValueError("Comment cannot be empty")
        if len(content) > MAX_COMMENT_LENGTH:
            raise ValueError(
                f"Comment is too long (max {MAX_COMMENT_LENGTH} characters)"
            )

        async with get_connection() as conn:

            issue = await conn.fetchrow("SELECT id FROM issues WHERE id=$1", issue_id)
            if not issue:
                raise ValueError("Issue not found")

            comment = await conn.fetchrow(
                """
                INSERT INTO comments (issue_id, user_id, content)
                VALUES ($1, $2, $3)
                RETURNING id, issue_id, user_id, content, created_at
                """,
                issue_id,
                user_id,
                content,
            )

            author = await conn.fetchrow(
                "SELECT username, display_name, avatar_url FROM users WHERE id=$1",
                user_id,
            )

        return {
            "comment_id": str(comment["id"]),
            "issue_id": str(comment["issue_id"]),
            "content": comment["content"],
            "created_at": comment["created_at"],
            "author": {
                "user_id": user_id,
                "username": author["username"],
                "display_name": author["display_name"],
                "avatar_url": author["avatar_url"],
            },
        }

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_issue_comments(
        self, issue_id: str, limit: int = 50, offset: int = 0
    ) -> dict:
        """
        Get comments for an issue, newest first.
        Public — no auth required.
        """
        async with get_connection() as conn:

            issue = await conn.fetchrow("SELECT id FROM issues WHERE id=$1", issue_id)
            if not issue:
                raise ValueError("Issue not found")

            total = await conn.fetchval(
                "SELECT COUNT(*) FROM comments WHERE issue_id=$1", issue_id
            )

            rows = await conn.fetch(
                """
                SELECT c.id, c.content, c.created_at,
                       u.id AS user_id, u.username, u.display_name, u.avatar_url
                FROM comments c
                JOIN users u ON u.id = c.user_id
                WHERE c.issue_id = $1
                ORDER BY c.created_at DESC
                LIMIT $2 OFFSET $3
                """,
                issue_id,
                limit,
                offset,
            )

        return {
            "issue_id": issue_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "comments": [
                {
                    "comment_id": str(r["id"]),
                    "content": r["content"],
                    "created_at": r["created_at"],
                    "author": {
                        "user_id": str(r["user_id"]),
                        "username": r["username"],
                        "display_name": r["display_name"],
                        "avatar_url": r["avatar_url"],
                    },
                }
                for r in rows
            ],
        }

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_comment(self, user_id: str, comment_id: str) -> dict:
        """
        Delete a comment. Only the author or an admin may delete.
        """
        async with get_connection() as conn:

            comment = await conn.fetchrow(
                "SELECT id, user_id FROM comments WHERE id=$1", comment_id
            )
            if not comment:
                raise ValueError("Comment not found")

            role = await conn.fetchval("SELECT role FROM users WHERE id=$1", user_id)
            if str(comment["user_id"]) != str(user_id) and role != "admin":
                raise PermissionError("You can only delete your own comments")

            await conn.execute("DELETE FROM comments WHERE id=$1", comment_id)

        return {"comment_id": comment_id, "deleted": True}
