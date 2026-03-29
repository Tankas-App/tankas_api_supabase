"""
pledge_service.py — Pledging system
Allows users to pledge money or equipment toward issue resolution.
"""

from app.database import get_connection
from datetime import datetime
from typing import Optional, List


PLEDGE_TYPES = ["money", "equipment", "volunteer", "other"]


class PledgeService:

    # ------------------------------------------------------------------
    # Create pledge
    # ------------------------------------------------------------------

    async def create_pledge(
        self,
        user_id: str,
        issue_id: str,
        pledge_type: str,
        description: str,
        quantity: int = 1,
        amount: Optional[float] = None,
    ) -> dict:
        """
        Create a new pledge on an issue.

        pledge_type: 'money', 'equipment', 'volunteer', 'other'
        amount: only required for money pledges (GHS)
        description: what they're pledging (e.g. "GHS 20", "10 trash bags", "truck")
        quantity: number of items (for equipment)
        """
        if pledge_type not in PLEDGE_TYPES:
            raise ValueError(
                f"Invalid pledge type. Must be one of: {', '.join(PLEDGE_TYPES)}"
            )

        if pledge_type == "money" and (not amount or amount <= 0):
            raise ValueError(
                "Amount is required for money pledges and must be greater than 0"
            )

        async with get_connection() as conn:

            # Verify issue exists and is open
            issue = await conn.fetchrow(
                "SELECT id, status, title FROM issues WHERE id=$1",
                issue_id,
            )
            if not issue:
                raise ValueError("Issue not found")
            if issue["status"] not in ("open", "pending_review"):
                raise ValueError("Can only pledge on open issues")

            # Check if user already has an active pledge of this type on this issue
            existing = await conn.fetchrow(
                """
                SELECT id FROM pledges
                WHERE user_id=$1 AND issue_id=$2
                AND pledge_type=$3 AND status='pending'
                """,
                user_id,
                issue_id,
                pledge_type,
            )
            if existing:
                raise ValueError(
                    f"You already have an active {pledge_type} pledge on this issue"
                )

            # Create pledge
            pledge = await conn.fetchrow(
                """
                INSERT INTO pledges
                    (user_id, issue_id, pledge_type, description,
                     quantity, amount, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, 'pending', NOW())
                RETURNING *
                """,
                user_id,
                issue_id,
                pledge_type,
                description,
                quantity,
                amount,
            )

            # Get user info for response
            user = await conn.fetchrow(
                "SELECT username, display_name FROM users WHERE id=$1",
                user_id,
            )

        return self._serialize(pledge, user)

    # ------------------------------------------------------------------
    # Get pledges for an issue
    # ------------------------------------------------------------------

    async def get_issue_pledges(self, issue_id: str) -> dict:
        """
        Get all pledges for an issue with summary totals.
        """
        async with get_connection() as conn:

            issue = await conn.fetchrow("SELECT id FROM issues WHERE id=$1", issue_id)
            if not issue:
                raise ValueError("Issue not found")

            pledges = await conn.fetch(
                """
                SELECT p.*, u.username, u.display_name, u.avatar_url
                FROM pledges p
                JOIN users u ON u.id = p.user_id
                WHERE p.issue_id=$1
                ORDER BY p.created_at DESC
                """,
                issue_id,
            )

        # Build summary
        total_money = sum(
            float(p["amount"] or 0)
            for p in pledges
            if p["pledge_type"] == "money" and p["status"] == "pending"
        )
        total_pledges = len(pledges)
        money_pledges = [p for p in pledges if p["pledge_type"] == "money"]
        equipment_pledges = [p for p in pledges if p["pledge_type"] == "equipment"]
        volunteer_pledges = [p for p in pledges if p["pledge_type"] == "volunteer"]

        return {
            "issue_id": issue_id,
            "total_pledges": total_pledges,
            "total_money_ghs": round(total_money, 2),
            "summary": {
                "money": len(money_pledges),
                "equipment": len(equipment_pledges),
                "volunteer": len(volunteer_pledges),
            },
            "pledges": [
                {
                    **self._serialize(p),
                    "pledger_name": p["display_name"] or p["username"],
                    "pledger_avatar": p["avatar_url"],
                }
                for p in pledges
            ],
        }

    # ------------------------------------------------------------------
    # Get a single pledge
    # ------------------------------------------------------------------

    async def get_pledge(self, pledge_id: str) -> dict:
        async with get_connection() as conn:
            pledge = await conn.fetchrow(
                """
                SELECT p.*, u.username, u.display_name
                FROM pledges p
                JOIN users u ON u.id = p.user_id
                WHERE p.id=$1
                """,
                pledge_id,
            )
        if not pledge:
            raise ValueError("Pledge not found")
        return self._serialize(pledge)

    # ------------------------------------------------------------------
    # Fulfil a pledge (admin or issue resolver marks it done)
    # ------------------------------------------------------------------

    async def fulfil_pledge(self, pledge_id: str, user_id: str) -> dict:
        """Mark a pledge as fulfilled."""
        async with get_connection() as conn:

            pledge = await conn.fetchrow("SELECT * FROM pledges WHERE id=$1", pledge_id)
            if not pledge:
                raise ValueError("Pledge not found")
            if pledge["status"] != "pending":
                raise ValueError(f"Pledge is already {pledge['status']}")

            # Only the pledger or an admin can fulfil
            user = await conn.fetchrow("SELECT role FROM users WHERE id=$1", user_id)
            if str(pledge["user_id"]) != user_id and user["role"] != "admin":
                raise ValueError("Only the pledger or an admin can fulfil this pledge")

            await conn.execute(
                """
                UPDATE pledges
                SET status='fulfilled', fulfilled_at=NOW()
                WHERE id=$1
                """,
                pledge_id,
            )

            updated = await conn.fetchrow(
                "SELECT * FROM pledges WHERE id=$1", pledge_id
            )

        return self._serialize(updated)

    # ------------------------------------------------------------------
    # Cancel a pledge
    # ------------------------------------------------------------------

    async def cancel_pledge(self, pledge_id: str, user_id: str) -> dict:
        """Cancel a pending pledge. Only the pledger can cancel."""
        async with get_connection() as conn:

            pledge = await conn.fetchrow("SELECT * FROM pledges WHERE id=$1", pledge_id)
            if not pledge:
                raise ValueError("Pledge not found")
            if str(pledge["user_id"]) != user_id:
                raise ValueError("You can only cancel your own pledges")
            if pledge["status"] != "pending":
                raise ValueError(f"Cannot cancel a {pledge['status']} pledge")

            await conn.execute(
                "UPDATE pledges SET status='cancelled' WHERE id=$1",
                pledge_id,
            )

        return {
            "pledge_id": pledge_id,
            "status": "cancelled",
            "message": "Pledge cancelled successfully",
        }

    # ------------------------------------------------------------------
    # Get user's pledges
    # ------------------------------------------------------------------

    async def get_user_pledges(
        self,
        user_id: str,
        status: Optional[str] = None,
    ) -> List[dict]:
        """Get all pledges made by a user."""
        async with get_connection() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT p.*, i.title as issue_title
                    FROM pledges p
                    JOIN issues i ON i.id = p.issue_id
                    WHERE p.user_id=$1 AND p.status=$2
                    ORDER BY p.created_at DESC
                    """,
                    user_id,
                    status,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT p.*, i.title as issue_title
                    FROM pledges p
                    JOIN issues i ON i.id = p.issue_id
                    WHERE p.user_id=$1
                    ORDER BY p.created_at DESC
                    """,
                    user_id,
                )

        return [
            {
                **self._serialize(r),
                "issue_title": r["issue_title"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Serializer
    # ------------------------------------------------------------------

    def _serialize(self, row, user=None) -> dict:
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "issue_id": str(row["issue_id"]),
            "pledge_type": row["pledge_type"],
            "description": row["description"],
            "quantity": row["quantity"],
            "amount": float(row["amount"]) if row["amount"] else None,
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "fulfilled_at": (
                row["fulfilled_at"].isoformat() if row.get("fulfilled_at") else None
            ),
            **(
                {
                    "pledger_name": user["display_name"] or user["username"],
                }
                if user
                else {}
            ),
        }
