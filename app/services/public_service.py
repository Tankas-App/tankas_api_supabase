"""
public_service.py — Unauthenticated read-only endpoints for the landing page

Ported from the legacy tankas_app-api, which exposed /events and /warriors so
the marketing site could render activity without requiring a login.

Everything here is deliberately public, so it returns only non-sensitive fields:
no emails, no phone numbers, no roles.
"""

from app.database import get_connection


class PublicService:

    # ------------------------------------------------------------------
    # Events — public issue feed
    # ------------------------------------------------------------------

    async def get_events(
        self, status: str = None, limit: int = 50, offset: int = 0
    ) -> dict:
        """
        Public feed of cleanup events (issues), newest first.
        Optionally filtered by status.
        """
        async with get_connection() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT i.id, i.title, i.description, i.picture_url,
                           i.latitude, i.longitude, i.status, i.difficulty,
                           i.priority, i.points_assigned, i.created_at,
                           u.username, u.display_name, u.avatar_url
                    FROM issues i
                    JOIN users u ON u.id = i.user_id
                    WHERE i.status = $1
                    ORDER BY i.created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    status,
                    limit,
                    offset,
                )
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM issues WHERE status=$1", status
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT i.id, i.title, i.description, i.picture_url,
                           i.latitude, i.longitude, i.status, i.difficulty,
                           i.priority, i.points_assigned, i.created_at,
                           u.username, u.display_name, u.avatar_url
                    FROM issues i
                    JOIN users u ON u.id = i.user_id
                    ORDER BY i.created_at DESC
                    LIMIT $1 OFFSET $2
                    """,
                    limit,
                    offset,
                )
                total = await conn.fetchval("SELECT COUNT(*) FROM issues")

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "events": [
                {
                    "issue_id": str(r["id"]),
                    "title": r["title"],
                    "description": r["description"],
                    "picture_url": r["picture_url"],
                    "latitude": r["latitude"],
                    "longitude": r["longitude"],
                    "status": r["status"],
                    "difficulty": r["difficulty"],
                    "priority": r["priority"],
                    "points_assigned": r["points_assigned"],
                    "created_at": r["created_at"],
                    "reported_by": {
                        "username": r["username"],
                        "display_name": r["display_name"],
                        "avatar_url": r["avatar_url"],
                    },
                }
                for r in rows
            ],
        }

    # ------------------------------------------------------------------
    # Warriors — public cleanup-warrior directory
    # ------------------------------------------------------------------

    async def get_warriors(self, limit: int = 50, offset: int = 0) -> dict:
        """
        Public directory of cleanup warriors, ranked by points.

        Similar to /leaderboards but intentionally simpler and unauthenticated:
        a flat directory for the landing page rather than a ranked competition
        view with cache, periods, and regions.
        """
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, username, display_name, avatar_url, total_points,
                       badge_tier, issues_reported, tasks_completed,
                       total_kg_collected, created_at
                FROM users
                WHERE role <> 'banned'
                ORDER BY total_points DESC, created_at ASC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE role <> 'banned'"
            )

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "warriors": [
                {
                    "user_id": str(r["id"]),
                    "rank": offset + idx + 1,
                    "username": r["username"],
                    "display_name": r["display_name"],
                    "avatar_url": r["avatar_url"],
                    "total_points": r["total_points"],
                    "badge_tier": r["badge_tier"],
                    "issues_reported": r["issues_reported"],
                    "tasks_completed": r["tasks_completed"],
                    "total_kg_collected": float(r["total_kg_collected"] or 0),
                    "joined_at": r["created_at"],
                }
                for idx, r in enumerate(rows)
            ],
        }

    async def get_warrior(self, user_id: str) -> dict:
        """Public profile for a single warrior."""
        async with get_connection() as conn:
            r = await conn.fetchrow(
                """
                SELECT id, username, display_name, avatar_url, total_points,
                       badge_tier, issues_reported, tasks_completed,
                       volunteer_hours, volunteer_streak, total_kg_collected,
                       created_at
                FROM users
                WHERE id=$1 AND role <> 'banned'
                """,
                user_id,
            )
            if not r:
                raise ValueError("Warrior not found")

            badges = await conn.fetch(
                "SELECT badge_type, earned_at FROM user_badges WHERE user_id=$1 ORDER BY earned_at DESC",
                user_id,
            )

            rank = await conn.fetchval(
                """
                SELECT COUNT(*) + 1 FROM users
                WHERE total_points > $1 AND role <> 'banned'
                """,
                r["total_points"] or 0,
            )

        return {
            "user_id": str(r["id"]),
            "rank": rank,
            "username": r["username"],
            "display_name": r["display_name"],
            "avatar_url": r["avatar_url"],
            "total_points": r["total_points"],
            "badge_tier": r["badge_tier"],
            "issues_reported": r["issues_reported"],
            "tasks_completed": r["tasks_completed"],
            "volunteer_hours": r["volunteer_hours"],
            "volunteer_streak": r["volunteer_streak"],
            "total_kg_collected": float(r["total_kg_collected"] or 0),
            "joined_at": r["created_at"],
            "badges": [
                {"badge_type": b["badge_type"], "earned_at": b["earned_at"]}
                for b in badges
            ],
        }

    # ------------------------------------------------------------------
    # Stats — landing page counters
    # ------------------------------------------------------------------

    async def get_platform_stats(self) -> dict:
        """Headline totals for the landing page."""
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                  (SELECT COUNT(*) FROM users)                            AS total_users,
                  (SELECT COUNT(*) FROM issues)                           AS total_issues,
                  (SELECT COUNT(*) FROM issues WHERE status='resolved')   AS resolved_issues,
                  (SELECT COUNT(*) FROM issues WHERE status='open')       AS open_issues,
                  (SELECT COALESCE(SUM(total_kg_collected),0) FROM users) AS total_kg_collected
                """
            )

        return {
            "total_users": row["total_users"],
            "total_issues": row["total_issues"],
            "resolved_issues": row["resolved_issues"],
            "open_issues": row["open_issues"],
            "total_kg_collected": float(row["total_kg_collected"] or 0),
        }
