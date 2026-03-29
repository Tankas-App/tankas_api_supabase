"""
issue_service.py — Environmental issue management
Handles AI fallback to admin review when confidence is low.
"""

from app.database import get_connection
from app.utils.exif_helper import ExifHelper
from app.utils.ai_service import AIService
from app.utils.points_calculator import PointsCalculator
from app.utils.cloudinary_helper import CloudinaryHelper
from app.services.point_service import PointsService
from datetime import datetime
from typing import Optional


class IssueService:

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

        # Hard rejection — selfies, animals only
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
        needs_review = ai_analysis.get("needs_review", False)
        review_reason = ai_analysis.get("review_reason", "")

        final_description = description or ai_description

        if priority.lower() not in ["low", "medium", "high"]:
            priority = "medium"

        # Step 4: Determine status
        # pending_review → admin must classify before issue goes live
        # open → auto-classified, immediately visible to volunteers
        issue_status = "pending_review" if needs_review else "open"

        # Step 5: Calculate points
        print("Step 4: Calculating points...")
        points_assigned = PointsCalculator.calculate_issue_points(
            ai_difficulty, priority.lower()
        )

        # Step 6: Insert into DB
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
                    $12, $13, NOW(), NOW()
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
                label_names,
                ai_confidence,
                points_assigned,
                issue_status,
                location_source,
            )

        # Step 7: Award reporter points (regardless of review status)
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
                "needs_review": needs_review,
            },
        )

        # Step 8: Send confirmation email
        await self._send_issue_confirmation(
            user_id=user_id,
            title=title or ai_description,
            points=self.ISSUE_REPORT_POINTS,
        )

        print(f"[SUCCESS] Issue created: {issue['id']} — status: {issue_status}")

        return {
            "issue": self._serialize(issue),
            "ai_analysis": {
                "difficulty": ai_difficulty,
                "description": ai_description,
                "confidence": ai_confidence,
                "labels": ai_labels,
                "needs_review": needs_review,
                "review_reason": review_reason,
            },
            # Tell the frontend what happened
            "status": issue_status,
            "message": (
                "Your issue has been submitted and is pending admin review. "
                "You'll be notified once it's approved and visible to volunteers."
                if needs_review
                else "Issue reported successfully! Volunteers in your area have been notified."
            ),
        }

    # ------------------------------------------------------------------
    # Get issue by ID
    # ------------------------------------------------------------------

    async def get_issue(self, issue_id: str) -> dict:
        async with get_connection() as conn:
            issue = await conn.fetchrow("SELECT * FROM issues WHERE id=$1", issue_id)
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
        from app.utils.distance_calculator import DistanceCalculator

        async with get_connection() as conn:
            # Only return open issues to volunteers — not pending_review
            rows = await conn.fetch("SELECT * FROM issues WHERE status='open'")

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
        resolution_photo_url = None
        if resolution_photo_bytes:
            resolution_photo_url = await self._upload_photo(
                resolution_photo_bytes, resolved_by_user_id
            )

        async with get_connection() as conn:
            issue = await conn.fetchrow(
                """
                UPDATE issues
                SET status='resolved', resolved_by=$1, resolved_at=NOW(),
                    resolution_picture_url=$2, updated_at=NOW()
                WHERE id=$3
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
    # Admin — classify a pending_review issue
    # ------------------------------------------------------------------

    async def admin_classify_issue(
        self,
        issue_id: str,
        admin_id: str,
        difficulty: str,
        priority: str,
        approved: bool,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Admin manually classifies a pending_review issue.
        If approved → status becomes 'open', points recalculated.
        If rejected → status becomes 'rejected'.
        """
        if difficulty not in ["easy", "medium", "hard"]:
            raise ValueError("Difficulty must be easy, medium, or hard")

        async with get_connection() as conn:
            issue = await conn.fetchrow("SELECT * FROM issues WHERE id=$1", issue_id)
            if not issue:
                raise ValueError("Issue not found")
            if issue["status"] != "pending_review":
                raise ValueError("Issue is not pending review")

            if approved:
                # Recalculate points with admin-set difficulty
                new_points = PointsCalculator.calculate_issue_points(
                    difficulty, priority
                )
                await conn.execute(
                    """
                    UPDATE issues
                    SET status='open', difficulty=$1, priority=$2,
                        points_assigned=$3, updated_at=NOW()
                    WHERE id=$4
                    """,
                    difficulty,
                    priority,
                    new_points,
                    issue_id,
                )
                status = "open"
            else:
                new_points = 0
                await conn.execute(
                    "UPDATE issues SET status='rejected', updated_at=NOW() WHERE id=$1",
                    issue_id,
                )
                status = "rejected"

        return {
            "issue_id": issue_id,
            "status": status,
            "difficulty": difficulty,
            "priority": priority,
            "points_assigned": new_points if approved else 0,
            "approved": approved,
            "notes": notes,
            "message": f"Issue {'approved and now live' if approved else 'rejected'}.",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _upload_photo(self, photo_bytes: bytes, user_id: str) -> str:
        try:
            return await CloudinaryHelper.upload_photo(
                photo_bytes, folder=f"tankas-issues/{user_id}"
            )
        except Exception as e:
            raise Exception(f"Photo upload failed: {str(e)}")

    async def _send_issue_confirmation(
        self, user_id: str, title: str, points: int
    ) -> None:
        try:
            from app.services.email_service import EmailService

            async with get_connection() as conn:
                user = await conn.fetchrow(
                    "SELECT email, username FROM users WHERE id=$1", user_id
                )
            if user:
                EmailService().send_issue_reported(
                    user["email"], user["username"], title, points
                )
        except Exception as e:
            print(f"[EMAIL] Issue confirmation failed: {e}")

    def _serialize(self, row) -> dict:
        result = {}
        for key, value in row.items():
            if hasattr(value, "hex"):
                result[key] = str(value)
            elif hasattr(value, "isoformat"):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result
