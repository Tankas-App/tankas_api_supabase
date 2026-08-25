"""
profile_service.py — User profile management and dashboard

Ported from the legacy tankas_app-api: profile editing, avatar upload, and the
personal dashboard. The new schema carries richer stats than the old one
(streaks, kg collected, badges), so the dashboard surfaces those too.
"""

from app.database import get_connection
from app.utils.cloudinary_helper import CloudinaryHelper


MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class ProfileService:

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_profile(self, user_id: str) -> dict:
        """Get a user's own full profile."""
        async with get_connection() as conn:
            u = await conn.fetchrow(
                """
                SELECT id, email, phone, username, display_name, avatar_url,
                       total_points, badge_tier, issues_reported, tasks_completed,
                       volunteer_hours, email_verified, phone_verified, role,
                       volunteer_streak, last_volunteer_date, total_kg_collected,
                       created_at
                FROM users WHERE id=$1
                """,
                user_id,
            )
        if not u:
            raise ValueError("User not found")

        return {
            "user_id": str(u["id"]),
            "email": u["email"],
            "phone": u["phone"],
            "username": u["username"],
            "display_name": u["display_name"],
            "avatar_url": u["avatar_url"],
            "total_points": u["total_points"],
            "badge_tier": u["badge_tier"],
            "issues_reported": u["issues_reported"],
            "tasks_completed": u["tasks_completed"],
            "volunteer_hours": u["volunteer_hours"],
            "email_verified": u["email_verified"],
            "phone_verified": u["phone_verified"],
            "role": u["role"],
            "volunteer_streak": u["volunteer_streak"],
            "last_volunteer_date": u["last_volunteer_date"],
            "total_kg_collected": float(u["total_kg_collected"] or 0),
            "created_at": u["created_at"],
        }

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_profile(
        self,
        user_id: str,
        display_name: str = None,
        username: str = None,
        phone: str = None,
    ) -> dict:
        """
        Update editable profile fields. Only non-None fields are changed.

        Email is deliberately not editable here — it is the login identity and
        changing it would need re-verification through the OTP flow.
        """
        updates = {}
        if display_name is not None:
            display_name = display_name.strip()
            if not display_name:
                raise ValueError("Display name cannot be empty")
            updates["display_name"] = display_name

        if username is not None:
            username = username.strip()
            if len(username) < 3:
                raise ValueError("Username must be at least 3 characters")
            updates["username"] = username

        if phone is not None:
            updates["phone"] = phone.strip() or None

        if not updates:
            raise ValueError("No fields to update")

        async with get_connection() as conn:

            if "username" in updates:
                clash = await conn.fetchrow(
                    "SELECT id FROM users WHERE username=$1 AND id<>$2",
                    updates["username"],
                    user_id,
                )
                if clash:
                    raise ValueError("That username is already taken")

            # Build the SET clause from whichever fields were supplied.
            columns = list(updates.keys())
            assignments = ", ".join(f"{c} = ${i + 1}" for i, c in enumerate(columns))
            values = [updates[c] for c in columns]

            row = await conn.fetchrow(
                f"""
                UPDATE users SET {assignments}, updated_at = NOW()
                WHERE id = ${len(columns) + 1}
                RETURNING id, username, display_name, phone, avatar_url
                """,
                *values,
                user_id,
            )

        if not row:
            raise ValueError("User not found")

        return {
            "user_id": str(row["id"]),
            "username": row["username"],
            "display_name": row["display_name"],
            "phone": row["phone"],
            "avatar_url": row["avatar_url"],
        }

    async def update_avatar(
        self, user_id: str, photo_bytes: bytes, content_type: str
    ) -> dict:
        """Upload a new avatar to Cloudinary and store the URL."""
        if content_type not in ALLOWED_AVATAR_TYPES:
            raise ValueError(
                f"Unsupported image type. Allowed: {', '.join(sorted(ALLOWED_AVATAR_TYPES))}"
            )
        if not photo_bytes:
            raise ValueError("Empty file")
        if len(photo_bytes) > MAX_AVATAR_BYTES:
            raise ValueError("Avatar must be 5 MB or smaller")

        avatar_url = await CloudinaryHelper.upload_photo(
            photo_bytes, folder="tankas-avatars"
        )

        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE users SET avatar_url=$1, updated_at=NOW()
                WHERE id=$2
                RETURNING id, username, avatar_url
                """,
                avatar_url,
                user_id,
            )
        if not row:
            raise ValueError("User not found")

        return {
            "user_id": str(row["id"]),
            "username": row["username"],
            "avatar_url": row["avatar_url"],
        }

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    async def get_dashboard(self, user_id: str) -> dict:
        """
        Personal dashboard: profile summary, headline stats, recent activity.
        """
        async with get_connection() as conn:

            u = await conn.fetchrow(
                """
                SELECT id, username, display_name, avatar_url, total_points,
                       badge_tier, issues_reported, tasks_completed,
                       volunteer_hours, volunteer_streak, total_kg_collected
                FROM users WHERE id=$1
                """,
                user_id,
            )
            if not u:
                raise ValueError("User not found")

            recent_issues = await conn.fetch(
                """
                SELECT id, title, status, picture_url, points_assigned, created_at
                FROM issues
                WHERE user_id=$1
                ORDER BY created_at DESC
                LIMIT 5
                """,
                user_id,
            )

            recent_volunteering = await conn.fetch(
                """
                SELECT v.id, v.issue_id, v.points_earned, v.created_at,
                       i.title, i.status
                FROM volunteers v
                JOIN issues i ON i.id = v.issue_id
                WHERE v.user_id=$1
                ORDER BY v.created_at DESC
                LIMIT 5
                """,
                user_id,
            )

            badges = await conn.fetch(
                """
                SELECT badge_type, earned_at
                FROM user_badges
                WHERE user_id=$1
                ORDER BY earned_at DESC
                """,
                user_id,
            )

            # Distinct issues this user actually helped resolve.
            areas_cleaned = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT i.id)
                FROM issues i
                LEFT JOIN volunteers v ON v.issue_id = i.id AND v.user_id = $1
                WHERE i.status = 'resolved'
                  AND (i.resolved_by = $1 OR v.user_id = $1)
                """,
                user_id,
            )

        return {
            "profile": {
                "user_id": str(u["id"]),
                "username": u["username"],
                "display_name": u["display_name"],
                "avatar_url": u["avatar_url"],
                "badge_tier": u["badge_tier"],
            },
            "stats": {
                "total_points": u["total_points"],
                "issues_reported": u["issues_reported"],
                "tasks_completed": u["tasks_completed"],
                "areas_cleaned": areas_cleaned or 0,
                "volunteer_hours": u["volunteer_hours"],
                "volunteer_streak": u["volunteer_streak"],
                "total_kg_collected": float(u["total_kg_collected"] or 0),
                "badges_earned": len(badges),
            },
            "recent_issues": [
                {
                    "issue_id": str(r["id"]),
                    "title": r["title"],
                    "status": r["status"],
                    "picture_url": r["picture_url"],
                    "points_assigned": r["points_assigned"],
                    "created_at": r["created_at"],
                }
                for r in recent_issues
            ],
            "recent_volunteering": [
                {
                    "volunteer_id": str(r["id"]),
                    "issue_id": str(r["issue_id"]),
                    "title": r["title"],
                    "status": r["status"],
                    "points_earned": r["points_earned"],
                    "created_at": r["created_at"],
                }
                for r in recent_volunteering
            ],
            "badges": [
                {"badge_type": b["badge_type"], "earned_at": b["earned_at"]}
                for b in badges
            ],
        }
