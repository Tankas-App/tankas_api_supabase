from app.database import supabase
from app.utils.exif_helper import ExifHelper
from app.utils.ai_service import AIService
from app.utils.points_calculator import PointsCalculator
from app.utils.cloudinary_helper import CloudinaryHelper
from app.services.point_service import PointsService  # NEW IMPORT
from datetime import datetime
from typing import Optional, Tuple

class IssueService:
    """Handle environmental issue management"""
    
    def __init__(self):
        """Initialize services"""
        self.supabase = supabase
        self.ai_service = AIService()
        self.points_service = PointsService()  # NEW
        
        # Points for reporting an issue
        self.ISSUE_REPORT_POINTS = 15  # NEW
    
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
        1. Upload photo to Cloudinary
        2. Extract EXIF location (if available)
        3. Send photo to Google Vision for AI analysis
        4. Calculate difficulty and points based on AI results
        5. Create issue record in database
        6. Award points to reporter (via PointsService)
        
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
            # Step 1: Upload photo to Cloudinary
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
                raise ValueError(ai_analysis.get("error", "Image analysis failed - this doesn't appear to be an environmental cleanup issue"))
            
            # Step 4: Extract data from AI analysis
            ai_difficulty = ai_analysis.get("difficulty", "medium")
            ai_description = ai_analysis.get("description", f"Environmental issue reported at {latitude}, {longitude}")
            ai_confidence = ai_analysis.get("confidence", 0)
            ai_labels = ai_analysis.get("labels", [])
            
            # Use user-provided description if available, otherwise use AI-generated
            final_description = description or ai_description
            
            # Validate priority
            if priority.lower() not in ["low", "medium", "high"]:
                priority = "medium"
            
            # Step 5: Calculate points for this issue based on AI-determined difficulty
            print("Step 5: Calculating points...")
            points_assigned = PointsCalculator.calculate_issue_points(ai_difficulty, priority.lower())
            
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
                "difficulty": ai_difficulty,
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
            
            # Step 7: Award points to reporter
            print("Step 7: Awarding points to reporter...")
            await self.points_service.award_points(
                user_id=user_id,
                points=self.ISSUE_REPORT_POINTS,
                activity_type="issue_reported",
                reference_id=created_issue["id"],
                reference_type="issue",
                metadata={
                    "ai_difficulty": ai_difficulty,
                    "ai_confidence": ai_confidence,
                    "priority": priority
                }
            )
            
            print(f"[SUCCESS] Issue created with ID: {created_issue['id']}")
            
            return {
                "issue": created_issue,
                "ai_analysis": {
                    "difficulty": ai_difficulty,
                    "description": ai_description,
                    "confidence": ai_confidence,
                    "labels": ai_labels
                }
            }
        
        except ValueError as e:
            raise ValueError(f"Validation error: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to create issue: {str(e)}")
    
    async def _upload_photo_to_storage(self, photo_bytes: bytes, user_id: str) -> str:
        """
        Upload photo to Cloudinary
        
        Args:
            photo_bytes: Raw photo data
            user_id: User's UUID (for organizing in Cloudinary)
            
        Returns:
            Public URL of uploaded photo
        """
        try:
            # Upload to Cloudinary
            photo_url = await CloudinaryHelper.upload_photo(photo_bytes, folder=f"tankas-issues/{user_id}")
            return photo_url
        
        except Exception as e:
            print(f"DEBUG: Photo upload error: {e}")
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
            # Fetch all open issues
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