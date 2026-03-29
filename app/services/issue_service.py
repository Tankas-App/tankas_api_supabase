from app.database import get_connection
from app.utils.exif_helper import ExifHelper
from app.utils.ai_service import AIService
from app.utils.points_calculator import PointsCalculator
from app.utils.cloudinary_helper import CloudinaryHelper
from app.services.point_service import PointsService
from datetime import datetime
from typing import Optional
import json


class IssueService:
    """Handle environmental issue management"""

    def __init__(self):
        self.ai_service = AIService()
        self.points_service = PointsService()
        self.ISSUE_REPORT_POINTS = 15

    # ------------------------------------------------------------------
    # Create issue
    # ------------------------------------------------------------------

    async def create_issue(
        self,
        user_id: str,
        title: str,
        description: Optional[str],
        photo_bytes: bytes,
        latitude: float,
        longitude: float,
        priority: str = "medium",
    ) -> dict:
        """
        Create a new environmental issue.

        Flow:
        1. Upload photo to Cloudinary
        2. Extract EXIF location (if available)
        3. Analyse with Google Vision
        4. Calculate difficulty + points
        5. Insert into DB
        6. Award reporter points via PointsService
        """
        # Step 1: Upload photo
        print("Step 1: Uploading photo...")
        photo_url = await self._upload_photo(photo_bytes, user_id)

        # Step 2: EXIF location
        print("Step 2: Extracting EXIF...")
        exif_location = ExifHelper.extract_gps_coordinates(photo_bytes)
        if exif_location:
            latitude, longitude = exif_location
            location_source = "exif"
        else:
            location_source = "manual"

        # Step 3: AI analysis
        print("Step 3: Running AI analysis...")
        ai_analysis = await self.ai_service.analyze_issue_image(photo_bytes)
        if not ai_analysis.get("is_valid_issue"):
            raise ValueError(
                ai_analysis.get(
                    "error", "Image does not appear to be an environmental issue"
                )
            )

        ai_difficulty = ai_analysis.get("difficulty", "medium")
        ai_description = ai_analysis.get(
            "description", f"Environmental issue at {latitude}, {longitude}"
        )
        ai_confidence = ai_analysis.get("confidence", 0)
        ai_labels = ai_analysis.get("labels", [])

        final_description = description or ai_description

        if priority.lower() not in ["low", "medium", "high"]:
            priority = "medium"

        # Step 4: Calculate points
        print("Step 4: Calculating points...")
        points_assigned = PointsCalculator.calculate_issue_points(
            ai_difficulty, priority.lower()
        )

        # Step 5: Insert into DB
        print("Step 5: Inserting issue...")
        label_names = [label["name"] for label in ai_labels]

        async with get_connection() as conn:
            issue = await conn.fetchrow(
                """
                INSERT INTO issues (
                    user_id, title, description, picture_url,
                    latitude, longitude, priority, difficulty,
                    ai_labels, ai_confidence_score, points_assigned,
                    status, location_source, created_at, updated_at
                )
                VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7, $8,
                    $9, $10, $11,
                    'open', $12, NOW(), NOW()
                )
                RETURNING *
                """,
                user_id,
                title or ai_description,
                final_description,
                photo_url,
                latitude,
                longitude,
                priority.lower(),
                ai_difficulty,
                label_names,  # asyncpg handles TEXT[] natively
                ai_confidence,
                points_assigned,
                location_source,
            )

        # Step 6: Award points
        print("Step 6: Awarding points...")
        await self.points_service.award_points(
            user_id=user_id,
            points=self.ISSUE_REPORT_POINTS,
            activity_type="issue_reported",
            reference_id=str(issue["id"]),
            reference_type="issue",
            metadata={
                "ai_difficulty": ai_difficulty,
                "ai_confidence": ai_confidence,
                "priority": priority,
            },
        )

        print(f"[SUCCESS] Issue created: {issue['id']}")
        return {
            "issue": self._serialize(issue),
            "ai_analysis": {
                "difficulty": ai_difficulty,
                "description": ai_description,
                "confidence": ai_confidence,
                "labels": ai_labels,
            },
        }

    # ------------------------------------------------------------------
    # Get issue by ID
    # ------------------------------------------------------------------

    async def get_issue(self, issue_id: str) -> dict:
        """Fetch a single issue by UUID."""
        async with get_connection() as conn:
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id = $1",
                issue_id,
            )

        if not issue:
            raise ValueError("Issue not found")

        return self._serialize(issue)

    # ------------------------------------------------------------------
    # Get nearby issues
    # ------------------------------------------------------------------

    async def get_nearby_issues(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
    ) -> list:
        """Return open issues within radius_km of the given coordinates."""
        from app.utils.distance_calculator import DistanceCalculator

        async with get_connection() as conn:
            rows = await conn.fetch("SELECT * FROM issues WHERE status = 'open'")

        nearby = []
        for row in rows:
            distance = DistanceCalculator.haversine(
                latitude,
                longitude,
                row["latitude"],
                row["longitude"],
            )
            if distance <= radius_km:
                issue = self._serialize(row)
                issue["distance_km"] = round(distance, 2)
                nearby.append(issue)

        nearby.sort(key=lambda x: x["distance_km"])
        return nearby

    # ------------------------------------------------------------------
    # Resolve issue
    # ------------------------------------------------------------------

    async def resolve_issue(
        self,
        issue_id: str,
        resolved_by_user_id: str,
        resolution_photo_bytes: Optional[bytes] = None,
        resolution_latitude: Optional[float] = None,
        resolution_longitude: Optional[float] = None,
    ) -> dict:
        """Mark an issue as resolved."""
        resolution_photo_url = None
        if resolution_photo_bytes:
            resolution_photo_url = await self._upload_photo(
                resolution_photo_bytes, resolved_by_user_id
            )

        async with get_connection() as conn:
            issue = await conn.fetchrow(
                """
                UPDATE issues
                SET
                    status                 = 'resolved',
                    resolved_by            = $1,
                    resolved_at            = NOW(),
                    resolution_picture_url = $2,
                    updated_at             = NOW()
                WHERE id = $3
                RETURNING *
                """,
                resolved_by_user_id,
                resolution_photo_url,
                issue_id,
            )

        if not issue:
            raise ValueError("Issue not found")

        return self._serialize(issue)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _upload_photo(self, photo_bytes: bytes, user_id: str) -> str:
        """Upload photo to Cloudinary and return the URL."""
        try:
            return await CloudinaryHelper.upload_photo(
                photo_bytes, folder=f"tankas-issues/{user_id}"
            )
        except Exception as e:
            raise Exception(f"Photo upload failed: {str(e)}")

    def _serialize(self, row) -> dict:
        """
        Convert an asyncpg Record to a plain dict.
        Handles UUID → str and datetime → str conversions.
        """
        result = {}
        for key, value in row.items():
            if hasattr(value, "hex"):  # UUID
                result[key] = str(value)
            elif hasattr(value, "isoformat"):  # datetime / date
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result
