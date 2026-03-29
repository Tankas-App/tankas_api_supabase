"""
admin_service.py — Admin dashboard and moderation tools
"""

from app.database import get_connection
from app.services.email_service import EmailService
from datetime import datetime
from typing import Optional
import json


class AdminService:

    def __init__(self):
        self.email_service = EmailService()

    # ------------------------------------------------------------------
    # System overview
    # ------------------------------------------------------------------

    async def get_overview(self) -> dict:
        """Return high-level system stats for the admin dashboard."""

        async with get_connection() as conn:

            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            total_issues = await conn.fetchval("SELECT COUNT(*) FROM issues")
            open_issues = await conn.fetchval(
                "SELECT COUNT(*) FROM issues WHERE status='open'"
            )
            resolved_issues = await conn.fetchval(
                "SELECT COUNT(*) FROM issues WHERE status='resolved'"
            )
            total_volunteers = await conn.fetchval("SELECT COUNT(*) FROM volunteers")
            total_collections = await conn.fetchval("SELECT COUNT(*) FROM collections")
            verified_collections = await conn.fetchval(
                "SELECT COUNT(*) FROM collections WHERE status='verified'"
            )
            total_points_awarded = await conn.fetchval(
                "SELECT COALESCE(SUM(points_earned), 0) FROM user_activity_log"
            )
            total_payments = await conn.fetchval("SELECT COUNT(*) FROM payments")
            total_ghs_paid = await conn.fetchval(
                "SELECT COALESCE(SUM(amount_ghs), 0) FROM payments WHERE status='completed'"
            )

            # New users this week
            new_users_this_week = await conn.fetchval(
                """
                SELECT COUNT(*) FROM users
                WHERE created_at >= NOW() - INTERVAL '7 days'
                """
            )

            # Issues reported this week
            issues_this_week = await conn.fetchval(
                """
                SELECT COUNT(*) FROM issues
                WHERE created_at >= NOW() - INTERVAL '7 days'
                """
            )

            # Badge tier breakdown
            badge_counts = await conn.fetch(
                """
                SELECT badge_tier, COUNT(*) as count
                FROM users
                GROUP BY badge_tier
                """
            )

        return {
            "users": {
                "total": total_users,
                "new_this_week": new_users_this_week,
                "by_badge_tier": {
                    row["badge_tier"]: row["count"] for row in badge_counts
                },
            },
            "issues": {
                "total": total_issues,
                "open": open_issues,
                "resolved": resolved_issues,
                "this_week": issues_this_week,
            },
            "volunteers": {
                "total_records": total_volunteers,
            },
            "collections": {
                "total": total_collections,
                "verified": verified_collections,
            },
            "points": {
                "total_awarded": int(total_points_awarded or 0),
            },
            "payments": {
                "total_transactions": total_payments,
                "total_ghs_paid": float(total_ghs_paid or 0),
            },
        }

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------

    async def list_users(
        self,
        limit: int = 20,
        offset: int = 0,
        search: Optional[str] = None,
        role: Optional[str] = None,
    ) -> dict:
        """Paginated user list with optional search and role filter."""

        async with get_connection() as conn:

            # Build query dynamically
            conditions = []
            params = []
            idx = 1

            if search:
                conditions.append(
                    f"(username ILIKE ${idx} OR email ILIKE ${idx} OR display_name ILIKE ${idx})"
                )
                params.append(f"%{search}%")
                idx += 1

            if role:
                conditions.append(f"role = ${idx}")
                params.append(role)
                idx += 1

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            users = await conn.fetch(
                f"""
                SELECT id, email, username, display_name, role, badge_tier,
                       total_points, issues_reported, tasks_completed,
                       email_verified, created_at
                FROM users
                {where}
                ORDER BY created_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}
                """,
                *params,
                limit,
                offset,
            )

            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM users {where}",
                *params,
            )

        return {
            "users": [self._serialize_user(u) for u in users],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        }

    async def get_user_detail(self, user_id: str) -> dict:
        """Get full details for a specific user including activity."""

        async with get_connection() as conn:

            user = await conn.fetchrow(
                "SELECT * FROM users WHERE id=$1",
                user_id,
            )
            if not user:
                raise ValueError("User not found")

            # Recent activity
            activity = await conn.fetch(
                """
                SELECT activity_type, points_earned, activity_date
                FROM user_activity_log
                WHERE user_id=$1
                ORDER BY created_at DESC
                LIMIT 10
                """,
                user_id,
            )

            # Badges
            badges = await conn.fetch(
                "SELECT badge_type, earned_at FROM user_badges WHERE user_id=$1 ORDER BY earned_at DESC",
                user_id,
            )

            # Payment history
            payments = await conn.fetch(
                """
                SELECT payment_type, amount_ghs, points_spent, status, created_at
                FROM payments
                WHERE user_id=$1
                ORDER BY created_at DESC
                LIMIT 5
                """,
                user_id,
            )

        return {
            **self._serialize_user(user),
            "volunteer_streak": user["volunteer_streak"],
            "total_kg_collected": float(user["total_kg_collected"] or 0),
            "recent_activity": [dict(a) for a in activity],
            "badges": [dict(b) for b in badges],
            "recent_payments": [
                {
                    "payment_type": p["payment_type"],
                    "amount_ghs": float(p["amount_ghs"]),
                    "points_spent": p["points_spent"],
                    "status": p["status"],
                    "created_at": p["created_at"].isoformat(),
                }
                for p in payments
            ],
        }

    async def ban_user(self, admin_id: str, user_id: str, reason: str) -> dict:
        """
        Ban a user by setting their role to 'banned'.
        Logs the action to user_activity_log for audit trail.
        """

        async with get_connection() as conn:

            user = await conn.fetchrow(
                "SELECT id, username, email, role FROM users WHERE id=$1",
                user_id,
            )
            if not user:
                raise ValueError("User not found")

            if user["role"] == "admin":
                raise ValueError("Cannot ban an admin user")

            if user["role"] == "banned":
                raise ValueError("User is already banned")

            await conn.execute(
                "UPDATE users SET role='banned', updated_at=NOW() WHERE id=$1",
                user_id,
            )

            # Audit log
            await conn.execute(
                """
                INSERT INTO user_activity_log
                    (user_id, activity_type, activity_date, points_earned,
                     reference_id, reference_type, metadata, created_at)
                VALUES ($1, 'user_banned', $2, 0, $3, 'admin_action', $4, NOW())
                """,
                user_id,
                datetime.utcnow().date(),
                admin_id,
                json.dumps({"reason": reason, "banned_by": admin_id}),
            )

        return {
            "user_id": user_id,
            "username": user["username"],
            "status": "banned",
            "reason": reason,
            "message": f"User {user['username']} has been banned.",
        }

    async def unban_user(self, admin_id: str, user_id: str) -> dict:
        """Restore a banned user's access."""

        async with get_connection() as conn:

            user = await conn.fetchrow(
                "SELECT id, username, role FROM users WHERE id=$1",
                user_id,
            )
            if not user:
                raise ValueError("User not found")

            if user["role"] != "banned":
                raise ValueError("User is not banned")

            await conn.execute(
                "UPDATE users SET role='user', updated_at=NOW() WHERE id=$1",
                user_id,
            )

            await conn.execute(
                """
                INSERT INTO user_activity_log
                    (user_id, activity_type, activity_date, points_earned,
                     reference_id, reference_type, metadata, created_at)
                VALUES ($1, 'user_unbanned', $2, 0, $3, 'admin_action', $4, NOW())
                """,
                user_id,
                datetime.utcnow().date(),
                admin_id,
                json.dumps({"unbanned_by": admin_id}),
            )

        return {
            "user_id": user_id,
            "username": user["username"],
            "status": "active",
            "message": f"User {user['username']} has been unbanned.",
        }

    # ------------------------------------------------------------------
    # Issue moderation
    # ------------------------------------------------------------------

    async def get_pending_verifications(self, limit: int = 20, offset: int = 0) -> dict:
        """Get issues that need manual admin verification."""

        async with get_connection() as conn:

            issues = await conn.fetch(
                """
                SELECT i.*, u.username, u.email
                FROM issues i
                JOIN users u ON u.id = i.user_id
                WHERE i.status = 'open'
                ORDER BY i.created_at ASC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )

            total = await conn.fetchval(
                "SELECT COUNT(*) FROM issues WHERE status='open'"
            )

        return {
            "issues": [self._serialize_issue(i) for i in issues],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        }

    async def verify_issue(
        self, admin_id: str, issue_id: str, approved: bool, notes: Optional[str] = None
    ) -> dict:
        """Manually approve or reject an issue report."""

        async with get_connection() as conn:

            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id=$1",
                issue_id,
            )
            if not issue:
                raise ValueError("Issue not found")

            new_status = "open" if approved else "rejected"

            await conn.execute(
                "UPDATE issues SET status=$1, updated_at=NOW() WHERE id=$2",
                new_status,
                issue_id,
            )

            # Audit log
            await conn.execute(
                """
                INSERT INTO user_activity_log
                    (user_id, activity_type, activity_date, points_earned,
                     reference_id, reference_type, metadata, created_at)
                VALUES ($1, $2, $3, 0, $4, 'issue', $5, NOW())
                """,
                str(issue["user_id"]),
                "issue_approved" if approved else "issue_rejected",
                datetime.utcnow().date(),
                issue_id,
                json.dumps({"admin_id": admin_id, "notes": notes}),
            )

        return {
            "issue_id": issue_id,
            "status": new_status,
            "approved": approved,
            "notes": notes,
            "message": f"Issue {'approved' if approved else 'rejected'} successfully.",
        }

    # ------------------------------------------------------------------
    # Serializers
    # ------------------------------------------------------------------

    def _serialize_user(self, row) -> dict:
        return {
            "id": str(row["id"]),
            "email": row["email"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "badge_tier": row["badge_tier"],
            "total_points": row["total_points"] or 0,
            "issues_reported": row["issues_reported"] or 0,
            "tasks_completed": row["tasks_completed"] or 0,
            "email_verified": row["email_verified"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

    def _serialize_issue(self, row) -> dict:
        return {
            "id": str(row["id"]),
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "priority": row["priority"],
            "difficulty": row["difficulty"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "picture_url": row["picture_url"],
            "reporter": row["username"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
