from app.database import get_connection
from app.utils.cloudinary_helper import CloudinaryHelper
from app.utils.distance_calculator import DistanceCalculator
from app.services.point_service import PointsService  # NEW IMPORT
from datetime import datetime
from typing import Optional, List


class CollectionsService:
    """Handle garbage collection, delivery verification, and payments"""

    def __init__(self):
        pass
        self.points_service = PointsService()  # NEW

        # Default payment per kg (can be configured)
        self.PAYMENT_PER_KG = 2.0  # GHS per kg (adjust as needed)
        self.POINTS_PER_KG = 5  # Points per kg collected

    # ============ DESTINATION MANAGEMENT ============

    async def create_destination(
        self,
        name: str,
        latitude: float,
        longitude: float,
        address: str,
        description: Optional[str] = None,
        contact_person: Optional[str] = None,
        contact_phone: Optional[str] = None,
        operating_hours: Optional[str] = None,
    ) -> dict:
        """
        Admin creates a new collection destination

        Args:
            name: Name of the destination
            latitude: GPS latitude
            longitude: GPS longitude
            address: Physical address
            description: Optional description
            contact_person: Optional contact person name
            contact_phone: Optional contact phone
            operating_hours: Optional operating hours

        Returns:
            Created destination details
        """
        try:
            destination_data = {
                "name": name,
                "description": description,
                "latitude": latitude,
                "longitude": longitude,
                "address": address,
                "contact_person": contact_person,
                "contact_phone": contact_phone,
                "operating_hours": operating_hours,
                "created_at": datetime.utcnow().isoformat(),
            }

            response = (
                self.supabase.table("destinations").insert(destination_data).execute()
            )

            if not response.data:
                raise Exception("Failed to create destination")

            dest = response.data[0]

            return {
                "destination_id": dest["id"],
                "name": dest["name"],
                "description": dest.get("description"),
                "latitude": dest["latitude"],
                "longitude": dest["longitude"],
                "address": dest["address"],
                "contact_person": dest.get("contact_person"),
                "contact_phone": dest.get("contact_phone"),
                "operating_hours": dest.get("operating_hours"),
                "created_at": dest["created_at"],
            }

        except Exception as e:
            raise Exception(f"Failed to create destination: {str(e)}")

    async def get_nearby_destinations(
        self, latitude: float, longitude: float, radius_km: float = 5.0
    ) -> List[dict]:
        """
        Get collection destinations near an issue location

        Args:
            latitude: Issue latitude
            longitude: Issue longitude
            radius_km: Search radius in kilometers

        Returns:
            List of nearby destinations sorted by distance
        """
        try:
            # Fetch all destinations
            response = self.supabase.table("destinations").select("*").execute()

            if not response.data:
                return []

            # Filter by distance
            nearby = []
            for dest in response.data:
                distance = DistanceCalculator.haversine(
                    latitude, longitude, dest["latitude"], dest["longitude"]
                )

                if distance <= radius_km:
                    dest["distance_km"] = round(distance, 2)
                    nearby.append(dest)

            # Sort by distance
            nearby.sort(key=lambda x: x["distance_km"])

            return nearby

        except Exception as e:
            raise Exception(f"Failed to fetch nearby destinations: {str(e)}")

    async def assign_destination_to_issue(
        self, issue_id: str, destination_id: str
    ) -> dict:
        """
        Admin assigns a destination to a resolved issue

        Args:
            issue_id: UUID of the issue
            destination_id: UUID of the destination

        Returns:
            Updated issue with destination
        """
        try:
            # Verify issue exists and is resolved
            issue_response = (
                self.supabase.table("issues").select("*").eq("id", issue_id).execute()
            )

            if not issue_response.data:
                raise ValueError("Issue not found")

            issue = issue_response.data[0]
            if issue["status"] != "resolved":
                raise ValueError("Issue must be resolved before assigning destination")

            # Verify destination exists
            dest_response = (
                self.supabase.table("destinations")
                .select("*")
                .eq("id", destination_id)
                .execute()
            )

            if not dest_response.data:
                raise ValueError("Destination not found")

            destination = dest_response.data[0]

            # Update issue with destination
            self.supabase.table("issues").update(
                {
                    "destination_id": destination_id,
                    "assigned_destination_at": datetime.utcnow().isoformat(),
                }
            ).eq("id", issue_id).execute()

            return {
                "message": "Destination assigned successfully",
                "issue_id": issue_id,
                "destination_id": destination_id,
                "destination_name": destination["name"],
                "destination_address": destination["address"],
            }

        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to assign destination: {str(e)}")

    # ============ COLLECTION MANAGEMENT ============

    async def start_collection(self, user_id: str, issue_id: str) -> dict:
        """
        Collector starts collecting garbage from a resolved issue

        Args:
            user_id: UUID of collector
            issue_id: UUID of issue to collect from

        Returns:
            Collection started confirmation
        """
        try:
            # Verify issue exists and is resolved
            issue_response = (
                self.supabase.table("issues").select("*").eq("id", issue_id).execute()
            )

            if not issue_response.data:
                raise ValueError("Issue not found")

            issue = issue_response.data[0]
            if issue["status"] != "resolved":
                raise ValueError("Issue must be resolved before collection")

            # Verify issue has destination assigned
            if not issue.get("destination_id"):
                raise ValueError(
                    "Issue must have a destination assigned before collection"
                )

            # Check if collector already has active collection for this issue
            existing = (
                self.supabase.table("collections")
                .select("id")
                .eq("user_id", user_id)
                .eq("issue_id", issue_id)
                .eq("status", "in_progress")
                .execute()
            )

            if existing.data:
                raise ValueError("You already have an active collection for this issue")

            # Create collection record
            collection_data = {
                "issue_id": issue_id,
                "collected_by_user_id": user_id,
                "destination_id": issue["destination_id"],
                "status": "in_progress",
                "created_at": datetime.utcnow().isoformat(),
            }

            response = (
                self.supabase.table("collections").insert(collection_data).execute()
            )

            if not response.data:
                raise Exception("Failed to start collection")

            collection = response.data[0]

            return {
                "collection_id": collection["id"],
                "issue_id": issue_id,
                "message": "Collection started. Please submit when complete.",
                "status": "in_progress",
            }

        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to start collection: {str(e)}")

    async def submit_collection(
        self,
        user_id: str,
        issue_id: str,
        destination_id: str,
        photo_bytes: bytes,
        notes: Optional[str] = None,
        quantity_kg: Optional[float] = None,
    ) -> dict:
        """
        Collector submits collected garbage with photo and notes

        Args:
            user_id: UUID of collector
            issue_id: UUID of issue
            destination_id: UUID of destination
            photo_bytes: Photo of collected garbage
            notes: Optional notes about collection
            quantity_kg: Optional weight (can be updated by admin later)

        Returns:
            Submission confirmation
        """
        try:
            # Get collection record
            col_response = (
                self.supabase.table("collections")
                .select("*")
                .eq("collected_by_user_id", user_id)
                .eq("issue_id", issue_id)
                .eq("status", "in_progress")
                .execute()
            )

            if not col_response.data:
                raise ValueError("Collection record not found")

            collection = col_response.data[0]

            # Upload photo to Cloudinary
            photo_url = await CloudinaryHelper.upload_photo(
                photo_bytes, folder=f"tankas-collections/{issue_id}"
            )

            # Update collection record
            update_data = {
                "photo_url": photo_url,
                "notes": notes,
                "quantity_kg": quantity_kg,
                "status": "submitted",
                "submitted_at": datetime.utcnow().isoformat(),
            }

            self.supabase.table("collections").update(update_data).eq(
                "id", collection["id"]
            ).execute()

            # Get destination for response
            dest_response = (
                self.supabase.table("destinations")
                .select("*")
                .eq("id", destination_id)
                .execute()
            )
            destination = dest_response.data[0] if dest_response.data else None

            return {
                "collection_id": collection["id"],
                "issue_id": issue_id,
                "status": "submitted",
                "message": "Collection submitted! Awaiting verification at destination.",
                "destination_name": destination["name"] if destination else "Unknown",
                "photo_url": photo_url,
            }

        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to submit collection: {str(e)}")

    async def verify_delivery(
        self,
        collection_id: str,
        destination_id: str,
        photo_bytes: bytes,
        verified: bool = True,
        notes: Optional[str] = None,
        quantity_kg: Optional[float] = None,
    ) -> dict:
        """
        Admin/destination verifies delivery and calculates payment

        Args:
            collection_id: UUID of collection
            destination_id: UUID of destination
            photo_bytes: Delivery proof photo
            verified: Whether delivery is verified
            notes: Optional verification notes
            quantity_kg: Optional actual weight measured

        Returns:
            Payment confirmation
        """
        try:
            # Get collection record
            col_response = (
                self.supabase.table("collections")
                .select("*")
                .eq("id", collection_id)
                .execute()
            )

            if not col_response.data:
                raise ValueError("Collection not found")

            collection = col_response.data[0]

            # Upload proof photo
            proof_url = await CloudinaryHelper.upload_photo(
                photo_bytes, folder=f"tankas-deliveries/{collection_id}"
            )

            if verified:
                # Use provided quantity or fallback to submitted quantity
                final_quantity = quantity_kg or collection.get("quantity_kg") or 0

                # Calculate payment and points
                payment_amount = final_quantity * self.PAYMENT_PER_KG
                points_earned = int(final_quantity * self.POINTS_PER_KG)

                # Update collection as verified
                update_data = {
                    "status": "verified",
                    "verified": True,
                    "verified_at": datetime.utcnow().isoformat(),
                    "delivery_proof_url": proof_url,
                    "quantity_kg": final_quantity,
                    "notes": notes,
                }

                self.supabase.table("collections").update(update_data).eq(
                    "id", collection_id
                ).execute()

                # ✅ NEW: Update user's kg collected stat
                collector_id = collection["collected_by_user_id"]
                user_response = (
                    self.supabase.table("users")
                    .select("total_kg_collected")
                    .eq("id", collector_id)
                    .execute()
                )

                if user_response.data:
                    current_kg = user_response.data[0].get("total_kg_collected", 0) or 0
                    new_total_kg = current_kg + final_quantity
                    self.supabase.table("users").update(
                        {"total_kg_collected": new_total_kg}
                    ).eq("id", collector_id).execute()

                # ✅ NEW: Use PointsService to award points
                # This handles: points update, activity logging, badges, cache invalidation
                await self.points_service.award_points(
                    user_id=collector_id,
                    points=points_earned,
                    activity_type="collection_verified",
                    reference_id=collection_id,
                    reference_type="collection",
                    metadata={
                        "quantity_kg": final_quantity,
                        "destination_id": destination_id,
                        "payment_amount": payment_amount,
                    },
                )
            else:
                # Mark as rejected
                update_data = {
                    "status": "rejected",
                    "verified": False,
                    "delivery_proof_url": proof_url,
                    "notes": notes,
                }

                self.supabase.table("collections").update(update_data).eq(
                    "id", collection_id
                ).execute()

                payment_amount = 0
                points_earned = 0

            # Get collector info for response
            collector_response = (
                self.supabase.table("users")
                .select("username, display_name")
                .eq("id", collection["collected_by_user_id"])
                .execute()
            )
            collector = collector_response.data[0] if collector_response.data else {}

            # Get destination info
            dest_response = (
                self.supabase.table("destinations")
                .select("name")
                .eq("id", destination_id)
                .execute()
            )
            destination = dest_response.data[0] if dest_response.data else {}

            return {
                "collection_id": collection_id,
                "collector_id": collection["collected_by_user_id"],
                "collector_name": collector.get(
                    "display_name", collector.get("username", "Unknown")
                ),
                "destination_name": destination.get("name", "Unknown"),
                "quantity_kg": collection.get("quantity_kg"),
                "points_earned": points_earned,
                "payment_amount": payment_amount,
                "status": "verified" if verified else "rejected",
                "message": (
                    f"Delivery verified! Collector earned {points_earned} points and GHS {payment_amount}"
                    if verified
                    else "Delivery rejected"
                ),
                "delivery_proof_url": proof_url,
            }

        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to verify delivery: {str(e)}")

    # ============ RETRIEVAL & ANALYTICS ============

    async def get_collection_by_id(self, collection_id: str) -> dict:
        """
        Retrieve a collection by ID with full details

        Args:
            collection_id: UUID of collection

        Returns:
            Collection details with related data
        """
        try:
            col_response = (
                self.supabase.table("collections")
                .select("*")
                .eq("id", collection_id)
                .execute()
            )

            if not col_response.data:
                raise ValueError("Collection not found")

            collection = col_response.data[0]

            # Get related issue info
            issue_resp = (
                self.supabase.table("issues")
                .select("title, description, location")
                .eq("id", collection["issue_id"])
                .execute()
            )
            issue = issue_resp.data[0] if issue_resp.data else {}

            # Get destination info
            dest_resp = (
                self.supabase.table("destinations")
                .select("name, address")
                .eq("id", collection["destination_id"])
                .execute()
            )
            destination = dest_resp.data[0] if dest_resp.data else {}

            # Get collector info
            user_resp = (
                self.supabase.table("users")
                .select("username, display_name, avatar_url")
                .eq("id", collection["collected_by_user_id"])
                .execute()
            )
            collector = user_resp.data[0] if user_resp.data else {}

            return {
                "collection_id": collection["id"],
                "issue_id": collection["issue_id"],
                "issue_title": issue.get("title"),
                "collector_id": collection["collected_by_user_id"],
                "collector_name": collector.get(
                    "display_name", collector.get("username")
                ),
                "collector_avatar": collector.get("avatar_url"),
                "destination_name": destination.get("name"),
                "destination_address": destination.get("address"),
                "status": collection["status"],
                "quantity_kg": collection.get("quantity_kg"),
                "photo_url": collection.get("photo_url"),
                "delivery_proof_url": collection.get("delivery_proof_url"),
                "notes": collection.get("notes"),
                "created_at": collection["created_at"],
                "submitted_at": collection.get("submitted_at"),
                "verified_at": collection.get("verified_at"),
            }

        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to retrieve collection: {str(e)}")

    async def get_collector_statistics(self, user_id: str) -> dict:
        """
        Get collection statistics for a specific collector

        Args:
            user_id: UUID of collector

        Returns:
            Collector's stats including total collected, earnings, etc
        """
        try:
            collections_resp = (
                self.supabase.table("collections")
                .select("*")
                .eq("collected_by_user_id", user_id)
                .execute()
            )

            collections = collections_resp.data if collections_resp.data else []

            verified_collections = [c for c in collections if c["status"] == "verified"]

            total_kg = sum(c.get("quantity_kg") or 0 for c in verified_collections)
            total_earnings = total_kg * self.PAYMENT_PER_KG
            total_points = sum(
                int(c.get("quantity_kg") or 0 * self.POINTS_PER_KG)
                for c in verified_collections
            )

            return {
                "user_id": user_id,
                "total_collections": len(collections),
                "verified_collections": len(verified_collections),
                "pending_collections": len(
                    [
                        c
                        for c in collections
                        if c["status"] in ["in_progress", "submitted"]
                    ]
                ),
                "rejected_collections": len(
                    [c for c in collections if c["status"] == "rejected"]
                ),
                "total_kg_collected": round(total_kg, 2),
                "total_earnings_ghs": round(total_earnings, 2),
                "total_points_earned": total_points,
            }

        except Exception as e:
            raise Exception(f"Failed to retrieve statistics: {str(e)}")

    async def get_destination_collections(
        self, destination_id: str, status_filter: Optional[str] = None
    ) -> List[dict]:
        """
        Get all collections for a specific destination

        Args:
            destination_id: UUID of destination
            status_filter: Optional filter by status (submitted, verified, rejected)

        Returns:
            List of collections for the destination
        """
        try:
            query = (
                self.supabase.table("collections")
                .select("*")
                .eq("destination_id", destination_id)
            )

            if status_filter:
                query = query.eq("status", status_filter)

            response = query.execute()
            collections = response.data if response.data else []

            # Enrich with collector and issue info
            for col in collections:
                user_resp = (
                    self.supabase.table("users")
                    .select("username, display_name")
                    .eq("id", col["collected_by_user_id"])
                    .execute()
                )
                col["collector_name"] = (
                    user_resp.data[0]["display_name"] if user_resp.data else "Unknown"
                )

            return collections

        except Exception as e:
            raise Exception(f"Failed to retrieve destination collections: {str(e)}")

    async def get_pending_verifications(self, destination_id: str) -> List[dict]:
        """
        Get all submissions awaiting verification at a destination

        Args:
            destination_id: UUID of destination

        Returns:
            List of submitted collections awaiting verification
        """
        try:
            response = (
                self.supabase.table("collections")
                .select("*")
                .eq("destination_id", destination_id)
                .eq("status", "submitted")
                .order("submitted_at", desc=False)
                .execute()
            )

            collections = response.data if response.data else []

            # Enrich with collector and issue info
            for col in collections:
                user_resp = (
                    self.supabase.table("users")
                    .select("username, display_name")
                    .eq("id", col["collected_by_user_id"])
                    .execute()
                )
                col["collector_name"] = (
                    user_resp.data[0]["display_name"] if user_resp.data else "Unknown"
                )

                issue_resp = (
                    self.supabase.table("issues")
                    .select("title")
                    .eq("id", col["issue_id"])
                    .execute()
                )
                col["issue_title"] = (
                    issue_resp.data[0]["title"] if issue_resp.data else "Unknown"
                )

            return collections

        except Exception as e:
            raise Exception(f"Failed to retrieve pending verifications: {str(e)}")

    # ============ UPDATE & DELETE ============

    async def cancel_collection(self, collection_id: str, user_id: str) -> dict:
        """
        Cancel an in-progress collection

        Args:
            collection_id: UUID of collection
            user_id: UUID of user (to verify ownership)

        Returns:
            Cancellation confirmation
        """
        try:
            col_response = (
                self.supabase.table("collections")
                .select("*")
                .eq("id", collection_id)
                .execute()
            )

            if not col_response.data:
                raise ValueError("Collection not found")

            collection = col_response.data[0]

            if collection["collected_by_user_id"] != user_id:
                raise ValueError("You can only cancel your own collections")

            if collection["status"] != "in_progress":
                raise ValueError("Only in-progress collections can be cancelled")

            self.supabase.table("collections").update(
                {"status": "cancelled", "cancelled_at": datetime.utcnow().isoformat()}
            ).eq("id", collection_id).execute()

            return {
                "collection_id": collection_id,
                "status": "cancelled",
                "message": "Collection cancelled successfully",
            }

        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to cancel collection: {str(e)}")

    async def delete_destination(self, destination_id: str) -> dict:
        """
        Delete a destination (only if no active collections)

        Args:
            destination_id: UUID of destination

        Returns:
            Deletion confirmation
        """
        try:
            # Check for active collections
            active_resp = (
                self.supabase.table("collections")
                .select("id")
                .eq("destination_id", destination_id)
                .in_("status", ["in_progress", "submitted"])
                .execute()
            )

            if active_resp.data:
                raise ValueError("Cannot delete destination with active collections")

            self.supabase.table("destinations").delete().eq(
                "id", destination_id
            ).execute()

            return {
                "destination_id": destination_id,
                "message": "Destination deleted successfully",
            }

        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise Exception(f"Failed to delete destination: {str(e)}")
