from app.database import get_connection
from app.utils.points_calculator import PointsCalculator
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import asyncio


class PointsService:
    """Handle all points awarding, activity logging, badge checking, and cache invalidation"""

    def __init__(self):
        pass

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
        Award points to a user and trigger all related actions

        This is the SINGLE source of truth for awarding points.
        It handles:
        1. Update user's total_points
        2. Log the activity
        3. Check for new badges
        4. Invalidate leaderboard cache
        5. Update user stats

        Args:
            user_id: UUID of user earning points
            points: Number of points to award
            activity_type: "issue_reported", "cleanup_verified", "collection_verified", etc.
            reference_id: ID of related issue/collection/volunteer record
            reference_type: "issue", "collection", "volunteer"
            metadata: Additional data to store (optional)

        Returns:
            Dictionary with:
            - user_id
            - points_awarded
            - new_total_points
            - badges_unlocked: List of newly earned badges
            - message
        """
        try:
            # Step 1: Get current user data
            print(f"[POINTS] Awarding {points} points to {user_id} for {activity_type}")
            user_response = (
                self.supabase.table("users").select("*").eq("id", user_id).execute()
            )

            if not user_response.data:
                raise ValueError("User not found")

            user = user_response.data[0]
            current_points = user.get("total_points", 0)
            new_total_points = current_points + points

            # Step 2: Update user's total points
            print(f"[POINTS] Updating points: {current_points} → {new_total_points}")
            self.supabase.table("users").update(
                {
                    "total_points": new_total_points,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            ).eq("id", user_id).execute()

            # Step 3: Log the activity
            print(f"[ACTIVITY] Logging {activity_type}")
            activity_log_data = {
                "user_id": user_id,
                "activity_type": activity_type,
                "activity_date": datetime.utcnow().date().isoformat(),
                "points_earned": points,
                "reference_id": reference_id,
                "reference_type": reference_type,
                "metadata": metadata or {},
            }
            self.supabase.table("user_activity_log").insert(activity_log_data).execute()

            # Step 4: Update activity-specific user stats
            print(f"[STATS] Updating user stats for {activity_type}")
            await self._update_user_stats(user_id, activity_type)

            # Step 5: Check for newly earned badges
            print(f"[BADGES] Checking for new badges")
            badges_unlocked = await self._check_and_award_badges(
                user_id, new_total_points
            )

            # Step 6: Invalidate leaderboard cache
            print(f"[CACHE] Invalidating leaderboard cache")
            await self._invalidate_cache(user_id)

            return {
                "user_id": user_id,
                "points_awarded": points,
                "previous_total_points": current_points,
                "new_total_points": new_total_points,
                "badges_unlocked": badges_unlocked,
                "message": (
                    f"Awarded {points} points! {len(badges_unlocked)} new badge(s) earned!"
                    if badges_unlocked
                    else f"Awarded {points} points!"
                ),
            }

        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to award points: {str(e)}")

    async def _update_user_stats(self, user_id: str, activity_type: str) -> None:
        """
        Update user statistics based on activity type

        Args:
            user_id: User UUID
            activity_type: Type of activity performed
        """
        try:
            # Get current user stats
            user_response = (
                self.supabase.table("users")
                .select(
                    "issues_reported,tasks_completed,total_kg_collected,total_verifications_accepted,last_volunteer_date,volunteer_streak"
                )
                .eq("id", user_id)
                .execute()
            )

            if not user_response.data:
                return

            user = user_response.data[0]
            update_data = {}
            today = datetime.utcnow().date()

            # Update based on activity type
            if activity_type == "issue_reported":
                update_data["issues_reported"] = (
                    user.get("issues_reported", 0) or 0
                ) + 1

            elif activity_type == "cleanup_verified":
                update_data["tasks_completed"] = (
                    user.get("tasks_completed", 0) or 0
                ) + 1
                # Update streak
                last_volunteer_date = user.get("last_volunteer_date")
                current_streak = user.get("volunteer_streak", 0) or 0

                if last_volunteer_date:
                    last_date = (
                        datetime.strptime(last_volunteer_date, "%Y-%m-%d").date()
                        if isinstance(last_volunteer_date, str)
                        else last_volunteer_date
                    )
                    if (today - last_date).days == 1:
                        # Consecutive day! Increment streak
                        update_data["volunteer_streak"] = current_streak + 1
                    elif (today - last_date).days > 1:
                        # Streak broken, reset to 1
                        update_data["volunteer_streak"] = 1
                else:
                    # First time
                    update_data["volunteer_streak"] = 1

                update_data["last_volunteer_date"] = today.isoformat()

            elif activity_type == "collection_verified":
                update_data["tasks_completed"] = (
                    user.get("tasks_completed", 0) or 0
                ) + 1
                # For collections, we update kg in collection_service
                # But we can update streak here too
                last_volunteer_date = user.get("last_volunteer_date")
                current_streak = user.get("volunteer_streak", 0) or 0

                if last_volunteer_date:
                    last_date = (
                        datetime.strptime(last_volunteer_date, "%Y-%m-%d").date()
                        if isinstance(last_volunteer_date, str)
                        else last_volunteer_date
                    )
                    if (today - last_date).days == 1:
                        update_data["volunteer_streak"] = current_streak + 1
                    elif (today - last_date).days > 1:
                        update_data["volunteer_streak"] = 1
                else:
                    update_data["volunteer_streak"] = 1

                update_data["last_volunteer_date"] = today.isoformat()

            # Apply updates
            if update_data:
                self.supabase.table("users").update(update_data).eq(
                    "id", user_id
                ).execute()

        except Exception as e:
            print(f"Warning: Failed to update user stats: {str(e)}")

    async def _check_and_award_badges(self, user_id: str, current_points: int) -> list:
        """
        Check if user qualifies for any new badges and award them

        Args:
            user_id: User UUID
            current_points: User's current total points

        Returns:
            List of newly earned badge types
        """
        try:
            badges_unlocked = []

            # Get all badge definitions
            badges_response = (
                self.supabase.table("badge_definitions").select("*").execute()
            )

            if not badges_response.data:
                return badges_unlocked

            # Get user's current badges (to avoid duplicates)
            user_badges_response = (
                self.supabase.table("user_badges")
                .select("badge_type")
                .eq("user_id", user_id)
                .execute()
            )
            user_badge_types = set(
                b["badge_type"] for b in (user_badges_response.data or [])
            )

            # Get user's current stats
            user_response = (
                self.supabase.table("users").select("*").eq("id", user_id).execute()
            )
            user = user_response.data[0]

            # Check each badge definition
            for badge_def in badges_response.data:
                badge_type = badge_def["badge_type"]

                # Skip if user already has this permanent badge
                if badge_def["is_permanent"] and badge_type in user_badge_types:
                    continue

                # Check unlock condition
                condition = badge_def["unlock_condition"]
                condition_met = await self._check_badge_condition(
                    user, condition, user_id
                )

                if condition_met:
                    # Award the badge
                    badge_data = {
                        "user_id": user_id,
                        "badge_type": badge_type,
                        "is_permanent": badge_def["is_permanent"],
                        "earned_at": datetime.utcnow().isoformat(),
                        "current_week_earned": True,
                        "week_start_date": self._get_week_start_date().isoformat(),
                        "metadata": {"condition": condition},
                    }

                    self.supabase.table("user_badges").insert(badge_data).execute()
                    badges_unlocked.append(badge_type)
                    print(f"[BADGE] User {user_id} unlocked badge: {badge_type}")

            return badges_unlocked

        except Exception as e:
            print(f"Warning: Failed to check badges: {str(e)}")
            return []

    async def _check_badge_condition(
        self, user: Dict, condition: Dict, user_id: str
    ) -> bool:
        """
        Check if user meets a badge unlock condition

        Args:
            user: User data dict
            condition: Badge unlock condition from badge_definitions
            user_id: User UUID (for activity log queries)

        Returns:
            True if condition is met, False otherwise
        """
        try:
            condition_type = condition.get("type")
            threshold = condition.get("threshold")

            # POINTS-BASED CONDITIONS
            if condition_type == "points":
                return user.get("total_points", 0) >= threshold

            # ISSUE REPORTING
            elif condition_type == "issues_reported":
                return user.get("issues_reported", 0) >= threshold

            # CLEANUP COMPLETION
            elif condition_type == "cleanups":
                # Count completed cleanups from activity log
                activity_response = (
                    self.supabase.table("user_activity_log")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("activity_type", "cleanup_verified")
                    .execute()
                )
                count = len(activity_response.data or [])
                return count >= threshold

            # GROUP CLEANUPS
            elif condition_type == "group_cleanups":
                # Count group cleanups (where user was not solo)
                volunteers_response = (
                    self.supabase.table("volunteers")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("solo_work", False)
                    .eq("verified", True)
                    .execute()
                )
                count = len(volunteers_response.data or [])
                return count >= threshold

            # KG COLLECTED
            elif condition_type == "kg_collected":
                return user.get("total_kg_collected", 0) >= threshold

            # VERIFICATIONS ACCEPTED
            elif condition_type == "verifications":
                return user.get("total_verifications_accepted", 0) >= threshold

            # STREAK
            elif condition_type == "streak":
                streak_days = condition.get("days", 0)
                return user.get("volunteer_streak", 0) >= streak_days

            # BADGES COUNT (for Legend badge)
            elif condition_type == "badges_count":
                badges_response = (
                    self.supabase.table("user_badges")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("is_permanent", True)
                    .execute()
                )
                count = len(badges_response.data or [])
                return count >= threshold

            # WEEKLY CONDITIONS
            elif condition_type == "weekly_rank":
                # This is checked separately in leaderboard service
                return False

            elif condition_type == "weekly_points":
                # Calculate points earned this week
                week_start = self._get_week_start_date()
                activity_response = (
                    self.supabase.table("user_activity_log")
                    .select("points_earned")
                    .eq("user_id", user_id)
                    .gte("activity_date", week_start.isoformat())
                    .execute()
                )
                weekly_points = sum(
                    a.get("points_earned", 0) for a in (activity_response.data or [])
                )
                return weekly_points >= threshold

            elif condition_type == "weekly_cleanups":
                # Count cleanups this week
                week_start = self._get_week_start_date()
                activity_response = (
                    self.supabase.table("user_activity_log")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("activity_type", "cleanup_verified")
                    .gte("activity_date", week_start.isoformat())
                    .execute()
                )
                count = len(activity_response.data or [])
                return count >= threshold

            return False

        except Exception as e:
            print(f"Warning: Failed to check badge condition: {str(e)}")
            return False

    async def _invalidate_cache(self, user_id: str) -> None:
        """
        Invalidate leaderboard cache entries related to this user

        Args:
            user_id: User UUID
        """
        try:
            # Delete all cache entries for this user
            # This forces fresh calculation on next request
            self.supabase.table("leaderboard_cache").delete().eq(
                "user_id", user_id
            ).execute()
            print(f"[CACHE] Invalidated cache for user {user_id}")

        except Exception as e:
            print(f"Warning: Failed to invalidate cache: {str(e)}")

    @staticmethod
    def _get_week_start_date() -> datetime:
        """
        Get the start date of the current week (Monday)

        Returns:
            Monday of the current week as datetime.date
        """
        today = datetime.utcnow().date()
        # Monday is 0, Sunday is 6
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday)
        return week_start

    async def recalculate_weekly_badges(self) -> Dict[str, int]:
        """
        Recalculate weekly badges for ALL users

        This should be run once per week (on Monday at 00:00)

        Returns:
            Dict with counts of badges awarded
        """
        try:
            print("[WEEKLY] Starting weekly badge recalculation...")

            counts = {"rising_star": 0, "momentum": 0, "on_fire": 0}

            # Step 1: Mark all previous weekly badges as no longer current
            self.supabase.table("user_badges").update(
                {"current_week_earned": False}
            ).eq("is_permanent", False).execute()

            # Step 2: Get all users
            users_response = self.supabase.table("users").select("id").execute()
            user_ids = [u["id"] for u in (users_response.data or [])]

            print(f"[WEEKLY] Processing {len(user_ids)} users...")

            # Step 3: For each user, check weekly badge conditions
            for user_id in user_ids:
                user_response = (
                    self.supabase.table("users").select("*").eq("id", user_id).execute()
                )
                if not user_response.data:
                    continue

                user = user_response.data[0]
                week_start = self._get_week_start_date()

                # Check Rising Star (top 10 in points this week)
                # This will be handled by leaderboard service, just ensure badge exists

                # Check Momentum (100+ points this week)
                activity_response = (
                    self.supabase.table("user_activity_log")
                    .select("points_earned")
                    .eq("user_id", user_id)
                    .gte("activity_date", week_start.isoformat())
                    .execute()
                )
                weekly_points = sum(
                    a.get("points_earned", 0) for a in (activity_response.data or [])
                )

                if weekly_points >= 100:
                    # Award momentum badge
                    existing = (
                        self.supabase.table("user_badges")
                        .select("id")
                        .eq("user_id", user_id)
                        .eq("badge_type", "momentum")
                        .gte("earned_at", week_start.isoformat())
                        .execute()
                    )
                    if not existing.data:
                        self.supabase.table("user_badges").insert(
                            {
                                "user_id": user_id,
                                "badge_type": "momentum",
                                "is_permanent": False,
                                "earned_at": datetime.utcnow().isoformat(),
                                "current_week_earned": True,
                                "week_start_date": week_start.isoformat(),
                                "metadata": {"weekly_points": weekly_points},
                            }
                        ).execute()
                        counts["momentum"] += 1

                # Check On Fire (3+ cleanups this week)
                activity_response = (
                    self.supabase.table("user_activity_log")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("activity_type", "cleanup_verified")
                    .gte("activity_date", week_start.isoformat())
                    .execute()
                )
                cleanup_count = len(activity_response.data or [])

                if cleanup_count >= 3:
                    # Award on_fire badge
                    existing = (
                        self.supabase.table("user_badges")
                        .select("id")
                        .eq("user_id", user_id)
                        .eq("badge_type", "on_fire")
                        .gte("earned_at", week_start.isoformat())
                        .execute()
                    )
                    if not existing.data:
                        self.supabase.table("user_badges").insert(
                            {
                                "user_id": user_id,
                                "badge_type": "on_fire",
                                "is_permanent": False,
                                "earned_at": datetime.utcnow().isoformat(),
                                "current_week_earned": True,
                                "week_start_date": week_start.isoformat(),
                                "metadata": {"weekly_cleanups": cleanup_count},
                            }
                        ).execute()
                        counts["on_fire"] += 1

            print(f"[WEEKLY] Completed! Awarded: {counts}")
            return counts

        except Exception as e:
            print(f"Error in weekly badge recalculation: {str(e)}")
            return {}
