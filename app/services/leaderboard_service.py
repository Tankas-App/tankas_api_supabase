from app.database import supabase
from app.services.point_service import PointsService
from app.utils.distance_calculator import DistanceCalculator
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import asyncio

class LeaderboardService:
    """Handle leaderboard calculations, caching, and weekly badge resets"""
    
    def __init__(self):
        """Initialize services"""
        self.supabase = supabase
        self.points_service = PointsService()
        
        # Cache duration in minutes
        self.CACHE_TTL_MINUTES = 5
    
    # ============ LEADERBOARD TYPES & AVAILABLE LISTS ============
    
    @staticmethod
    def get_available_leaderboards() -> Dict[str, Dict[str, Any]]:
        """
        Get all available leaderboard types and their descriptions
        
        Returns:
            Dict with leaderboard metadata
        """
        return {
            "points": {
                "name": "Points Leaderboard",
                "description": "Ranked by total points earned",
                "metric": "total_points",
                "order": "DESC"
            },
            "issues_reported": {
                "name": "Issue Reporter Leaderboard",
                "description": "Ranked by number of issues reported",
                "metric": "issues_reported",
                "order": "DESC"
            },
            "collections": {
                "name": "Collector Leaderboard",
                "description": "Ranked by number of successful collections",
                "metric": "collections_count",
                "order": "DESC"
            },
            "kg_collected": {
                "name": "Garbage Master Leaderboard",
                "description": "Ranked by total kg of garbage collected",
                "metric": "total_kg_collected",
                "order": "DESC"
            },
            "volunteer_hours": {
                "name": "Volunteer Hours Leaderboard",
                "description": "Ranked by total volunteer hours",
                "metric": "volunteer_hours",
                "order": "DESC"
            }
        }
    
    # ============ MAIN LEADERBOARD ENDPOINTS ============
    
    async def get_leaderboard(
        self,
        leaderboard_type: str = "points",
        location_type: str = "global",
        location_value: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get a full leaderboard (top N users)
        
        Args:
            leaderboard_type: Type of leaderboard (points, issues_reported, etc.)
            location_type: "global", "region", or "community"
            location_value: Region name or "lat,lng,radius_km" for community
            limit: Number of results (max 100)
            offset: Pagination offset
            
        Returns:
            Leaderboard data with rankings
        """
        try:
            print(f"[LEADERBOARD] Fetching {leaderboard_type} ({location_type})")
            
            # Validate inputs
            limit = min(limit, 100)  # Max 100
            
            # Check cache first
            cache_key = f"{leaderboard_type}:{location_type}:{location_value}"
            cached = await self._get_cache(cache_key)
            
            if cached:
                print(f"[CACHE HIT] Returning cached data")
                return {
                    "leaderboard_type": leaderboard_type,
                    "location_type": location_type,
                    "location_value": location_value,
                    "cached": True,
                    "cached_at": cached[0]["cached_at"],
                    "rankings": cached[limit + offset:limit + offset + limit],
                    "total_count": len(cached)
                }
            
            # Not in cache, calculate fresh
            print(f"[CACHE MISS] Calculating fresh rankings")
            rankings = await self._calculate_rankings(
                leaderboard_type,
                location_type,
                location_value
            )
            
            # Cache the results
            await self._cache_rankings(cache_key, rankings)
            
            return {
                "leaderboard_type": leaderboard_type,
                "location_type": location_type,
                "location_value": location_value,
                "cached": False,
                "rankings": rankings[offset:offset + limit],
                "total_count": len(rankings)
            }
        
        except Exception as e:
            print(f"[ERROR] Failed to get leaderboard: {str(e)}")
            raise Exception(f"Failed to get leaderboard: {str(e)}")
    
    async def get_leaderboard_context(
        self,
        user_id: str,
        leaderboard_type: str = "points",
        location_type: str = "global",
        location_value: Optional[str] = None,
        context_size: int = 5
    ) -> Dict[str, Any]:
        """
        Get leaderboard context for a specific user
        Returns: top 10 global + user's rank + neighbors
        
        Args:
            user_id: User UUID
            leaderboard_type: Type of leaderboard
            location_type: "global", "region", or "community"
            location_value: Region name or "lat,lng,radius_km"
            context_size: Number of neighbors above/below (default 5)
            
        Returns:
            Leaderboard context with user highlighted
        """
        try:
            print(f"[CONTEXT] Getting leaderboard context for user {user_id}")
            
            # Get full rankings
            rankings = await self._calculate_rankings(
                leaderboard_type,
                location_type,
                location_value
            )
            
            # Find user's position
            user_rank = None
            user_data = None
            
            for rank, entry in enumerate(rankings, 1):
                if entry["user_id"] == user_id:
                    user_rank = rank
                    user_data = entry
                    break
            
            if not user_data:
                raise ValueError(f"User {user_id} not found in leaderboard")
            
            # Get top 10
            top_10 = rankings[:10]
            
            # Get neighbors
            start_idx = max(0, user_rank - context_size - 1)
            end_idx = min(len(rankings), user_rank + context_size)
            neighbors = rankings[start_idx:end_idx]
            
            return {
                "leaderboard_type": leaderboard_type,
                "location_type": location_type,
                "location_value": location_value,
                "user_rank": user_rank,
                "user_total_users": len(rankings),
                "user_data": user_data,
                "top_10": top_10,
                "neighbors": neighbors,
                "context_size": context_size
            }
        
        except Exception as e:
            print(f"[ERROR] Failed to get leaderboard context: {str(e)}")
            raise Exception(f"Failed to get leaderboard context: {str(e)}")
    
    async def get_user_rank(
        self,
        user_id: str,
        leaderboard_type: str = "points",
        location_type: str = "global",
        location_value: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get just a user's current rank (always fresh, not cached)
        
        Args:
            user_id: User UUID
            leaderboard_type: Type of leaderboard
            location_type: "global", "region", or "community"
            location_value: Region name or "lat,lng,radius_km"
            
        Returns:
            User's rank and stats
        """
        try:
            # Always calculate fresh for personal rank
            rankings = await self._calculate_rankings(
                leaderboard_type,
                location_type,
                location_value
            )
            
            for rank, entry in enumerate(rankings, 1):
                if entry["user_id"] == user_id:
                    return {
                        "user_id": user_id,
                        "rank": rank,
                        "total_users": len(rankings),
                        "metric_value": entry["metric_value"],
                        "badge_tier": entry["badge_tier"],
                        "percentile": round((rank / len(rankings)) * 100, 2)
                    }
            
            raise ValueError(f"User {user_id} not found in leaderboard")
        
        except Exception as e:
            raise Exception(f"Failed to get user rank: {str(e)}")
    
    # ============ INTERNAL RANKING CALCULATION ============
    
    async def _calculate_rankings(
        self,
        leaderboard_type: str,
        location_type: str,
        location_value: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Calculate rankings for a specific leaderboard
        
        This is the core logic that queries users and ranks them
        
        Args:
            leaderboard_type: Type of leaderboard
            location_type: "global", "region", or "community"
            location_value: Region name or coordinates
            
        Returns:
            List of ranked users
        """
        try:
            leaderboards = self.get_available_leaderboards()
            
            if leaderboard_type not in leaderboards:
                raise ValueError(f"Unknown leaderboard type: {leaderboard_type}")
            
            lb_config = leaderboards[leaderboard_type]
            metric = lb_config["metric"]
            
            # Get users based on location filter
            users = await self._get_users_for_location(location_type, location_value)
            
            # Calculate metric values for each user
            rankings = []
            for user in users:
                metric_value = await self._get_metric_value(user["id"], metric)
                
                rankings.append({
                    "user_id": user["id"],
                    "username": user["username"],
                    "display_name": user.get("display_name", user["username"]),
                    "avatar_url": user.get("avatar_url"),
                    "badge_tier": user.get("badge_tier", "bronze"),
                    "metric_value": metric_value,
                    "total_points": user.get("total_points", 0),
                    "admin_region": user.get("admin_region")
                })
            
            # Sort by metric value (descending)
            rankings.sort(key=lambda x: x["metric_value"], reverse=True)
            
            return rankings
        
        except Exception as e:
            print(f"[ERROR] Failed to calculate rankings: {str(e)}")
            raise
    
    async def _get_users_for_location(
        self,
        location_type: str,
        location_value: Optional[str]
    ) -> List[Dict]:
        """
        Get users filtered by location
        
        Args:
            location_type: "global", "region", or "community"
            location_value: Region name or "lat,lng,radius_km"
            
        Returns:
            List of user objects
        """
        try:
            if location_type == "global":
                # Get all users
                response = self.supabase.table("users").select("*").execute()
                return response.data or []
            
            elif location_type == "region":
                # Get users in specific region
                if not location_value:
                    raise ValueError("Region name required for region filter")
                
                response = self.supabase.table("users").select("*").eq("admin_region", location_value).execute()
                return response.data or []
            
            elif location_type == "community":
                # Get users within radius (15km default)
                if not location_value:
                    raise ValueError("Coordinates required for community filter (lat,lng,radius)")
                
                parts = location_value.split(",")
                if len(parts) < 3:
                    raise ValueError("Community filter requires format: lat,lng,radius_km")
                
                lat = float(parts[0])
                lng = float(parts[1])
                radius = float(parts[2])
                
                # Get all users and filter by distance
                response = self.supabase.table("users").select("*").execute()
                users = response.data or []
                
                # Get issues for each user to get their location
                nearby_users = []
                for user in users:
                    # Get user's last issue location
                    issue_response = self.supabase.table("issues").select("latitude,longitude").eq("user_id", user["id"]).order("created_at", desc=True).limit(1).execute()
                    
                    if issue_response.data:
                        issue = issue_response.data[0]
                        distance = DistanceCalculator.haversine(
                            lat, lng,
                            issue["latitude"], issue["longitude"]
                        )
                        
                        if distance <= radius:
                            nearby_users.append(user)
                    else:
                        # If no issues, use provided coordinates as user location
                        # For now, skip users with no location data
                        pass
                
                return nearby_users
            
            else:
                raise ValueError(f"Unknown location type: {location_type}")
        
        except Exception as e:
            print(f"[ERROR] Failed to filter users by location: {str(e)}")
            raise
    
    async def _get_metric_value(self, user_id: str, metric: str) -> float:
        """
        Get a specific metric value for a user
        
        Args:
            user_id: User UUID
            metric: Metric name (total_points, issues_reported, etc.)
            
        Returns:
            Metric value
        """
        try:
            if metric == "collections_count":
                # Special case: count verified collections
                response = self.supabase.table("collections").select("id").eq("collected_by_user_id", user_id).eq("status", "verified").execute()
                return len(response.data or [])
            else:
                # Regular user metric
                response = self.supabase.table("users").select(metric).eq("id", user_id).execute()
                if response.data:
                    return response.data[0].get(metric, 0) or 0
                return 0
        
        except Exception as e:
            print(f"[ERROR] Failed to get metric {metric} for user {user_id}: {str(e)}")
            return 0
    
    # ============ CACHING LOGIC ============
    
    async def _get_cache(self, cache_key: str) -> Optional[List[Dict]]:
        """
        Get cached leaderboard data
        
        Args:
            cache_key: Cache key (format: "type:location_type:location_value")
            
        Returns:
            Cached rankings or None if expired
        """
        try:
            response = self.supabase.table("leaderboard_cache").select("*").eq("id", cache_key).execute()
            
            if not response.data:
                return None
            
            cache_entry = response.data[0]
            
            # Check if expired
            if datetime.fromisoformat(cache_entry["expires_at"]) < datetime.utcnow():
                # Delete expired cache
                self.supabase.table("leaderboard_cache").delete().eq("id", cache_key).execute()
                return None
            
            # Return cached rankings
            # Note: In real implementation, you'd deserialize the full ranking list
            # For now, this is simplified - you'd store rankings as JSONB
            return cache_entry.get("rankings", [])
        
        except Exception as e:
            print(f"[WARNING] Cache retrieval failed: {str(e)}")
            return None
    
    async def _cache_rankings(self, cache_key: str, rankings: List[Dict]) -> None:
        """
        Cache leaderboard rankings
        
        Args:
            cache_key: Cache key
            rankings: Rankings data to cache
        """
        try:
            expires_at = (datetime.utcnow() + timedelta(minutes=self.CACHE_TTL_MINUTES)).isoformat()
            
            cache_data = {
                "id": cache_key,
                "rankings": rankings,
                "cached_at": datetime.utcnow().isoformat(),
                "expires_at": expires_at
            }
            
            # Upsert (update if exists, insert if not)
            self.supabase.table("leaderboard_cache").upsert(cache_data).execute()
            
            print(f"[CACHE] Cached {len(rankings)} rankings for key: {cache_key}")
        
        except Exception as e:
            print(f"[WARNING] Cache write failed: {str(e)}")
    
    async def invalidate_cache(self, user_id: str) -> None:
        """
        Invalidate all cache entries for a user
        (Called when user gets points)
        
        Args:
            user_id: User UUID
        """
        try:
            # Delete all cache entries that include this user
            # In real implementation, you'd have better tracking
            # For now, we'll invalidate the most recent cache entries
            self.supabase.table("leaderboard_cache").delete().gte("cached_at", (datetime.utcnow() - timedelta(minutes=self.CACHE_TTL_MINUTES)).isoformat()).execute()
            
            print(f"[CACHE] Invalidated cache for user {user_id}")
        
        except Exception as e:
            print(f"[WARNING] Cache invalidation failed: {str(e)}")
    
    # ============ WEEKLY BADGE RESET ============
    
    async def reset_weekly_badges(self) -> Dict[str, int]:
        """
        Reset and recalculate weekly badges for all users
        
        This should be called:
        - Automatically every Monday at 00:00 UTC
        - Manually via admin endpoint
        
        Returns:
            Dict with counts of badges awarded
        """
        try:
            print("[WEEKLY] Starting weekly badge reset...")
            
            # Call points_service's recalculation method
            result = await self.points_service.recalculate_weekly_badges()
            
            # Also handle Rising Star badge (top 10 in points this week)
            await self._award_rising_star_badges()
            
            return result
        
        except Exception as e:
            print(f"[ERROR] Weekly badge reset failed: {str(e)}")
            raise
    
    async def _award_rising_star_badges(self) -> int:
        """
        Award Rising Star badge to top 10 users in points this week
        
        Returns:
            Number of badges awarded
        """
        try:
            week_start = PointsService._get_week_start_date()
            
            # Get top 10 users by points this week
            # Calculate weekly points from activity log
            users_response = self.supabase.table("users").select("id,username").execute()
            users = users_response.data or []
            
            user_weekly_points = []
            for user in users:
                activity_response = self.supabase.table("user_activity_log").select("points_earned").eq("user_id", user["id"]).gte("activity_date", week_start.isoformat()).execute()
                weekly_points = sum(a.get("points_earned", 0) for a in (activity_response.data or []))
                
                if weekly_points > 0:
                    user_weekly_points.append({
                        "user_id": user["id"],
                        "username": user["username"],
                        "weekly_points": weekly_points
                    })
            
            # Sort and get top 10
            user_weekly_points.sort(key=lambda x: x["weekly_points"], reverse=True)
            top_10 = user_weekly_points[:10]
            
            # Award badges to top 10
            badges_count = 0
            for user in top_10:
                existing = self.supabase.table("user_badges").select("id").eq("user_id", user["user_id"]).eq("badge_type", "rising_star").gte("earned_at", week_start.isoformat()).execute()
                
                if not existing.data:
                    self.supabase.table("user_badges").insert({
                        "user_id": user["user_id"],
                        "badge_type": "rising_star",
                        "is_permanent": False,
                        "earned_at": datetime.utcnow().isoformat(),
                        "current_week_earned": True,
                        "week_start_date": week_start.isoformat(),
                        "metadata": {"weekly_points": user["weekly_points"], "weekly_rank": top_10.index(user) + 1}
                    }).execute()
                    badges_count += 1
            
            print(f"[WEEKLY] Awarded {badges_count} Rising Star badges")
            return badges_count
        
        except Exception as e:
            print(f"[ERROR] Failed to award Rising Star badges: {str(e)}")
            return 0