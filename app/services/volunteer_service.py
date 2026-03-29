"""
volunteer_service.py — Volunteer group management
"""

from app.database import get_connection
from datetime import datetime
from typing import Optional, List


class VolunteerService:

    # ------------------------------------------------------------------
    # Join issue
    # ------------------------------------------------------------------

    async def join_issue(
        self,
        user_id: str,
        issue_id: str,
        solo_work: bool = False,
        equipment_needed: Optional[List[str]] = None,
    ) -> dict:

        async with get_connection() as conn:

            # Verify issue exists
            issue = await conn.fetchrow(
                "SELECT id, title FROM issues WHERE id = $1",
                issue_id,
            )
            if not issue:
                raise ValueError("Issue not found")

            # Check not already volunteering
            existing = await conn.fetchrow(
                "SELECT id FROM volunteers WHERE user_id=$1 AND issue_id=$2",
                user_id,
                issue_id,
            )
            if existing:
                raise ValueError("You're already volunteering for this issue")

            # Check if group exists
            group = await conn.fetchrow(
                "SELECT id FROM groups WHERE issue_id = $1",
                issue_id,
            )

            if not group:
                # Create group — user becomes leader
                group = await conn.fetchrow(
                    """
                    INSERT INTO groups (issue_id, leader_id, name, status, created_at, updated_at)
                    VALUES ($1, $2, $3, 'active', NOW(), NOW())
                    RETURNING id
                    """,
                    issue_id,
                    user_id,
                    f"Cleanup Group - {issue['title'][:30]}",
                )
                is_leader = True
            else:
                is_leader = False

            group_id = str(group["id"])

            # Create volunteer record
            volunteer = await conn.fetchrow(
                """
                INSERT INTO volunteers
                    (user_id, issue_id, group_id, is_leader, solo_work,
                     equipment_needed, verified, leader_validated, points_earned, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, FALSE, FALSE, 0, NOW())
                RETURNING id
                """,
                user_id,
                issue_id,
                group_id,
                is_leader,
                solo_work,
                equipment_needed or [],
            )

        return {
            "volunteer_id": str(volunteer["id"]),
            "issue_id": issue_id,
            "group_id": group_id,
            "is_leader": is_leader,
            "message": "You've joined the issue!"
            + (" as leader!" if is_leader else ""),
        }

    # ------------------------------------------------------------------
    # Transfer leadership
    # ------------------------------------------------------------------

    async def transfer_leadership(
        self,
        current_leader_volunteer_id: str,
        new_leader_volunteer_id: str,
    ) -> dict:

        async with get_connection() as conn:

            current = await conn.fetchrow(
                "SELECT * FROM volunteers WHERE id = $1",
                current_leader_volunteer_id,
            )
            if not current:
                raise ValueError("Current leader not found")
            if not current["is_leader"]:
                raise ValueError("You are not a leader")

            new = await conn.fetchrow(
                "SELECT * FROM volunteers WHERE id = $1",
                new_leader_volunteer_id,
            )
            if not new:
                raise ValueError("New leader not found")

            if str(current["group_id"]) != str(new["group_id"]):
                raise ValueError("Both volunteers must be in the same group")

            # Swap leadership
            await conn.execute(
                "UPDATE volunteers SET is_leader=FALSE WHERE id=$1",
                current_leader_volunteer_id,
            )
            await conn.execute(
                "UPDATE volunteers SET is_leader=TRUE WHERE id=$1",
                new_leader_volunteer_id,
            )
            await conn.execute(
                "UPDATE groups SET leader_id=$1, updated_at=NOW() WHERE id=$2",
                new["user_id"],
                current["group_id"],
            )

            # Get new leader's username for response
            user = await conn.fetchrow(
                "SELECT username FROM users WHERE id=$1",
                new["user_id"],
            )

        return {
            "message": "Leadership transferred successfully",
            "new_leader_id": str(new["user_id"]),
            "new_leader_name": user["username"] if user else "Unknown",
        }

    # ------------------------------------------------------------------
    # Get group members
    # ------------------------------------------------------------------

    async def get_group_members(self, group_id: str) -> dict:

        async with get_connection() as conn:

            group = await conn.fetchrow(
                "SELECT * FROM groups WHERE id = $1",
                group_id,
            )
            if not group:
                raise ValueError("Group not found")

            volunteers = await conn.fetch(
                "SELECT * FROM volunteers WHERE group_id = $1",
                group_id,
            )

            members = []
            for vol in volunteers:
                user = await conn.fetchrow(
                    "SELECT username, display_name, avatar_url FROM users WHERE id=$1",
                    vol["user_id"],
                )
                if user:
                    members.append(
                        {
                            "volunteer_id": str(vol["id"]),
                            "user_id": str(vol["user_id"]),
                            "username": user["username"],
                            "display_name": user["display_name"],
                            "avatar_url": user["avatar_url"],
                            "is_leader": vol["is_leader"],
                            "solo_work": vol["solo_work"],
                        }
                    )

        return {
            "group_id": group_id,
            "issue_id": str(group["issue_id"]),
            "leader_id": str(group["leader_id"]),
            "members": members,
            "member_count": len(members),
            "created_at": group["created_at"].isoformat(),
        }

    # ------------------------------------------------------------------
    # Get volunteer profile
    # ------------------------------------------------------------------

    async def get_volunteer_profile(self, user_id: str) -> dict:

        async with get_connection() as conn:

            user = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1",
                user_id,
            )
            if not user:
                raise ValueError("User not found")

            volunteers = await conn.fetch(
                "SELECT * FROM volunteers WHERE user_id = $1",
                user_id,
            )

            history = []
            active_issues = []

            for vol in volunteers:
                issue = await conn.fetchrow(
                    "SELECT * FROM issues WHERE id = $1",
                    vol["issue_id"],
                )
                if not issue:
                    continue

                group_size = 1
                if vol["group_id"]:
                    group_size = await conn.fetchval(
                        "SELECT COUNT(*) FROM volunteers WHERE group_id=$1",
                        vol["group_id"],
                    )

                history.append(
                    {
                        "issue_id": str(issue["id"]),
                        "title": issue["title"],
                        "description": issue["description"],
                        "location": f"{issue['latitude']}, {issue['longitude']}",
                        "difficulty": issue["difficulty"],
                        "priority": issue["priority"],
                        "points_earned": vol["points_earned"],
                        "volunteered_at": (
                            vol["created_at"].isoformat() if vol["created_at"] else None
                        ),
                        "completed_at": (
                            vol["completed_at"].isoformat()
                            if vol["completed_at"]
                            else None
                        ),
                        "was_verified": vol["verified"],
                        "group_size": group_size,
                    }
                )

                if issue["status"] == "open":
                    active_issues.append(str(issue["id"]))

        return {
            "user_id": str(user["id"]),
            "username": user["username"],
            "display_name": user["display_name"],
            "avatar_url": user["avatar_url"],
            "total_points": user["total_points"] or 0,
            "tasks_completed": user["tasks_completed"] or 0,
            "volunteer_hours": user["volunteer_hours"] or 0,
            "badge_tier": user["badge_tier"] or "bronze",
            "volunteering_history": history,
            "active_issues": active_issues,
        }
