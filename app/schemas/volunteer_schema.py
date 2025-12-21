from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# ============ REQUEST SCHEMAS ============

class JoinIssueRequest(BaseModel):
    """Request to join an issue as a volunteer"""
    issue_id: str
    solo_work: Optional[bool] = False  # True if working alone, False for group
    equipment_needed: Optional[List[str]] = None  # List of equipment IDs


class TransferLeadershipRequest(BaseModel):
    """Request to transfer leadership to another volunteer"""
    new_leader_volunteer_id: str  # ID of volunteer to transfer to


class VerifyVolunteersRequest(BaseModel):
    """Request to verify which volunteers actually worked"""
    verified_volunteer_ids: List[str]  # List of volunteer IDs who showed up


# ============ RESPONSE SCHEMAS ============

class VolunteerQuickResponse(BaseModel):
    """Quick volunteer info for displaying in group/issue lists"""
    volunteer_id: str
    user_id: str
    username: str
    display_name: str
    avatar_url: Optional[str]
    is_leader: bool
    solo_work: bool


class VolunteerHistoryItem(BaseModel):
    """Single item in volunteer's history"""
    issue_id: str
    title: str
    description: str
    location: str  # "latitude, longitude"
    difficulty: str
    priority: str
    points_earned: int
    volunteered_at: str  # ISO timestamp
    completed_at: Optional[str]  # ISO timestamp (null if not completed)
    was_verified: bool
    group_size: int  # How many people were in the group


class VolunteerProfileResponse(BaseModel):
    """Complete volunteer profile with history"""
    user_id: str
    username: str
    display_name: str
    avatar_url: Optional[str]
    total_points: int
    tasks_completed: int
    volunteer_hours: float
    badge_tier: str
    volunteering_history: List[VolunteerHistoryItem]
    active_issues: List[str]  # Issue IDs currently working on


class GroupMemberListResponse(BaseModel):
    """Response with list of group members"""
    group_id: str
    issue_id: str
    leader_id: str
    leader_name: str
    members: List[VolunteerQuickResponse]
    member_count: int
    created_at: str


class JoinIssueResponse(BaseModel):
    """Response when volunteer joins an issue"""
    volunteer_id: str
    issue_id: str
    group_id: str
    is_leader: bool
    message: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "volunteer_id": "vol-123",
                "issue_id": "issue-456",
                "group_id": "group-789",
                "is_leader": True,
                "message": "You've joined the issue and created a group as leader!"
            }
        }