from app.database import supabase
from app.utils.exif_helper import ExifHelper
from app.utils.ai_service import AIService
from app.utils.points_calculator import PointsCalculator
from datetime import datetime
from typing import Optional, Tuple

class IssueService:
    """Handle environmental issue management"""
    
    def __init__(self):
        """Initialize services"""
        self.supabase = supabase
        self.ai_service = AIService()
    
    async def create_issue(
        self,
        user_id: str,
        title: str,
        description: Optional[str],
        photo_bytes: bytes,
        latitude: float,
        longitude: float,
        priority: str = "medium"
    ) -> dict:
        """
        Create a new environmental issue
        
        Flow:
        1. Upload photo to Supabase Storage
        2. Extract EXIF location (if available)
        3. Send photo to Google Vision for AI analysis
        4. Calculate difficulty and points
        5. Create issue record in database
        
        Args:
            user_id: UUID of user reporting the issue
            title: Issue title (optional, can be auto-generated)
            description: Issue description (optional)
            photo_bytes: Raw photo data
            latitude: GPS latitude coordinate
            longitude: GPS longitude coordinate
            priority: "low", "medium", or "high"
            
        Returns:
            Dictionary with created issue data
            
        Raises:
            ValueError: If validation fails
            Exception: If any step fails
        """
        try:
            # Step 1: Upload photo to Supabase Storage
            print("Step 1: Uploading photo to storage...")
            photo_url = await self._upload_photo_to_storage(photo_bytes, user_id)
            
            # Step 2: Extract EXIF location (if available)
            print("Step 2: Extracting EXIF data...")
            exif_location = ExifHelper.extract_gps_coordinates(photo_bytes)
            
            # Use EXIF location if available, otherwise use provided coordinates
            if exif_location:
                latitude, longitude = exif_location
                location_source = "exif"
            else:
                location_source = "manual"
            
            # Step 3: Send to Google Vision for AI analysis
            print("Step 3: Analyzing image with Google Vision...")
            ai_analysis = await self.ai_service.analyze_issue_image(photo_bytes)
            
            # Check if this is a valid cleanup issue
            if not ai_analysis.get("is_valid_issue"):
                raise ValueError(ai_analysis.get("error", "Image analysis failed"))
            
            # Step 4: Extract data from AI analysis
            ai_difficulty = ai_analysis["difficulty"]
            ai_description = ai_analysis["description"]
            ai_confidence = ai_analysis["confidence"]
            ai_labels = ai_analysis["labels"]
            
            # Use AI-generated description if user didn't provide one
            final_description = description or ai_description
            
            # Use AI-determined difficulty
            difficulty = ai_difficulty
            
            # Validate priority
            if priority.lower() not in ["low", "medium", "high"]:
                priority = "medium"
            
            # Step 5: Calculate points for this issue
            print("Step 5: Calculating points...")
            points_assigned = PointsCalculator.calculate_issue_points(difficulty, priority.lower())
            
            # Step 6: Create issue record in database
            print("Step 6: Creating issue in database...")
            issue_data = {
                "user_id": user_id,
                "title": title or ai_description,  # Use AI description as title if not provided
                "description": final_description,
                "picture_url": photo_url,
                "latitude": latitude,
                "longitude": longitude,
                "priority": priority.lower(),
                "difficulty": difficulty,
                "ai_labels": [label["name"] for label in ai_labels],
                "ai_confidence_score": ai_confidence,
                "points_assigned": points_assigned,
                "status": "open",
                "location_source": location_source,
                "created_at": datetime.utcnow().isoformat()
            }
            
            response = self.supabase.table("issues").insert(issue_data).execute()
            
            if not response.data or len(response.data) == 0:
                raise Exception("Failed to create issue in database")
            
            created_issue = response.data[0]
            
            # Step 7: Increment user's issues_reported counter
            await self._increment_user_stat(user_id, "issues_reported", 1)
            
            return {
                "issue": created_issue,
                "ai_analysis": ai_analysis
            }
        
        except ValueError as e:
            raise ValueError(f"Validation error: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to create issue: {str(e)}")
    
    async def _upload_photo_to_storage(self, photo_bytes: bytes, user_id: str) -> str:
        """
        Upload photo to Supabase Storage
        
        Args:
            photo_bytes: Raw photo data
            user_id: User's UUID (for organizing storage)
            
        Returns:
            Public URL of uploaded photo
        """
        try:
            # Create a unique filename
            timestamp = datetime.utcnow().isoformat()
            filename = f"{user_id}/{timestamp}.jpg"
            
            # Upload to Supabase Storage
            response = self.supabase.storage.from_("issues").upload(
                filename,
                photo_bytes
            )
            
            # Get public URL
            public_url = self.supabase.storage.from_("issues").get_public_url(filename)
            
            return public_url
        
        except Exception as e:
            print(f"DEBUG: Full error: {e}")
            print(f"DEBUG: Error type: {type(e)}")
            raise Exception(f"Photo upload failed: {str(e)}")
    
    async def get_issue(self, issue_id: str) -> dict:
        """
        Get issue details by ID
        
        Args:
            issue_id: The issue's UUID
            
        Returns:
            Issue data
            
        Raises:
            ValueError: If issue not found
        """
        try:
            response = self.supabase.table("issues").select("*").eq("id", issue_id).execute()
            
            if not response.data or len(response.data) == 0:
                raise ValueError("Issue not found")
            
            return response.data[0]
        
        except ValueError as e:
            raise e
        except Exception as e:
            raise Exception(f"Failed to fetch issue: {str(e)}")
    
    async def get_nearby_issues(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0
    ) -> list:
        """
        Get issues near a location (within radius_km)
        
        Args:
            latitude: User's latitude
            longitude: User's longitude
            radius_km: Search radius in kilometers (default 5km)
            
        Returns:
            List of nearby issues
        """
        try:
            # For MVP, we'll fetch all open issues and filter in Python
            # In production, use PostGIS for better performance
            response = self.supabase.table("issues").select("*").eq("status", "open").execute()
            
            if not response.data:
                return []
            
            # Filter by distance using Haversine formula
            from app.utils.distance_calculator import DistanceCalculator
            
            nearby = []
            for issue in response.data:
                distance = DistanceCalculator.haversine(
                    latitude,
                    longitude,
                    issue["latitude"],
                    issue["longitude"]
                )
                
                if distance <= radius_km:
                    issue["distance_km"] = round(distance, 2)
                    nearby.append(issue)
            
            # Sort by distance (closest first)
            nearby.sort(key=lambda x: x["distance_km"])
            
            return nearby
        
        except Exception as e:
            raise Exception(f"Failed to fetch nearby issues: {str(e)}")
    
    async def resolve_issue(
        self,
        issue_id: str,
        resolved_by_user_id: str,
        resolution_photo_bytes: Optional[bytes] = None,
        resolution_latitude: Optional[float] = None,
        resolution_longitude: Optional[float] = None
    ) -> dict:
        """
        Mark an issue as resolved
        
        Args:
            issue_id: The issue's UUID
            resolved_by_user_id: User who resolved it
            resolution_photo_bytes: Optional before/after photo
            resolution_latitude: Optional location of resolution
            resolution_longitude: Optional location of resolution
            
        Returns:
            Updated issue data
        """
        try:
            # Upload resolution photo if provided
            resolution_photo_url = None
            if resolution_photo_bytes:
                resolution_photo_url = await self._upload_photo_to_storage(
                    resolution_photo_bytes,
                    resolved_by_user_id
                )
            
            # Update issue
            update_data = {
                "status": "resolved",
                "resolved_by": resolved_by_user_id,
                "resolved_at": datetime.utcnow().isoformat(),
                "resolution_picture_url": resolution_photo_url
            }
            
            if resolution_latitude and resolution_longitude:
                update_data["resolution_latitude"] = resolution_latitude
                update_data["resolution_longitude"] = resolution_longitude
            
            response = self.supabase.table("issues").update(update_data).eq("id", issue_id).execute()
            
            if not response.data:
                raise Exception("Failed to update issue")
            
            return response.data[0]
        
        except Exception as e:
            raise Exception(f"Failed to resolve issue: {str(e)}")
    
    async def _increment_user_stat(self, user_id: str, stat_name: str, increment: int) -> None:
        """
        Increment a user statistic (issues_reported, tasks_completed, etc.)
        
        Args:
            user_id: User's UUID
            stat_name: Name of the stat to increment
            increment: Amount to increment by
        """
        try:
            # Get current value
            response = self.supabase.table("users").select(stat_name).eq("id", user_id).execute()
            
            if not response.data:
                return
            
            current_value = response.data[0].get(stat_name, 0) or 0
            new_value = current_value + increment
            
            # Update
            self.supabase.table("users").update({stat_name: new_value}).eq("id", user_id).execute()
        
        except Exception as e:
            print(f"Warning: Failed to update user stat {stat_name}: {str(e)}")