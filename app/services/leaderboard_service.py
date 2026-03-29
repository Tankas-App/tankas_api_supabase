"""
leaderboard_service.py — Rankings, caching, weekly badge resets
"""

from app.database import get_connection
from app.services.point_service import PointsService
from app.utils.distance_calculator import DistanceCalculator
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json


class LeaderboardService:

    def __init__(self):
        self.points_service = PointsService()
        self.CACHE_TTL_MINUTES = 5

    # ------------------------------------------------------------------
    # Available leaderboard types
    # ------------------------------------------------------------------

    @staticmethod
    def get_available_leaderboards() -> Dict[str, Dict[str, Any]]:
        return {
            "points": {
                "name": "Points Leaderboard",
                "metric": "total_points",
                "order": "DESC",
            },
            "issues_reported": {
                "name": "Issue Reporter Leaderboard",
                "metric": "issues_reported",
                "order": "DESC",
            },
            "collections": {
                "name": "Collector Leaderboard",
                "metric": "collections_count",
                "order": "DESC",
            },
            "kg_collected": {
                "name": "Garbage Master Leaderboard",
                "metric": "total_kg_collected",
                "order": "DESC",
            },
            "volunteer_hours": {
                "name": "Volunteer Hours Leaderboard",
                "metric": "volunteer_hours",
                "order": "DESC",
            },
        }

    # ------------------------------------------------------------------
    # Get full leaderboard
    # ------------------------------------------------------------------

    async def get_leaderboard(
        self,
        leaderboard_type: str = "points",
        location_type: str = "global",
        location_value: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:

        limit = min(limit, 100)
        rankings = await self._calculate_rankings(
            leaderboard_type, location_type, location_value
        )

        return {
            "leaderboard_type": leaderboard_type,
            "location_type": location_type,
            "location_value": location_value,
            "rankings": rankings[offset : offset + limit],
            "total_count": len(rankings),
        }

    # ------------------------------------------------------------------
    # Get leaderboard context for a user
    # ------------------------------------------------------------------

    async def get_leaderboard_context(
        self,
        user_id: str,
        leaderboard_type: str = "points",
        location_type: str = "global",
        location_value: Optional[str] = None,
        context_size: int = 5,
    ) -> Dict[str, Any]:

        rankings = await self._calculate_rankings(
            leaderboard_type, location_type, location_value
        )

        user_rank = None
        user_data = None
        for rank, entry in enumerate(rankings, 1):
            if entry["user_id"] == user_id:
                user_rank = rank
                user_data = entry
                break

        if not user_data:
            raise ValueError(f"User {user_id} not found in leaderboard")

        start = max(0, user_rank - context_size - 1)
        end = min(len(rankings), user_rank + context_size)

        return {
            "leaderboard_type": leaderboard_type,
            "location_type": location_type,
            "user_rank": user_rank,
            "user_total_users": len(rankings),
            "user_data": user_data,
            "top_10": rankings[:10],
            "neighbors": rankings[start:end],
        }

    # ------------------------------------------------------------------
    # Get single user rank
    # ------------------------------------------------------------------

    async def get_user_rank(
        self,
        user_id: str,
        leaderboard_type: str = "points",
        location_type: str = "global",
        location_value: Optional[str] = None,
    ) -> Dict[str, Any]:

        rankings = await self._calculate_rankings(
            leaderboard_type, location_type, location_value
        )

        for rank, entry in enumerate(rankings, 1):
            if entry["user_id"] == user_id:
                return {
                    "user_id": user_id,
                    "rank": rank,
                    "total_users": len(rankings),
                    "metric_value": entry["metric_value"],
                    "badge_tier": entry["badge_tier"],
                    "percentile": round((rank / len(rankings)) * 100, 2),
                }

        raise ValueError(f"User {user_id} not found in leaderboard")

    # ------------------------------------------------------------------
    # Internal ranking calculation
    # ------------------------------------------------------------------

    async def _calculate_rankings(
        self,
        leaderboard_type: str,
        location_type: str,
        location_value: Optional[str],
    ) -> List[Dict[str, Any]]:

        lbs = self.get_available_leaderboards()
        if leaderboard_type not in lbs:
            raise ValueError(f"Unknown leaderboard type: {leaderboard_type}")

        metric = lbs[leaderboard_type]["metric"]
        users = await self._get_users_for_location(location_type, location_value)

        rankings = []
        for user in users:
            metric_value = await self._get_metric_value(str(user["id"]), metric)
            rankings.append(
                {
                    "user_id": str(user["id"]),
                    "username": user["username"],
                    "display_name": user["display_name"] or user["username"],
                    "avatar_url": user["avatar_url"],
                    "badge_tier": user["badge_tier"] or "bronze",
                    "metric_value": metric_value,
                    "total_points": user["total_points"] or 0,
                    "admin_region": user["admin_region"],
                }
            )

        rankings.sort(key=lambda x: x["metric_value"], reverse=True)
        return rankings

    async def _get_users_for_location(
        self, location_type: str, location_value: Optional[str]
    ) -> List:

        async with get_connection() as conn:

            if location_type == "global":
                return await conn.fetch("SELECT * FROM users")

            elif location_type == "region":
                if not location_value:
                    raise ValueError("Region name required for region filter")
                return await conn.fetch(
                    "SELECT * FROM users WHERE admin_region=$1",
                    location_value,
                )

            elif location_type == "community":
                if not location_value:
                    raise ValueError("Coordinates required: lat,lng,radius_km")
                parts = location_value.split(",")
                if len(parts) < 3:
                    raise ValueError(
                        "Community filter requires format: lat,lng,radius_km"
                    )
                lat, lng, radius = float(parts[0]), float(parts[1]), float(parts[2])

                all_users = await conn.fetch("SELECT * FROM users")
                nearby = []
                for user in all_users:
                    last_issue = await conn.fetchrow(
                        "SELECT latitude, longitude FROM issues WHERE user_id=$1 ORDER BY created_at DESC LIMIT 1",
                        user["id"],
                    )
                    if last_issue:
                        dist = DistanceCalculator.haversine(
                            lat, lng, last_issue["latitude"], last_issue["longitude"]
                        )
                        if dist <= radius:
                            nearby.append(user)
                return nearby

            else:
                raise ValueError(f"Unknown location type: {location_type}")

    async def _get_metric_value(self, user_id: str, metric: str) -> float:
        async with get_connection() as conn:
            if metric == "collections_count":
                return (
                    await conn.fetchval(
                        "SELECT COUNT(*) FROM collections WHERE collected_by_user_id=$1 AND status='verified'",
                        user_id,
                    )
                    or 0
                )
            else:
                val = await conn.fetchval(
                    f"SELECT {metric} FROM users WHERE id=$1",
                    user_id,
                )
                return float(val or 0)

    # ------------------------------------------------------------------
    # Weekly badge reset
    # ------------------------------------------------------------------

    async def reset_weekly_badges(self) -> Dict[str, int]:
        result = await self.points_service.recalculate_weekly_badges()
        rising_star_count = await self._award_rising_star_badges()
        result["rising_star"] = rising_star_count
        return result

    async def _award_rising_star_badges(self) -> int:
        week_start = PointsService._get_week_start_date()
        count = 0

        async with get_connection() as conn:
            users = await conn.fetch("SELECT id FROM users")

            user_weekly_pts = []
            for row in users:
                uid = str(row["id"])
                pts = await conn.fetchval(
                    "SELECT COALESCE(SUM(points_earned),0) FROM user_activity_log WHERE user_id=$1 AND activity_date>=$2",
                    uid,
                    week_start,
                )
                if pts > 0:
                    user_weekly_pts.append({"user_id": uid, "weekly_points": pts})

            user_weekly_pts.sort(key=lambda x: x["weekly_points"], reverse=True)
            top_10 = user_weekly_pts[:10]

            for i, entry in enumerate(top_10):
                uid = entry["user_id"]
                exists = await conn.fetchval(
                    "SELECT id FROM user_badges WHERE user_id=$1 AND badge_type='rising_star' AND week_start_date=$2",
                    uid,
                    week_start,
                )
                if not exists:
                    await conn.execute(
                        """
                        INSERT INTO user_badges
                            (user_id, badge_type, is_permanent, earned_at, current_week_earned, week_start_date, metadata)
                        VALUES ($1, 'rising_star', FALSE, NOW(), TRUE, $2, $3)
                        """,
                        uid,
                        week_start,
                        json.dumps(
                            {
                                "weekly_points": entry["weekly_points"],
                                "weekly_rank": i + 1,
                            }
                        ),
                    )
                    count += 1

        return count
