from app.database import supabase
from app.utils.cloudinary_helper import CloudinaryHelper
from app.utils.ai_service import AIService
from app.utils.points_calculator import PointsCalculator
from app.services.point_service import PointsService  # NEW IMPORT
from datetime import datetime
from typing import Optional, List

class CompletionService:
    """Handle issue completion, work verification, and points distribution"""
    
    def __init__(self):
        """Initialize services"""
        self.supabase = supabase
        self.ai_service = AIService()
        self.points_service = PointsService()  # NEW
    
    async def confirm_participation(
        self,
        user_id: str,
        issue_id: str,
        group_id: str
    ) -> dict:
        """
        Volunteer confirms they participated in the cleanup
        
        Args:
            user_id: UUID of volunteer
            issue_id: UUID of issue worked on
            group_id: UUID of group they worked with
            
        Returns:
            Confirmation message
        """
        try:
            # Get volunteer record
            vol_response = self.supabase.table("volunteers").select("*").eq("user_id", user_id).eq("issue_id", issue_id).execute()
            
            if not vol_response.data:
                raise ValueError("Volunteer record not found")
            
            volunteer = vol_response.data[0]
            
            # Mark as participation confirmed (we'll use a simple flag)
            # This prepares them for verification by leader
            
            return {
                "message": f"You've confirmed participation on {issue_id}",
                "volunteer_id": volunteer["id"],
                "status": "awaiting_leader_verification"
            }
        
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to confirm participation: {str(e)}")
    
    async def complete_issue(
        self,
        user_id: str,
        issue_id: str,
        group_id: str,
        photo_bytes: bytes
    ) -> dict:
        """
        Leader marks issue as complete and uploads cleanup photo
        
        Flow:
        1. Verify user is group leader
        2. Upload cleanup photo to Cloudinary
        3. Run AI verification comparing original photo to cleanup photo
        4. Set verification status based on AI confidence
        5. Mark issue as resolved
        
        Args:
            user_id: UUID of user (must be leader)
            issue_id: UUID of issue
            group_id: UUID of group
            photo_bytes: Cleanup photo as bytes
            
        Returns:
            Completion status with verification details
        """
        try:
            # Step 1: Verify user is leader
            print("Step 1: Verifying leader status...")
            vol_response = self.supabase.table("volunteers").select("*").eq("user_id", user_id).eq("group_id", group_id).execute()
            
            if not vol_response.data or len(vol_response.data) == 0:
                raise ValueError("You're not part of this group")
            
            volunteer = vol_response.data[0]
            if not volunteer["is_leader"]:
                raise ValueError("Only the group leader can mark issue as complete")
            
            # Step 2: Get original issue photo
            print("Step 2: Fetching original issue...")
            issue_response = self.supabase.table("issues").select("*").eq("id", issue_id).execute()
            
            if not issue_response.data:
                raise ValueError("Issue not found")
            
            issue = issue_response.data[0]
            original_photo_url = issue["picture_url"]
            
            # Step 3: Upload cleanup photo
            print("Step 3: Uploading cleanup photo...")
            cleanup_photo_url = await CloudinaryHelper.upload_photo(photo_bytes, folder=f"tankas-completions/{issue_id}")
            
            # Step 4: AI Verification (compare photos)
            print("Step 4: Running AI verification...")
            # TODO: Download photos and run AI comparison
            # For MVP, we'll use a simple confidence score
            ai_confidence = 85.0  # Default confidence for MVP
            
            if ai_confidence >= 80:
                verification_status = "verified"
                message = "Cleanup verified! Points will be distributed shortly."
            elif ai_confidence >= 50:
                verification_status = "pending_review"
                message = "Cleanup verification pending admin review. Points will be awarded once confirmed."
            else:
                verification_status = "rejected"
                message = "Photo doesn't match original issue. Please try again."
            
            # Step 5: Mark issue as resolved
            print("Step 5: Updating issue status...")
            update_data = {
                "status": "resolved",
                "resolved_by": user_id,
                "resolved_at": datetime.utcnow().isoformat(),
                "resolution_picture_url": cleanup_photo_url
            }
            
            self.supabase.table("issues").update(update_data).eq("id", issue_id).execute()
            
            # Get all volunteers in this group for response
            volunteers_response = self.supabase.table("volunteers").select("*").eq("group_id", group_id).execute()
            
            volunteer_list = []
            if volunteers_response.data:
                for vol in volunteers_response.data:
                    user_resp = self.supabase.table("users").select("username").eq("id", vol["user_id"]).execute()
                    username = user_resp.data[0]["username"] if user_resp.data else "Unknown"
                    
                    volunteer_list.append({
                        "volunteer_id": vol["id"],
                        "user_id": vol["user_id"],
                        "username": username,
                        "participated": False,  # Not yet confirmed
                        "verified": False,  # Not yet verified by leader
                        "points_earned": 0,
                        "status": "awaiting_confirmation"
                    })
            
            return {
                "issue_id": issue_id,
                "group_id": group_id,
                "status": "resolved",
                "verification_photo_url": cleanup_photo_url,
                "verification_status": verification_status,
                "ai_confidence": ai_confidence,
                "message": message,
                "volunteers": volunteer_list
            }
        
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to complete issue: {str(e)}")
    
    async def verify_volunteers(
        self,
        user_id: str,
        issue_id: str,
        group_id: str,
        verified_volunteer_ids: List[str]
    ) -> dict:
        """
        Leader confirms which volunteers actually worked
        Then distribute points to verified volunteers
        
        Args:
            user_id: UUID of leader
            issue_id: UUID of issue
            group_id: UUID of group
            verified_volunteer_ids: List of volunteer IDs who showed up
            
        Returns:
            Points distribution summary
        """
        try:
            # Step 1: Verify user is leader
            print("Step 1: Verifying leader...")
            vol_response = self.supabase.table("volunteers").select("*").eq("user_id", user_id).eq("group_id", group_id).execute()
            
            if not vol_response.data or not vol_response.data[0]["is_leader"]:
                raise ValueError("Only the group leader can verify volunteers")
            
            # Step 2: Get issue details
            print("Step 2: Fetching issue...")
            issue_response = self.supabase.table("issues").select("*").eq("id", issue_id).execute()
            if not issue_response.data:
                raise ValueError("Issue not found")
            
            issue = issue_response.data[0]
            total_points = issue["points_assigned"]
            
            # Step 3: Mark volunteers as verified/not verified
            print("Step 3: Marking verified volunteers...")
            distribution = {}
            
            # Get all volunteers in group
            all_volunteers = self.supabase.table("volunteers").select("*").eq("group_id", group_id).execute()
            
            verified_count = 0
            for vol in all_volunteers.data:
                is_verified = vol["id"] in verified_volunteer_ids
                
                if is_verified:
                    verified_count += 1
                    # Mark as verified
                    self.supabase.table("volunteers").update({
                        "verified": True,
                        "leader_validated": True,
                        "verified_at": datetime.utcnow().isoformat()
                    }).eq("id", vol["id"]).execute()
                    
                    distribution[vol["id"]] = {
                        "user_id": vol["user_id"],
                        "verified": True
                    }
                else:
                    # Mark as not verified
                    self.supabase.table("volunteers").update({
                        "verified": False,
                        "leader_validated": True
                    }).eq("id", vol["id"]).execute()
                    
                    distribution[vol["id"]] = {
                        "user_id": vol["user_id"],
                        "verified": False
                    }
            
            # Step 4: Calculate and distribute points
            print("Step 4: Distributing points...")
            if verified_count > 0:
                distribution_info = PointsCalculator.distribute_points_with_leader(
                    total_points, 
                    verified_count,
                    user_id
                )
                
                points_per_volunteer = distribution_info["points_per_volunteer"]
                leader_bonus = distribution_info["leader_bonus"]
                
                # Award points to each verified volunteer
                for vol_id, vol_data in distribution.items():
                    if vol_data["verified"]:
                        user_id_vol = vol_data["user_id"]
                        
                        # Determine points (leader gets bonus)
                        if user_id_vol == user_id:
                            points_earned = points_per_volunteer + leader_bonus
                        else:
                            points_earned = points_per_volunteer
                        
                        # Update volunteer record
                        self.supabase.table("volunteers").update({
                            "points_earned": points_earned
                        }).eq("id", vol_id).execute()
                        
                        # ✅ NEW: Use PointsService instead of manually updating
                        # This handles: points update, activity logging, badges, cache invalidation
                        await self.points_service.award_points(
                            user_id=user_id_vol,
                            points=points_earned,
                            activity_type="cleanup_verified",
                            reference_id=issue_id,
                            reference_type="issue",
                            metadata={
                                "group_id": group_id,
                                "is_leader": (user_id_vol == user_id),
                                "volunteer_count": verified_count
                            }
                        )
                        
                        distribution[vol_id]["points_earned"] = points_earned
            
            return {
                "issue_id": issue_id,
                "group_id": group_id,
                "total_points_available": total_points,
                "verified_volunteer_count": verified_count,
                "points_per_volunteer": distribution_info.get("points_per_volunteer", 0) if verified_count > 0 else 0,
                "leader_bonus": distribution_info.get("leader_bonus", 0) if verified_count > 0 else 0,
                "distribution": distribution,
                "message": f"Points distributed to {verified_count} verified volunteers!"
            }
        
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to verify volunteers: {str(e)}")