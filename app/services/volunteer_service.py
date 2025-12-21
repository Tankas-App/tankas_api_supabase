from app.database import supabase
from app.utils.points_calculator import PointsCalculator
from datetime import datetime
from typing import Optional, List

class VolunteerService:
    """Handle volunteer management and group coordination"""
    
    def __init__(self):
        """Initialize with Supabase client"""
        self.supabase = supabase
    
    async def join_issue(
        self,
        user_id: str,
        issue_id: str,
        solo_work: bool = False,
        equipment_needed: Optional[List[str]] = None
    ) -> dict:
        """
        Volunteer joins an issue
        
        Flow:
        1. Check if issue exists
        2. Check if group exists for this issue
        3. If no group → Create group, user becomes leader
        4. If group exists → Add user to group as regular member
        5. Create volunteer record
        
        Args:
            user_id: UUID of volunteering user
            issue_id: UUID of issue to volunteer for
            solo_work: Whether they're working alone
            equipment_needed: List of equipment IDs they're bringing
            
        Returns:
            Dictionary with volunteer details
            
        Raises:
            ValueError: If issue not found or user already volunteering
        """
        try:
            # Step 1: Verify issue exists
            issue_response = self.supabase.table("issues").select("*").eq("id", issue_id).execute()
            if not issue_response.data:
                raise ValueError("Issue not found")
            
            issue = issue_response.data[0]
            
            # Step 2: Check if user already volunteering for this issue
            existing = self.supabase.table("volunteers").select("id").eq("user_id", user_id).eq("issue_id", issue_id).execute()
            if existing.data and len(existing.data) > 0:
                raise ValueError("You're already volunteering for this issue")
            
            # Step 3: Check if group exists for this issue
            group_response = self.supabase.table("groups").select("*").eq("issue_id", issue_id).execute()
            
            group_id = None
            is_leader = False
            
            if not group_response.data or len(group_response.data) == 0:
                # No group exists → Create group and make user leader
                print("Creating new group...")
                group_data = {
                    "issue_id": issue_id,
                    "leader_id": user_id,
                    "name": f"Cleanup Group - {issue['title'][:30]}",
                    "status": "active",
                    "created_at": datetime.utcnow().isoformat()
                }
                group_response = self.supabase.table("groups").insert(group_data).execute()
                
                if not group_response.data:
                    raise Exception("Failed to create group")
                
                group_id = group_response.data[0]["id"]
                is_leader = True
                print(f"Group created: {group_id}, User is leader")
            else:
                # Group exists → Add user as regular member
                group_id = group_response.data[0]["id"]
                is_leader = False
                print(f"Joining existing group: {group_id}")
            
            # Step 4: Create volunteer record
            volunteer_data = {
                "user_id": user_id,
                "issue_id": issue_id,
                "group_id": group_id,
                "is_leader": is_leader,
                "solo_work": solo_work,
                "equipment_needed": equipment_needed or [],
                "verified": False,
                "leader_validated": False,
                "points_earned": 0,
                "created_at": datetime.utcnow().isoformat()
            }
            
            vol_response = self.supabase.table("volunteers").insert(volunteer_data).execute()
            
            if not vol_response.data:
                raise Exception("Failed to create volunteer record")
            
            volunteer = vol_response.data[0]
            
            return {
                "volunteer_id": volunteer["id"],
                "issue_id": issue_id,
                "group_id": group_id,
                "is_leader": is_leader,
                "message": "You've joined the issue!" + (" as leader!" if is_leader else "")
            }
        
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to join issue: {str(e)}")
    
    async def transfer_leadership(
        self,
        current_leader_volunteer_id: str,
        new_leader_volunteer_id: str
    ) -> dict:
        """
        Transfer leadership from one volunteer to another
        
        Args:
            current_leader_volunteer_id: Current leader's volunteer ID
            new_leader_volunteer_id: New leader's volunteer ID
            
        Returns:
            Updated group details
        """
        try:
            # Step 1: Get current leader's volunteer record
            current = self.supabase.table("volunteers").select("*").eq("id", current_leader_volunteer_id).execute()
            if not current.data:
                raise ValueError("Current leader not found")
            
            current_leader = current.data[0]
            if not current_leader["is_leader"]:
                raise ValueError("You are not a leader")
            
            # Step 2: Get new leader's volunteer record
            new = self.supabase.table("volunteers").select("*").eq("id", new_leader_volunteer_id).execute()
            if not new.data:
                raise ValueError("New leader not found")
            
            new_leader = new.data[0]
            
            # Step 3: Verify they're in the same group
            if current_leader["group_id"] != new_leader["group_id"]:
                raise ValueError("Both volunteers must be in the same group")
            
            # Step 4: Update both volunteer records
            # Current leader becomes regular member
            self.supabase.table("volunteers").update({"is_leader": False}).eq("id", current_leader_volunteer_id).execute()
            
            # New volunteer becomes leader
            self.supabase.table("volunteers").update({"is_leader": True}).eq("id", new_leader_volunteer_id).execute()
            
            # Step 5: Update group's leader_id
            self.supabase.table("groups").update({"leader_id": new_leader["user_id"]}).eq("id", current_leader["group_id"]).execute()
            
            return {
                "message": "Leadership transferred successfully",
                "new_leader_id": new_leader["user_id"],
                "new_leader_name": new_leader.get("username", "Unknown")
            }
        
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to transfer leadership: {str(e)}")
    
    async def get_group_members(self, group_id: str) -> dict:
        """
        Get all members of a group
        
        Args:
            group_id: UUID of the group
            
        Returns:
            Group details with member list
        """
        try:
            # Get group
            group_response = self.supabase.table("groups").select("*").eq("id", group_id).execute()
            if not group_response.data:
                raise ValueError("Group not found")
            
            group = group_response.data[0]
            
            # Get volunteers in group
            volunteers_response = self.supabase.table("volunteers").select("*").eq("group_id", group_id).execute()
            
            if not volunteers_response.data:
                members = []
            else:
                # Get user details for each volunteer
                members = []
                for vol in volunteers_response.data:
                    user_response = self.supabase.table("users").select("username, display_name, avatar_url").eq("id", vol["user_id"]).execute()
                    
                    if user_response.data:
                        user = user_response.data[0]
                        members.append({
                            "volunteer_id": vol["id"],
                            "user_id": vol["user_id"],
                            "username": user.get("username", "Unknown"),
                            "display_name": user.get("display_name", "Unknown"),
                            "avatar_url": user.get("avatar_url"),
                            "is_leader": vol["is_leader"],
                            "solo_work": vol["solo_work"]
                        })
            
            return {
                "group_id": group_id,
                "issue_id": group["issue_id"],
                "leader_id": group["leader_id"],
                "members": members,
                "member_count": len(members),
                "created_at": group["created_at"]
            }
        
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to fetch group members: {str(e)}")
    
    async def get_volunteer_profile(self, user_id: str) -> dict:
        """
        Get complete volunteer profile with history
        
        Args:
            user_id: UUID of the user
            
        Returns:
            User profile with volunteering history
        """
        try:
            # Get user info
            user_response = self.supabase.table("users").select("*").eq("id", user_id).execute()
            if not user_response.data:
                raise ValueError("User not found")
            
            user = user_response.data[0]
            
            # Get all volunteer records for this user
            volunteers_response = self.supabase.table("volunteers").select("*").eq("user_id", user_id).execute()
            
            history = []
            active_issues = []
            
            if volunteers_response.data:
                for vol in volunteers_response.data:
                    # Get issue details
                    issue_response = self.supabase.table("issues").select("*").eq("id", vol["issue_id"]).execute()
                    
                    if issue_response.data:
                        issue = issue_response.data[0]
                        location = f"{issue['latitude']}, {issue['longitude']}"
                        
                        history_item = {
                            "issue_id": issue["id"],
                            "title": issue["title"],
                            "description": issue["description"],
                            "location": location,
                            "difficulty": issue["difficulty"],
                            "priority": issue["priority"],
                            "points_earned": vol["points_earned"],
                            "volunteered_at": vol["created_at"],
                            "completed_at": vol.get("completed_at"),
                            "was_verified": vol["verified"],
                            "group_size": 1  # We'll calculate this below
                        }
                        
                        # Get group size
                        if vol["group_id"]:
                            group_members = self.supabase.table("volunteers").select("id").eq("group_id", vol["group_id"]).execute()
                            history_item["group_size"] = len(group_members.data) if group_members.data else 1
                        
                        history.append(history_item)
                        
                        # Track active issues (where issue is still open)
                        if issue["status"] == "open":
                            active_issues.append(issue["id"])
            
            return {
                "user_id": user_id,
                "username": user["username"],
                "display_name": user["display_name"],
                "avatar_url": user.get("avatar_url"),
                "total_points": user["total_points"],
                "tasks_completed": user["tasks_completed"],
                "volunteer_hours": user.get("volunteer_hours", 0),
                "badge_tier": user["badge_tier"],
                "volunteering_history": history,
                "active_issues": active_issues
            }
        
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to fetch volunteer profile: {str(e)}")