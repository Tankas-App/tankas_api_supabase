from pydantic import BaseModel
from typing import Optional, List

# ============ REQUEST SCHEMAS ============

class ConfirmParticipationRequest(BaseModel):
    """Volunteer confirms they participated in the cleanup"""
    issue_id: str
    group_id: str


class CompleteIssueRequest(BaseModel):
    """Leader marks issue as complete and uploads verification photo"""
    issue_id: str
    group_id: str
    # Photo will be sent as file in multipart/form-data


class VerifyVolunteerListRequest(BaseModel):
    """Leader confirms which volunteers actually showed up and worked"""
    issue_id: str
    group_id: str
    verified_volunteer_ids: List[str]  # IDs of volunteers who actually worked


class RetryVerificationRequest(BaseModel):
    """Leader retries verification with a new photo (after first attempt failed)"""
    issue_id: str
    group_id: str
    # New photo will be sent as file


# ============ RESPONSE SCHEMAS ============

class VerificationStatus(BaseModel):
    """Status of work verification"""
    verification_id: str
    issue_id: str
    group_id: str
    status: str  # "verified", "pending_review", "rejected"
    ai_confidence: float  # 0-100
    message: str
    retry_available: bool  # Can leader retry?


class VolunteerVerificationResponse(BaseModel):
    """Individual volunteer's verification status"""
    volunteer_id: str
    user_id: str
    username: str
    participated: bool  # Did they confirm participation?
    verified: bool  # Were they verified by leader?
    points_earned: int
    status: str  # "verified", "pending", "rejected", "awaiting_confirmation"


class IssueCompletionResponse(BaseModel):
    """Response when issue is marked complete"""
    issue_id: str
    group_id: str
    status: str  # "resolved"
    verification_photo_url: str
    verification_status: str  # "verified", "pending_review", "rejected"
    ai_confidence: float
    message: str
    volunteers: List[VolunteerVerificationResponse]


class DistributionSummary(BaseModel):
    """Summary of points distribution"""
    issue_id: str
    group_id: str
    total_points_available: int
    verified_volunteer_count: int
    points_per_volunteer: int
    leader_bonus: int
    distribution: dict  # {volunteer_id: points_earned}
    message: str