"""
reward_service.py — Reward catalogue and point redemption

The rewards and redemptions tables already existed in tankas_migration.sql but
had no endpoints. This wires them up, porting the catalogue/redeem flow from the
legacy tankas_app-api.

Note this is distinct from payments.redeem-points, which converts points to cash
via Paystack. This redeems points for a catalogue item (merch, airtime, vouchers).
"""

from app.database import get_connection


class RewardService:

    # ------------------------------------------------------------------
    # Catalogue
    # ------------------------------------------------------------------

    async def list_rewards(
        self, available_only: bool = True, limit: int = 100, offset: int = 0
    ) -> dict:
        """List the reward catalogue. Public — no auth required."""
        async with get_connection() as conn:
            if available_only:
                rows = await conn.fetch(
                    """
                    SELECT id, name, description, cost_in_points,
                           reward_type, is_available, created_at
                    FROM rewards
                    WHERE is_available = TRUE
                    ORDER BY cost_in_points ASC
                    LIMIT $1 OFFSET $2
                    """,
                    limit,
                    offset,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, name, description, cost_in_points,
                           reward_type, is_available, created_at
                    FROM rewards
                    ORDER BY cost_in_points ASC
                    LIMIT $1 OFFSET $2
                    """,
                    limit,
                    offset,
                )

        return {
            "count": len(rows),
            "rewards": [
                {
                    "reward_id": str(r["id"]),
                    "name": r["name"],
                    "description": r["description"],
                    "cost_in_points": r["cost_in_points"],
                    "reward_type": r["reward_type"],
                    "is_available": r["is_available"],
                }
                for r in rows
            ],
        }

    async def get_reward(self, reward_id: str) -> dict:
        """Get a single reward by id."""
        async with get_connection() as conn:
            r = await conn.fetchrow(
                """
                SELECT id, name, description, cost_in_points,
                       reward_type, is_available, created_at
                FROM rewards WHERE id=$1
                """,
                reward_id,
            )
        if not r:
            raise ValueError("Reward not found")

        return {
            "reward_id": str(r["id"]),
            "name": r["name"],
            "description": r["description"],
            "cost_in_points": r["cost_in_points"],
            "reward_type": r["reward_type"],
            "is_available": r["is_available"],
            "created_at": r["created_at"],
        }

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    async def create_reward(
        self,
        user_id: str,
        name: str,
        description: str,
        cost_in_points: int,
        reward_type: str = "merch",
    ) -> dict:
        """Create a reward. Admin only."""
        if cost_in_points <= 0:
            raise ValueError("cost_in_points must be greater than 0")

        async with get_connection() as conn:
            role = await conn.fetchval("SELECT role FROM users WHERE id=$1", user_id)
            if role != "admin":
                raise PermissionError("Admin access required")

            r = await conn.fetchrow(
                """
                INSERT INTO rewards (name, description, cost_in_points, reward_type)
                VALUES ($1, $2, $3, $4)
                RETURNING id, name, description, cost_in_points,
                          reward_type, is_available, created_at
                """,
                name,
                description,
                cost_in_points,
                reward_type,
            )

        return {
            "reward_id": str(r["id"]),
            "name": r["name"],
            "description": r["description"],
            "cost_in_points": r["cost_in_points"],
            "reward_type": r["reward_type"],
            "is_available": r["is_available"],
        }

    async def set_availability(
        self, user_id: str, reward_id: str, is_available: bool
    ) -> dict:
        """Enable or disable a reward. Admin only."""
        async with get_connection() as conn:
            role = await conn.fetchval("SELECT role FROM users WHERE id=$1", user_id)
            if role != "admin":
                raise PermissionError("Admin access required")

            r = await conn.fetchrow(
                """
                UPDATE rewards SET is_available=$1 WHERE id=$2
                RETURNING id, name, is_available
                """,
                is_available,
                reward_id,
            )
        if not r:
            raise ValueError("Reward not found")

        return {
            "reward_id": str(r["id"]),
            "name": r["name"],
            "is_available": r["is_available"],
        }

    # ------------------------------------------------------------------
    # Redemption
    # ------------------------------------------------------------------

    async def redeem_reward(
        self, user_id: str, reward_id: str, quantity: int = 1
    ) -> dict:
        """
        Redeem a catalogue reward with points.

        Runs in a transaction, and deducts points with a conditional UPDATE so
        two concurrent redemptions cannot drive a balance negative.
        """
        if quantity < 1:
            raise ValueError("Quantity must be at least 1")

        async with get_connection() as conn:
            async with conn.transaction():

                reward = await conn.fetchrow(
                    """
                    SELECT id, name, cost_in_points, is_available
                    FROM rewards WHERE id=$1
                    """,
                    reward_id,
                )
                if not reward:
                    raise ValueError("Reward not found")
                if not reward["is_available"]:
                    raise ValueError("This reward is no longer available")

                total_cost = reward["cost_in_points"] * quantity

                # Conditional deduction — returns no row if the balance is short,
                # which also closes the race against a concurrent redemption.
                updated = await conn.fetchrow(
                    """
                    UPDATE users
                    SET total_points = total_points - $1, updated_at = NOW()
                    WHERE id = $2 AND total_points >= $1
                    RETURNING total_points
                    """,
                    total_cost,
                    user_id,
                )
                if not updated:
                    balance = await conn.fetchval(
                        "SELECT total_points FROM users WHERE id=$1", user_id
                    )
                    if balance is None:
                        raise ValueError("User not found")
                    raise ValueError(
                        f"Not enough points. You have {balance} but need {total_cost}"
                    )

                redemption = await conn.fetchrow(
                    """
                    INSERT INTO redemptions
                        (user_id, reward_id, quantity, points_spent, status)
                    VALUES ($1, $2, $3, $4, 'pending')
                    RETURNING id, created_at
                    """,
                    user_id,
                    reward_id,
                    quantity,
                    total_cost,
                )

        return {
            "redemption_id": str(redemption["id"]),
            "reward_id": str(reward["id"]),
            "reward_name": reward["name"],
            "quantity": quantity,
            "points_spent": total_cost,
            "points_remaining": updated["total_points"],
            "status": "pending",
            "created_at": redemption["created_at"],
        }

    async def get_my_redemptions(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> dict:
        """List the caller's redemption history."""
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT rd.id, rd.quantity, rd.points_spent, rd.status,
                       rd.created_at, rd.completed_at,
                       r.name AS reward_name, r.reward_type
                FROM redemptions rd
                JOIN rewards r ON r.id = rd.reward_id
                WHERE rd.user_id = $1
                ORDER BY rd.created_at DESC
                LIMIT $2 OFFSET $3
                """,
                user_id,
                limit,
                offset,
            )

        return {
            "count": len(rows),
            "redemptions": [
                {
                    "redemption_id": str(r["id"]),
                    "reward_name": r["reward_name"],
                    "reward_type": r["reward_type"],
                    "quantity": r["quantity"],
                    "points_spent": r["points_spent"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "completed_at": r["completed_at"],
                }
                for r in rows
            ],
        }
