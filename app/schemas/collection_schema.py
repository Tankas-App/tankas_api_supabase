from pydantic import BaseModel
from typing import Optional, List

# ============ DESTINATION SCHEMAS ============

class CreateDestinationRequest(BaseModel):
    """Admin creates a new garbage collection destination"""
    name: str  # e.g., "Central Recycling Hub"
    description: Optional[str]
    latitude: float
    longitude: float
    address: str
    contact_person: Optional[str]
    contact_phone: Optional[str]
    operating_hours: Optional[str]  # e.g., "9AM-5PM"


class DestinationResponse(BaseModel):
    """Destination details"""
    destination_id: str
    name: str
    description: Optional[str]
    latitude: float
    longitude: float
    address: str
    contact_person: Optional[str]
    contact_phone: Optional[str]
    operating_hours: Optional[str]
    created_at: str


class AssignDestinationRequest(BaseModel):
    """Admin assigns a destination to a resolved issue"""
    issue_id: str
    destination_id: str


# ============ COLLECTION SCHEMAS ============

class StartCollectionRequest(BaseModel):
    """Collector starts collecting garbage from a resolved issue"""
    issue_id: str


class SubmitCollectionRequest(BaseModel):
    """Collector submits collected garbage for delivery"""
    issue_id: str
    destination_id: str
    notes: Optional[str]  # e.g., "Mixed plastic and paper"
    quantity_kg: Optional[float]  # Optional, admin can update later


class VerifyDeliveryRequest(BaseModel):
    """Admin/destination verifies garbage was delivered"""
    collection_id: str
    verified: bool
    notes: Optional[str]


class CollectionResponse(BaseModel):
    """Collection record details"""
    collection_id: str
    issue_id: str
    collector_id: str
    collector_name: str
    destination_id: str
    destination_name: str
    quantity_kg: Optional[float]
    notes: Optional[str]
    photo_url: Optional[str]
    status: str  # "in_progress", "submitted", "verified", "rejected"
    points_earned: int
    payment_amount: Optional[float]
    collected_at: str
    submitted_at: Optional[str]
    verified_at: Optional[str]


class CollectionListResponse(BaseModel):
    """List of collections for an issue"""
    issue_id: str
    collections: List[CollectionResponse]
    total_collections: int


class PaymentProofRequest(BaseModel):
    """Collector uploads proof of delivery at destination"""
    collection_id: str
    destination_id: str
    # Photo will be sent as file


class PaymentResponse(BaseModel):
    """Payment confirmation for delivery"""
    collection_id: str
    collector_id: str
    collector_name: str
    destination_name: str
    quantity_kg: Optional[float]
    points_earned: int
    payment_amount: float
    status: str  # "verified", "pending_review"
    message: str
    delivery_proof_url: Optional[str]