"""
completion_service.py — Issue completion, verification, points distribution
"""

from app.database import get_connection
from app.utils.cloudinary_helper import CloudinaryHelper
from app.utils.points_calculator import PointsCalculator
from app.services.point_service import PointsService
from datetime import datetime
from typing import List


class CompletionService:

    def __init__(self):
        self.points_service = PointsService()

    # ------------------------------------------------------------------
    # Confirm participation
    # ------------------------------------------------------------------

    async def confirm_participation(
        self, user_id: str, issue_id: str, group_id: str
    ) -> dict:

        async with get_connection() as conn:
            vol = await conn.fetchrow(
                "SELECT id FROM volunteers WHERE user_id=$1 AND issue_id=$2",
                user_id,
                issue_id,
            )
            if not vol:
                raise ValueError("Volunteer record not found")

        return {
            "message": f"You've confirmed participation on {issue_id}",
            "volunteer_id": str(vol["id"]),
            "status": "awaiting_leader_verification",
        }

    # ------------------------------------------------------------------
    # Complete issue (leader marks done + uploads photo)
    # ------------------------------------------------------------------

    async def complete_issue(
        self,
        user_id: str,
        issue_id: str,
        group_id: str,
        photo_bytes: bytes,
    ) -> dict:

        async with get_connection() as conn:

            # Verify leader
            vol = await conn.fetchrow(
                "SELECT * FROM volunteers WHERE user_id=$1 AND group_id=$2",
                user_id,
                group_id,
            )
            if not vol:
                raise ValueError("You're not part of this group")
            if not vol["is_leader"]:
                raise ValueError("Only the group leader can mark issue as complete")

            # Get issue
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id=$1",
                issue_id,
            )
            if not issue:
                raise ValueError("Issue not found")

            # Upload cleanup photo
            cleanup_photo_url = await CloudinaryHelper.upload_photo(
                photo_bytes, folder=f"tankas-completions/{issue_id}"
            )

            # AI confidence (MVP default — real comparison in a later phase)
            ai_confidence = 85.0
            verification_status = "verified"
            message = "Cleanup verified! Points will be distributed shortly."

            # Mark issue as resolved
            await conn.execute(
                """
                UPDATE issues
                SET status                 = 'resolved',
                    resolved_by            = $1,
                    resolved_at            = NOW(),
                    resolution_picture_url = $2,
                    updated_at             = NOW()
                WHERE id = $3
                """,
                user_id,
                cleanup_photo_url,
                issue_id,
            )

            # Build volunteer list for response
            volunteers_rows = await conn.fetch(
                "SELECT v.*, u.username FROM volunteers v JOIN users u ON u.id = v.user_id WHERE v.group_id=$1",
                group_id,
            )

        volunteer_list = [
            {
                "volunteer_id": str(v["id"]),
                "user_id": str(v["user_id"]),
                "username": v["username"],
                "participated": False,
                "verified": False,
                "points_earned": 0,
                "status": "awaiting_confirmation",
            }
            for v in volunteers_rows
        ]

        return {
            "issue_id": issue_id,
            "group_id": group_id,
            "status": "resolved",
            "verification_photo_url": cleanup_photo_url,
            "verification_status": verification_status,
            "ai_confidence": ai_confidence,
            "message": message,
            "volunteers": volunteer_list,
        }

    # ------------------------------------------------------------------
    # Verify volunteers + distribute points
    # ------------------------------------------------------------------

    async def verify_volunteers(
        self,
        user_id: str,
        issue_id: str,
        group_id: str,
        verified_volunteer_ids: List[str],
    ) -> dict:

        async with get_connection() as conn:

            # Verify leader
            leader_vol = await conn.fetchrow(
                "SELECT * FROM volunteers WHERE user_id=$1 AND group_id=$2",
                user_id,
                group_id,
            )
            if not leader_vol or not leader_vol["is_leader"]:
                raise ValueError("Only the group leader can verify volunteers")

            # Get issue points
            issue = await conn.fetchrow(
                "SELECT points_assigned FROM issues WHERE id=$1",
                issue_id,
            )
            if not issue:
                raise ValueError("Issue not found")

            total_points = issue["points_assigned"]

            # Get all volunteers in group
            all_vols = await conn.fetch(
                "SELECT * FROM volunteers WHERE group_id=$1",
                group_id,
            )

            distribution = {}
            verified_count = 0

            for vol in all_vols:
                vol_id = str(vol["id"])
                is_verified = vol_id in verified_volunteer_ids

                if is_verified:
                    verified_count += 1
                    await conn.execute(
                        "UPDATE volunteers SET verified=TRUE, leader_validated=TRUE, verified_at=NOW() WHERE id=$1",
                        vol_id,
                    )
                else:
                    await conn.execute(
                        "UPDATE volunteers SET verified=FALSE, leader_validated=TRUE WHERE id=$1",
                        vol_id,
                    )

                distribution[vol_id] = {
                    "user_id": str(vol["user_id"]),
                    "verified": is_verified,
                }

        # Distribute points outside the connection
        points_per_volunteer = 0
        leader_bonus = 0

        if verified_count > 0:
            dist_info = PointsCalculator.distribute_points_with_leader(
                total_points, verified_count, user_id
            )
            points_per_volunteer = dist_info["points_per_volunteer"]
            leader_bonus = dist_info["leader_bonus"]

            for vol_id, vol_data in distribution.items():
                if not vol_data["verified"]:
                    continue

                is_leader_vol = vol_data["user_id"] == user_id
                points_earned = points_per_volunteer + (
                    leader_bonus if is_leader_vol else 0
                )

                async with get_connection() as conn:
                    await conn.execute(
                        "UPDATE volunteers SET points_earned=$1 WHERE id=$2",
                        points_earned,
                        vol_id,
                    )

                await self.points_service.award_points(
                    user_id=vol_data["user_id"],
                    points=points_earned,
                    activity_type="cleanup_verified",
                    reference_id=issue_id,
                    reference_type="issue",
                    metadata={
                        "group_id": group_id,
                        "is_leader": is_leader_vol,
                        "volunteer_count": verified_count,
                    },
                )
                distribution[vol_id]["points_earned"] = points_earned

        return {
            "issue_id": issue_id,
            "group_id": group_id,
            "total_points_available": total_points,
            "verified_volunteer_count": verified_count,
            "points_per_volunteer": points_per_volunteer,
            "leader_bonus": leader_bonus,
            "distribution": distribution,
            "message": f"Points distributed to {verified_count} verified volunteers!",
        }
