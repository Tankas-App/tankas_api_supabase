"""
collection_service.py — Garbage collection, destinations, delivery verification
"""

from app.database import get_connection
from app.utils.cloudinary_helper import CloudinaryHelper
from app.utils.distance_calculator import DistanceCalculator
from app.services.point_service import PointsService
from datetime import datetime
from typing import Optional, List


class CollectionsService:

    def __init__(self):
        self.points_service = PointsService()
        self.PAYMENT_PER_KG = 2.0  # GHS per kg
        self.POINTS_PER_KG = 5  # points per kg

    # ------------------------------------------------------------------
    # Destinations
    # ------------------------------------------------------------------

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

        async with get_connection() as conn:
            dest = await conn.fetchrow(
                """
                INSERT INTO destinations
                    (name, description, latitude, longitude, address,
                     contact_person, contact_phone, operating_hours, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW())
                RETURNING *
                """,
                name,
                description,
                latitude,
                longitude,
                address,
                contact_person,
                contact_phone,
                operating_hours,
            )

        return {
            "destination_id": str(dest["id"]),
            "name": dest["name"],
            "description": dest["description"],
            "latitude": dest["latitude"],
            "longitude": dest["longitude"],
            "address": dest["address"],
            "contact_person": dest["contact_person"],
            "contact_phone": dest["contact_phone"],
            "operating_hours": dest["operating_hours"],
            "created_at": dest["created_at"].isoformat(),
        }

    async def get_nearby_destinations(
        self, latitude: float, longitude: float, radius_km: float = 5.0
    ) -> List[dict]:

        async with get_connection() as conn:
            rows = await conn.fetch("SELECT * FROM destinations")

        nearby = []
        for dest in rows:
            distance = DistanceCalculator.haversine(
                latitude, longitude, dest["latitude"], dest["longitude"]
            )
            if distance <= radius_km:
                d = dict(dest)
                d["id"] = str(d["id"])
                d["distance_km"] = round(distance, 2)
                nearby.append(d)

        nearby.sort(key=lambda x: x["distance_km"])
        return nearby

    async def assign_destination_to_issue(
        self, issue_id: str, destination_id: str
    ) -> dict:

        async with get_connection() as conn:
            issue = await conn.fetchrow(
                "SELECT id, status FROM issues WHERE id=$1",
                issue_id,
            )
            if not issue:
                raise ValueError("Issue not found")
            if issue["status"] != "resolved":
                raise ValueError(
                    "Issue must be resolved before assigning a destination"
                )

            dest = await conn.fetchrow(
                "SELECT id, name, address FROM destinations WHERE id=$1",
                destination_id,
            )
            if not dest:
                raise ValueError("Destination not found")

            await conn.execute(
                "UPDATE issues SET destination_id=$1, updated_at=NOW() WHERE id=$2",
                destination_id,
                issue_id,
            )

        return {
            "message": "Destination assigned successfully",
            "issue_id": issue_id,
            "destination_id": destination_id,
            "destination_name": dest["name"],
            "destination_address": dest["address"],
        }

    # ------------------------------------------------------------------
    # Collection workflow
    # ------------------------------------------------------------------

    async def start_collection(self, user_id: str, issue_id: str) -> dict:

        async with get_connection() as conn:
            issue = await conn.fetchrow(
                "SELECT id, status, destination_id FROM issues WHERE id=$1",
                issue_id,
            )
            if not issue:
                raise ValueError("Issue not found")
            if issue["status"] != "resolved":
                raise ValueError("Issue must be resolved before collection")
            if not issue["destination_id"]:
                raise ValueError(
                    "Issue must have a destination assigned before collection"
                )

            existing = await conn.fetchrow(
                "SELECT id FROM collections WHERE collected_by_user_id=$1 AND issue_id=$2 AND status='in_progress'",
                user_id,
                issue_id,
            )
            if existing:
                raise ValueError("You already have an active collection for this issue")

            collection = await conn.fetchrow(
                """
                INSERT INTO collections
                    (issue_id, collected_by_user_id, destination_id, status, created_at)
                VALUES ($1,$2,$3,'in_progress',NOW())
                RETURNING id
                """,
                issue_id,
                user_id,
                str(issue["destination_id"]),
            )

        return {
            "collection_id": str(collection["id"]),
            "issue_id": issue_id,
            "status": "in_progress",
            "message": "Collection started. Please submit when complete.",
        }

    async def submit_collection(
        self,
        user_id: str,
        issue_id: str,
        destination_id: str,
        photo_bytes: bytes,
        notes: Optional[str] = None,
        quantity_kg: Optional[float] = None,
    ) -> dict:

        async with get_connection() as conn:
            col = await conn.fetchrow(
                "SELECT * FROM collections WHERE collected_by_user_id=$1 AND issue_id=$2 AND status='in_progress'",
                user_id,
                issue_id,
            )
            if not col:
                raise ValueError("Active collection record not found")

            photo_url = await CloudinaryHelper.upload_photo(
                photo_bytes, folder=f"tankas-collections/{issue_id}"
            )

            await conn.execute(
                """
                UPDATE collections
                SET photo_url=$1, notes=$2, quantity=$3, status='submitted', submitted_at=NOW()
                WHERE id=$4
                """,
                photo_url,
                notes,
                quantity_kg,
                str(col["id"]),
            )

            dest = await conn.fetchrow(
                "SELECT name FROM destinations WHERE id=$1",
                destination_id,
            )

        return {
            "collection_id": str(col["id"]),
            "issue_id": issue_id,
            "status": "submitted",
            "message": "Collection submitted! Awaiting verification at destination.",
            "destination_name": dest["name"] if dest else "Unknown",
            "photo_url": photo_url,
        }

    async def verify_delivery(
        self,
        collection_id: str,
        destination_id: str,
        photo_bytes: bytes,
        verified: bool = True,
        notes: Optional[str] = None,
        quantity_kg: Optional[float] = None,
    ) -> dict:

        async with get_connection() as conn:
            col = await conn.fetchrow(
                "SELECT * FROM collections WHERE id=$1",
                collection_id,
            )
            if not col:
                raise ValueError("Collection not found")

            proof_url = await CloudinaryHelper.upload_photo(
                photo_bytes, folder=f"tankas-deliveries/{collection_id}"
            )

            if verified:
                final_qty = quantity_kg or col["quantity"] or 0
                payment_amount = final_qty * self.PAYMENT_PER_KG
                points_earned = int(final_qty * self.POINTS_PER_KG)

                await conn.execute(
                    """
                    UPDATE collections
                    SET status='verified', verified=TRUE, verified_at=NOW(),
                        delivery_proof_url=$1, quantity=$2, notes=$3
                    WHERE id=$4
                    """,
                    proof_url,
                    final_qty,
                    notes,
                    collection_id,
                )

                collector_id = str(col["collected_by_user_id"])

                # Update kg collected stat
                await conn.execute(
                    "UPDATE users SET total_kg_collected = total_kg_collected + $1 WHERE id=$2",
                    final_qty,
                    collector_id,
                )

                dest = await conn.fetchrow(
                    "SELECT name FROM destinations WHERE id=$1",
                    destination_id,
                )
                collector = await conn.fetchrow(
                    "SELECT username, display_name FROM users WHERE id=$1",
                    collector_id,
                )

            else:
                payment_amount = 0
                points_earned = 0
                final_qty = 0

                await conn.execute(
                    "UPDATE collections SET status='rejected', verified=FALSE, delivery_proof_url=$1, notes=$2 WHERE id=$3",
                    proof_url,
                    notes,
                    collection_id,
                )

                dest = await conn.fetchrow(
                    "SELECT name FROM destinations WHERE id=$1", destination_id
                )
                collector = await conn.fetchrow(
                    "SELECT username, display_name FROM users WHERE id=$1",
                    str(col["collected_by_user_id"]),
                )

        if verified:
            await self.points_service.award_points(
                user_id=collector_id,
                points=points_earned,
                activity_type="collection_verified",
                reference_id=collection_id,
                reference_type="collection",
                metadata={
                    "quantity_kg": final_qty,
                    "destination_id": destination_id,
                    "payment_amount": payment_amount,
                },
            )

        collector_name = (
            collector["display_name"] or collector["username"]
            if collector
            else "Unknown"
        )

        return {
            "collection_id": collection_id,
            "collector_id": str(col["collected_by_user_id"]),
            "collector_name": collector_name,
            "destination_name": dest["name"] if dest else "Unknown",
            "quantity_kg": final_qty,
            "points_earned": points_earned,
            "payment_amount": payment_amount,
            "status": "verified" if verified else "rejected",
            "message": (
                f"Delivery verified! Earned {points_earned} points and GHS {payment_amount}"
                if verified
                else "Delivery rejected"
            ),
            "delivery_proof_url": proof_url,
        }

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def get_collection_by_id(self, collection_id: str) -> dict:

        async with get_connection() as conn:
            col = await conn.fetchrow(
                "SELECT * FROM collections WHERE id=$1",
                collection_id,
            )
            if not col:
                raise ValueError("Collection not found")

            issue = await conn.fetchrow(
                "SELECT title FROM issues WHERE id=$1", col["issue_id"]
            )
            dest = await conn.fetchrow(
                "SELECT name, address FROM destinations WHERE id=$1",
                col["destination_id"],
            )
            collector = await conn.fetchrow(
                "SELECT username, display_name, avatar_url FROM users WHERE id=$1",
                col["collected_by_user_id"],
            )

        return {
            "collection_id": str(col["id"]),
            "issue_id": str(col["issue_id"]),
            "issue_title": issue["title"] if issue else None,
            "collector_id": str(col["collected_by_user_id"]),
            "collector_name": (
                collector["display_name"] or collector["username"]
                if collector
                else None
            ),
            "collector_avatar": collector["avatar_url"] if collector else None,
            "destination_name": dest["name"] if dest else None,
            "destination_address": dest["address"] if dest else None,
            "status": col["status"],
            "quantity_kg": col["quantity"],
            "photo_url": col["photo_url"],
            "delivery_proof_url": col["delivery_proof_url"],
            "notes": col["notes"],
            "created_at": col["created_at"].isoformat() if col["created_at"] else None,
            "submitted_at": (
                col["submitted_at"].isoformat() if col["submitted_at"] else None
            ),
            "verified_at": (
                col["verified_at"].isoformat() if col["verified_at"] else None
            ),
        }

    async def get_collector_statistics(self, user_id: str) -> dict:

        async with get_connection() as conn:
            cols = await conn.fetch(
                "SELECT * FROM collections WHERE collected_by_user_id=$1",
                user_id,
            )

        verified = [c for c in cols if c["status"] == "verified"]
        total_kg = sum(c["quantity"] or 0 for c in verified)
        earnings = total_kg * self.PAYMENT_PER_KG
        pts = int(total_kg * self.POINTS_PER_KG)

        return {
            "user_id": user_id,
            "total_collections": len(cols),
            "verified_collections": len(verified),
            "pending_collections": len(
                [c for c in cols if c["status"] in ("in_progress", "submitted")]
            ),
            "rejected_collections": len([c for c in cols if c["status"] == "rejected"]),
            "total_kg_collected": round(total_kg, 2),
            "total_earnings_ghs": round(earnings, 2),
            "total_points_earned": pts,
        }

    async def get_destination_collections(
        self, destination_id: str, status_filter: Optional[str] = None
    ) -> List[dict]:

        async with get_connection() as conn:
            if status_filter:
                rows = await conn.fetch(
                    "SELECT * FROM collections WHERE destination_id=$1 AND status=$2",
                    destination_id,
                    status_filter,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM collections WHERE destination_id=$1",
                    destination_id,
                )

            result = []
            for col in rows:
                user = await conn.fetchrow(
                    "SELECT display_name, username FROM users WHERE id=$1",
                    col["collected_by_user_id"],
                )
                d = dict(col)
                d["id"] = str(d["id"])
                d["collector_name"] = (
                    user["display_name"] or user["username"] if user else "Unknown"
                )
                result.append(d)

        return result

    async def get_pending_verifications(self, destination_id: str) -> List[dict]:

        async with get_connection() as conn:
            rows = await conn.fetch(
                "SELECT * FROM collections WHERE destination_id=$1 AND status='submitted' ORDER BY submitted_at ASC",
                destination_id,
            )

            result = []
            for col in rows:
                user = await conn.fetchrow(
                    "SELECT display_name, username FROM users WHERE id=$1",
                    col["collected_by_user_id"],
                )
                issue = await conn.fetchrow(
                    "SELECT title FROM issues WHERE id=$1", col["issue_id"]
                )
                d = dict(col)
                d["id"] = str(d["id"])
                d["collector_name"] = (
                    user["display_name"] or user["username"] if user else "Unknown"
                )
                d["issue_title"] = issue["title"] if issue else "Unknown"
                result.append(d)

        return result

    async def cancel_collection(self, collection_id: str, user_id: str) -> dict:

        async with get_connection() as conn:
            col = await conn.fetchrow(
                "SELECT * FROM collections WHERE id=$1", collection_id
            )
            if not col:
                raise ValueError("Collection not found")
            if str(col["collected_by_user_id"]) != user_id:
                raise ValueError("You can only cancel your own collections")
            if col["status"] != "in_progress":
                raise ValueError("Only in-progress collections can be cancelled")

            await conn.execute(
                "UPDATE collections SET status='cancelled' WHERE id=$1",
                collection_id,
            )

        return {
            "collection_id": collection_id,
            "status": "cancelled",
            "message": "Collection cancelled successfully",
        }

    async def delete_destination(self, destination_id: str) -> dict:

        async with get_connection() as conn:
            active = await conn.fetchval(
                "SELECT COUNT(*) FROM collections WHERE destination_id=$1 AND status IN ('in_progress','submitted')",
                destination_id,
            )
            if active:
                raise ValueError("Cannot delete destination with active collections")

            await conn.execute("DELETE FROM destinations WHERE id=$1", destination_id)

        return {
            "destination_id": destination_id,
            "message": "Destination deleted successfully",
        }
