"""
point_service.py — Points, activity logging, badges, cache invalidation
"""

from app.database import get_connection
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import json


class PointsService:

    # ------------------------------------------------------------------
    # Award points — single entry point for all point transactions
    # ------------------------------------------------------------------

    async def award_points(
        self,
        user_id: str,
        points: int,
        activity_type: str,
        reference_id: Optional[str] = None,
        reference_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Award points to a user and trigger all related actions:
        1. Update total_points
        2. Log activity
        3. Update activity-specific stats
        4. Check + award badges
        5. Invalidate leaderboard cache
        """
        async with get_connection() as conn:

            # Step 1: Get current points
            user = await conn.fetchrow(
                "SELECT id, total_points FROM users WHERE id = $1",
                user_id,
            )
            if not user:
                raise ValueError("User not found")

            current_points = user["total_points"] or 0
            new_total = current_points + points

            # Step 2: Update total_points
            await conn.execute(
                "UPDATE users SET total_points = $1, updated_at = NOW() WHERE id = $2",
                new_total,
                user_id,
            )

            # Step 3: Log activity
            await conn.execute(
                """
                INSERT INTO user_activity_log
                    (user_id, activity_type, activity_date, points_earned,
                     reference_id, reference_type, metadata, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                """,
                user_id,
                activity_type,
                datetime.utcnow().date(),
                points,
                reference_id,
                reference_type,
                json.dumps(metadata or {}),
            )

            # Step 4: Update activity-specific stats
            await self._update_user_stats(conn, user_id, activity_type)

            # Step 5: Check badges
            badges_unlocked = await self._check_and_award_badges(
                conn, user_id, new_total
            )

        # Step 6: Invalidate leaderboard cache (separate connection is fine)
        await self._invalidate_cache(user_id)

        return {
            "user_id": user_id,
            "points_awarded": points,
            "previous_total_points": current_points,
            "new_total_points": new_total,
            "badges_unlocked": badges_unlocked,
            "message": (
                f"Awarded {points} points! {len(badges_unlocked)} new badge(s) earned!"
                if badges_unlocked
                else f"Awarded {points} points!"
            ),
        }

    # ------------------------------------------------------------------
    # Update user stats based on activity type
    # ------------------------------------------------------------------

    async def _update_user_stats(self, conn, user_id: str, activity_type: str) -> None:
        today = datetime.utcnow().date()

        if activity_type == "issue_reported":
            await conn.execute(
                "UPDATE users SET issues_reported = issues_reported + 1 WHERE id = $1",
                user_id,
            )

        elif activity_type in ("cleanup_verified", "collection_verified"):
            user = await conn.fetchrow(
                "SELECT last_volunteer_date, volunteer_streak FROM users WHERE id = $1",
                user_id,
            )
            streak = user["volunteer_streak"] or 0
            last = user["last_volunteer_date"]

            if last:
                diff = (today - last).days
                new_streak = streak + 1 if diff == 1 else 1
            else:
                new_streak = 1

            await conn.execute(
                """
                UPDATE users
                SET tasks_completed      = tasks_completed + 1,
                    volunteer_streak     = $1,
                    last_volunteer_date  = $2,
                    updated_at           = NOW()
                WHERE id = $3
                """,
                new_streak,
                today,
                user_id,
            )

    # ------------------------------------------------------------------
    # Badge checking
    # ------------------------------------------------------------------

    async def _check_and_award_badges(
        self, conn, user_id: str, current_points: int
    ) -> List[str]:
        badges_unlocked = []

        # Get all badge definitions
        badge_defs = await conn.fetch("SELECT * FROM badge_definitions")
        if not badge_defs:
            return badges_unlocked

        # Get badges user already has
        existing = await conn.fetch(
            "SELECT badge_type FROM user_badges WHERE user_id = $1",
            user_id,
        )
        owned = {r["badge_type"] for r in existing}

        # Get full user record for condition checks
        user = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

        week_start = self._get_week_start_date()

        for badge in badge_defs:
            badge_type = badge["badge_type"]

            # Skip permanent badges user already owns
            if badge["is_permanent"] and badge_type in owned:
                continue

            condition = badge["unlock_condition"]
            if isinstance(condition, str):
                condition = json.loads(condition)

            met = await self._check_badge_condition(conn, user, condition, user_id)

            if met:
                await conn.execute(
                    """
                    INSERT INTO user_badges
                        (user_id, badge_type, is_permanent, earned_at,
                         current_week_earned, week_start_date, metadata)
                    VALUES ($1, $2, $3, NOW(), TRUE, $4, $5)
                    """,
                    user_id,
                    badge_type,
                    badge["is_permanent"],
                    week_start,
                    json.dumps({"condition": condition}),
                )
                badges_unlocked.append(badge_type)

        return badges_unlocked

    async def _check_badge_condition(
        self, conn, user, condition: Dict, user_id: str
    ) -> bool:
        condition_type = condition.get("type")
        threshold = condition.get("threshold", 0)

        if condition_type == "points":
            return (user["total_points"] or 0) >= threshold

        elif condition_type == "issues_reported":
            return (user["issues_reported"] or 0) >= threshold

        elif condition_type == "cleanups":
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM user_activity_log WHERE user_id=$1 AND activity_type='cleanup_verified'",
                user_id,
            )
            return count >= threshold

        elif condition_type == "group_cleanups":
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM volunteers WHERE user_id=$1 AND solo_work=FALSE AND verified=TRUE",
                user_id,
            )
            return count >= threshold

        elif condition_type == "kg_collected":
            return float(user["total_kg_collected"] or 0) >= threshold

        elif condition_type == "streak":
            return (user["volunteer_streak"] or 0) >= condition.get("days", 0)

        elif condition_type == "badges_count":
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM user_badges WHERE user_id=$1 AND is_permanent=TRUE",
                user_id,
            )
            return count >= threshold

        elif condition_type == "weekly_points":
            week_start = self._get_week_start_date()
            total = await conn.fetchval(
                """
                SELECT COALESCE(SUM(points_earned), 0)
                FROM user_activity_log
                WHERE user_id=$1 AND activity_date >= $2
                """,
                user_id,
                week_start,
            )
            return total >= threshold

        elif condition_type == "weekly_cleanups":
            week_start = self._get_week_start_date()
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM user_activity_log
                WHERE user_id=$1 AND activity_type='cleanup_verified' AND activity_date >= $2
                """,
                user_id,
                week_start,
            )
            return count >= threshold

        return False

    # ------------------------------------------------------------------
    # Cache invalidation
    # ------------------------------------------------------------------

    async def _invalidate_cache(self, user_id: str) -> None:
        try:
            async with get_connection() as conn:
                await conn.execute(
                    "DELETE FROM leaderboard_cache WHERE cached_at >= NOW() - INTERVAL '5 minutes'"
                )
        except Exception as e:
            print(f"[WARNING] Cache invalidation failed: {e}")

    # ------------------------------------------------------------------
    # Weekly badge recalculation
    # ------------------------------------------------------------------

    async def recalculate_weekly_badges(self) -> Dict[str, int]:
        counts = {"momentum": 0, "on_fire": 0}
        week_start = self._get_week_start_date()

        async with get_connection() as conn:

            # Mark all previous weekly badges as not current
            await conn.execute(
                "UPDATE user_badges SET current_week_earned=FALSE WHERE is_permanent=FALSE"
            )

            users = await conn.fetch("SELECT id FROM users")

            for row in users:
                uid = str(row["id"])

                # Momentum — 100+ points this week
                weekly_pts = await conn.fetchval(
                    """
                    SELECT COALESCE(SUM(points_earned), 0)
                    FROM user_activity_log
                    WHERE user_id=$1 AND activity_date >= $2
                    """,
                    uid,
                    week_start,
                )
                if weekly_pts >= 100:
                    exists = await conn.fetchval(
                        "SELECT id FROM user_badges WHERE user_id=$1 AND badge_type='momentum' AND week_start_date=$2",
                        uid,
                        week_start,
                    )
                    if not exists:
                        await conn.execute(
                            """
                            INSERT INTO user_badges
                                (user_id, badge_type, is_permanent, earned_at, current_week_earned, week_start_date, metadata)
                            VALUES ($1, 'momentum', FALSE, NOW(), TRUE, $2, $3)
                            """,
                            uid,
                            week_start,
                            json.dumps({"weekly_points": weekly_pts}),
                        )
                        counts["momentum"] += 1

                # On Fire — 3+ cleanups this week
                cleanups = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM user_activity_log
                    WHERE user_id=$1 AND activity_type='cleanup_verified' AND activity_date >= $2
                    """,
                    uid,
                    week_start,
                )
                if cleanups >= 3:
                    exists = await conn.fetchval(
                        "SELECT id FROM user_badges WHERE user_id=$1 AND badge_type='on_fire' AND week_start_date=$2",
                        uid,
                        week_start,
                    )
                    if not exists:
                        await conn.execute(
                            """
                            INSERT INTO user_badges
                                (user_id, badge_type, is_permanent, earned_at, current_week_earned, week_start_date, metadata)
                            VALUES ($1, 'on_fire', FALSE, NOW(), TRUE, $2, $3)
                            """,
                            uid,
                            week_start,
                            json.dumps({"weekly_cleanups": cleanups}),
                        )
                        counts["on_fire"] += 1

        return counts

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _get_week_start_date():
        today = datetime.utcnow().date()
        return today - timedelta(days=today.weekday())
