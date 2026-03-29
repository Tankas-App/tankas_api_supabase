"""
payment_service.py — Paystack integration
Features:
- Point redemption (points → GHS via Paystack)
- Mobile Money withdrawals (MTN/Vodafone/AirtelTigo)
- Webhook handling
- Payment history
"""

from app.database import get_connection
from app.config import config
from datetime import datetime
from typing import Optional, Dict, Any
import httpx
import hashlib
import hmac
import json
import uuid


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POINTS_TO_GHS_RATE = 0.01  # 100 points = 1 GHS
MIN_REDEMPTION_POINTS = 500  # minimum points to redeem
MIN_REDEMPTION_GHS = 5.00  # minimum GHS value

MOMO_PROVIDERS = {
    "mtn": "MTN Mobile Money",
    "vodafone": "Vodafone Cash",
    "airteltigo": "AirtelTigo Money",
}

# Ghana phone prefixes per network
MTN_PREFIXES = ["024", "054", "055", "059", "025", "053"]
VODAFONE_PREFIXES = ["020", "050"]
AIRTELTIGO_PREFIXES = ["027", "057", "026", "056"]


class PaymentService:

    def __init__(self):
        self.secret_key = config.PAYSTACK_SECRET_KEY
        self.base_url = config.PAYSTACK_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # 1. Redeem points → GHS (initialise Paystack transaction)
    # ------------------------------------------------------------------

    async def redeem_points(
        self,
        user_id: str,
        points_to_redeem: int,
        email: str,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convert points to GHS and initialise a Paystack payment.

        Flow:
        1. Validate user has enough points
        2. Calculate GHS amount
        3. Deduct points from user (hold)
        4. Initialise Paystack transaction
        5. Return authorization_url for user to complete payment
        """

        # Validate minimum
        if points_to_redeem < MIN_REDEMPTION_POINTS:
            raise ValueError(f"Minimum redemption is {MIN_REDEMPTION_POINTS} points")

        amount_ghs = round(points_to_redeem * POINTS_TO_GHS_RATE, 2)

        if amount_ghs < MIN_REDEMPTION_GHS:
            raise ValueError(f"Minimum redemption amount is GHS {MIN_REDEMPTION_GHS}")

        async with get_connection() as conn:

            # Check user has enough points
            user = await conn.fetchrow(
                "SELECT id, email, total_points FROM users WHERE id=$1",
                user_id,
            )
            if not user:
                raise ValueError("User not found")

            if (user["total_points"] or 0) < points_to_redeem:
                raise ValueError(
                    f"Not enough points. You have {user['total_points']} but need {points_to_redeem}"
                )

            # Generate unique reference
            ref = f"TANKAS-REDEEM-{uuid.uuid4().hex[:12].upper()}"

            # Deduct points immediately (hold)
            await conn.execute(
                "UPDATE users SET total_points = total_points - $1, updated_at=NOW() WHERE id=$2",
                points_to_redeem,
                user_id,
            )

            # Create pending payment record
            payment = await conn.fetchrow(
                """
                INSERT INTO payments
                    (user_id, payment_type, amount_ghs, points_spent,
                     status, paystack_ref, metadata, created_at, updated_at)
                VALUES ($1, 'redemption', $2, $3, 'pending', $4, $5, NOW(), NOW())
                RETURNING id
                """,
                user_id,
                amount_ghs,
                points_to_redeem,
                ref,
                json.dumps({"email": email}),
            )

        # Initialise Paystack transaction
        # Amount is in pesewas (GHS × 100)
        payload = {
            "email": email,
            "amount": int(amount_ghs * 100),
            "reference": ref,
            "currency": "GHS",
            "metadata": {
                "user_id": user_id,
                "points_redeemed": points_to_redeem,
                "payment_id": str(payment["id"]),
                "custom_fields": [
                    {
                        "display_name": "Points Redeemed",
                        "variable_name": "points_redeemed",
                        "value": points_to_redeem,
                    }
                ],
            },
        }

        if callback_url:
            payload["callback_url"] = callback_url

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/transaction/initialize",
                    headers=self.headers,
                    json=payload,
                    timeout=30,
                )
                data = response.json()
        except Exception as e:
            # Rollback points deduction if Paystack call fails
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE users SET total_points = total_points + $1 WHERE id=$2",
                    points_to_redeem,
                    user_id,
                )
                await conn.execute(
                    "UPDATE payments SET status='failed', updated_at=NOW() WHERE paystack_ref=$1",
                    ref,
                )
            raise Exception(f"Paystack connection failed: {str(e)}")

        if not data.get("status"):
            # Rollback
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE users SET total_points = total_points + $1 WHERE id=$2",
                    points_to_redeem,
                    user_id,
                )
                await conn.execute(
                    "UPDATE payments SET status='failed', updated_at=NOW() WHERE paystack_ref=$1",
                    ref,
                )
            raise Exception(f"Paystack error: {data.get('message', 'Unknown error')}")

        # Store access code
        access_code = data["data"]["access_code"]
        authorization_url = data["data"]["authorization_url"]

        async with get_connection() as conn:
            await conn.execute(
                "UPDATE payments SET paystack_access_code=$1, authorization_url=$2, updated_at=NOW() WHERE paystack_ref=$3",
                access_code,
                authorization_url,
                ref,
            )

        return {
            "payment_id": str(payment["id"]),
            "reference": ref,
            "amount_ghs": amount_ghs,
            "points_redeemed": points_to_redeem,
            "authorization_url": authorization_url,
            "access_code": access_code,
            "message": f"Redirecting to payment. GHS {amount_ghs} for {points_to_redeem} points.",
        }

    # ------------------------------------------------------------------
    # 2. Verify payment (called after Paystack redirects back)
    # ------------------------------------------------------------------

    async def verify_payment(self, reference: str) -> Dict[str, Any]:
        """
        Verify a Paystack transaction by reference.
        Called after user completes payment on Paystack's page.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/transaction/verify/{reference}",
                    headers=self.headers,
                    timeout=30,
                )
                data = response.json()
        except Exception as e:
            raise Exception(f"Paystack verification failed: {str(e)}")

        if not data.get("status"):
            raise Exception(f"Paystack error: {data.get('message')}")

        tx = data["data"]
        status = tx["status"]  # 'success', 'failed', 'abandoned'

        async with get_connection() as conn:
            payment = await conn.fetchrow(
                "SELECT * FROM payments WHERE paystack_ref=$1",
                reference,
            )
            if not payment:
                raise ValueError("Payment record not found")

            if status == "success":
                await conn.execute(
                    "UPDATE payments SET status='completed', updated_at=NOW() WHERE paystack_ref=$1",
                    reference,
                )
                # Log activity
                await conn.execute(
                    """
                    INSERT INTO user_activity_log
                        (user_id, activity_type, activity_date, points_earned,
                         reference_id, reference_type, metadata, created_at)
                    VALUES ($1, 'points_redeemed', $2, $3, $4, 'payment', $5, NOW())
                    """,
                    str(payment["user_id"]),
                    datetime.utcnow().date(),
                    -payment["points_spent"],  # negative — points were spent
                    str(payment["id"]),
                    json.dumps(
                        {
                            "amount_ghs": float(payment["amount_ghs"]),
                            "reference": reference,
                        }
                    ),
                )
            else:
                # Refund points if payment failed
                await conn.execute(
                    "UPDATE payments SET status='failed', updated_at=NOW() WHERE paystack_ref=$1",
                    reference,
                )
                await conn.execute(
                    "UPDATE users SET total_points = total_points + $1, updated_at=NOW() WHERE id=$2",
                    payment["points_spent"],
                    str(payment["user_id"]),
                )

        return {
            "reference": reference,
            "status": status,
            "amount_ghs": float(payment["amount_ghs"]),
            "points_spent": payment["points_spent"],
            "message": (
                "Payment successful!"
                if status == "success"
                else f"Payment {status}. Points have been refunded."
            ),
        }

    # ------------------------------------------------------------------
    # 3. Mobile Money withdrawal
    # ------------------------------------------------------------------

    async def withdraw_to_momo(
        self,
        user_id: str,
        points_to_redeem: int,
        momo_number: str,
        momo_provider: str,
    ) -> Dict[str, Any]:
        """
        Send GHS directly to a Mobile Money number via Paystack Transfer API.

        Flow:
        1. Validate points + phone number
        2. Create Paystack Transfer Recipient
        3. Initiate transfer
        4. Deduct points on success
        """

        # Validate provider
        momo_provider = momo_provider.lower()
        if momo_provider not in MOMO_PROVIDERS:
            raise ValueError(
                f"Invalid provider. Must be one of: {', '.join(MOMO_PROVIDERS.keys())}"
            )

        # Validate minimum
        if points_to_redeem < MIN_REDEMPTION_POINTS:
            raise ValueError(f"Minimum redemption is {MIN_REDEMPTION_POINTS} points")

        amount_ghs = round(points_to_redeem * POINTS_TO_GHS_RATE, 2)

        # Validate + normalise phone number
        momo_number = self._normalise_phone(momo_number)
        detected = self._detect_provider(momo_number)

        if detected and detected != momo_provider:
            raise ValueError(
                f"Phone number {momo_number} looks like {MOMO_PROVIDERS[detected]}, not {MOMO_PROVIDERS[momo_provider]}"
            )

        async with get_connection() as conn:
            user = await conn.fetchrow(
                "SELECT id, total_points, display_name, username FROM users WHERE id=$1",
                user_id,
            )
            if not user:
                raise ValueError("User not found")
            if (user["total_points"] or 0) < points_to_redeem:
                raise ValueError(
                    f"Not enough points. You have {user['total_points']} but need {points_to_redeem}"
                )

        # Step 1: Create transfer recipient on Paystack
        recipient_code = await self._create_momo_recipient(
            name=user["display_name"] or user["username"],
            account_number=momo_number,
            bank_code=self._get_momo_bank_code(momo_provider),
        )

        ref = f"TANKAS-MOMO-{uuid.uuid4().hex[:12].upper()}"

        # Step 2: Initiate transfer
        transfer_data = await self._initiate_transfer(
            amount_ghs=amount_ghs,
            recipient_code=recipient_code,
            reference=ref,
            reason=f"Tankas points redemption — {points_to_redeem} points",
        )

        transfer_status = transfer_data.get("status", "pending")

        async with get_connection() as conn:
            # Deduct points
            await conn.execute(
                "UPDATE users SET total_points = total_points - $1, updated_at=NOW() WHERE id=$2",
                points_to_redeem,
                user_id,
            )

            # Record payment
            payment = await conn.fetchrow(
                """
                INSERT INTO payments
                    (user_id, payment_type, amount_ghs, points_spent,
                     status, paystack_ref, momo_provider, momo_number,
                     metadata, created_at, updated_at)
                VALUES ($1,'withdrawal',$2,$3,$4,$5,$6,$7,$8,NOW(),NOW())
                RETURNING id
                """,
                user_id,
                amount_ghs,
                points_to_redeem,
                transfer_status,
                ref,
                momo_provider,
                momo_number,
                json.dumps(
                    {
                        "recipient_code": recipient_code,
                        "transfer_code": transfer_data.get("transfer_code"),
                        "provider_name": MOMO_PROVIDERS[momo_provider],
                    }
                ),
            )

            # Log activity
            await conn.execute(
                """
                INSERT INTO user_activity_log
                    (user_id, activity_type, activity_date, points_earned,
                     reference_id, reference_type, metadata, created_at)
                VALUES ($1,'momo_withdrawal',$2,$3,$4,'payment',$5,NOW())
                """,
                user_id,
                datetime.utcnow().date(),
                -points_to_redeem,
                str(payment["id"]),
                json.dumps(
                    {
                        "amount_ghs": amount_ghs,
                        "momo_number": momo_number,
                        "provider": momo_provider,
                    }
                ),
            )

        return {
            "payment_id": str(payment["id"]),
            "reference": ref,
            "amount_ghs": amount_ghs,
            "points_spent": points_to_redeem,
            "momo_number": momo_number,
            "momo_provider": MOMO_PROVIDERS[momo_provider],
            "status": transfer_status,
            "message": f"GHS {amount_ghs} is being sent to {momo_number} ({MOMO_PROVIDERS[momo_provider]})",
        }

    # ------------------------------------------------------------------
    # 4. Webhook handler
    # ------------------------------------------------------------------

    async def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Verify and process Paystack webhook events.
        Paystack sends events for: charge.success, transfer.success, transfer.failed
        """

        # Verify signature
        expected = hmac.new(
            self.secret_key.encode("utf-8"),
            payload,
            hashlib.sha512,
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid webhook signature")

        event = json.loads(payload)
        event_type = event.get("event")
        data = event.get("data", {})

        print(f"[WEBHOOK] Received: {event_type}")

        if event_type == "charge.success":
            await self._handle_charge_success(data)

        elif event_type == "transfer.success":
            await self._handle_transfer_success(data)

        elif event_type == "transfer.failed":
            await self._handle_transfer_failed(data)

        elif event_type == "transfer.reversed":
            await self._handle_transfer_failed(data)

        return {"status": "processed", "event": event_type}

    # ------------------------------------------------------------------
    # 5. Payment history
    # ------------------------------------------------------------------

    async def get_payment_history(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        payment_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return paginated payment history for a user."""

        async with get_connection() as conn:

            if payment_type:
                rows = await conn.fetch(
                    """
                    SELECT * FROM payments
                    WHERE user_id=$1 AND payment_type=$2
                    ORDER BY created_at DESC
                    LIMIT $3 OFFSET $4
                    """,
                    user_id,
                    payment_type,
                    limit,
                    offset,
                )
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM payments WHERE user_id=$1 AND payment_type=$2",
                    user_id,
                    payment_type,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM payments
                    WHERE user_id=$1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    user_id,
                    limit,
                    offset,
                )
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM payments WHERE user_id=$1",
                    user_id,
                )

        payments = []
        for row in rows:
            payments.append(
                {
                    "payment_id": str(row["id"]),
                    "payment_type": row["payment_type"],
                    "amount_ghs": float(row["amount_ghs"]),
                    "points_spent": row["points_spent"],
                    "status": row["status"],
                    "reference": row["paystack_ref"],
                    "momo_provider": row["momo_provider"],
                    "momo_number": row["momo_number"],
                    "created_at": row["created_at"].isoformat(),
                }
            )

        return {
            "payments": payments,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        }

    # ------------------------------------------------------------------
    # Webhook event handlers
    # ------------------------------------------------------------------

    async def _handle_charge_success(self, data: dict) -> None:
        """Handle successful card/bank payment."""
        ref = data.get("reference")
        if not ref:
            return

        async with get_connection() as conn:
            payment = await conn.fetchrow(
                "SELECT * FROM payments WHERE paystack_ref=$1",
                ref,
            )
            if not payment or payment["status"] == "completed":
                return

            await conn.execute(
                "UPDATE payments SET status='completed', updated_at=NOW() WHERE paystack_ref=$1",
                ref,
            )

            await conn.execute(
                """
                INSERT INTO user_activity_log
                    (user_id, activity_type, activity_date, points_earned,
                     reference_id, reference_type, metadata, created_at)
                VALUES ($1,'points_redeemed',$2,$3,$4,'payment',$5,NOW())
                """,
                str(payment["user_id"]),
                datetime.utcnow().date(),
                -payment["points_spent"],
                str(payment["id"]),
                json.dumps(
                    {"amount_ghs": float(payment["amount_ghs"]), "reference": ref}
                ),
            )

    async def _handle_transfer_success(self, data: dict) -> None:
        """Handle successful MoMo transfer."""
        ref = data.get("reference")
        if not ref:
            return

        async with get_connection() as conn:
            await conn.execute(
                "UPDATE payments SET status='completed', updated_at=NOW() WHERE paystack_ref=$1",
                ref,
            )

    async def _handle_transfer_failed(self, data: dict) -> None:
        """Handle failed/reversed MoMo transfer — refund points."""
        ref = data.get("reference")
        if not ref:
            return

        async with get_connection() as conn:
            payment = await conn.fetchrow(
                "SELECT * FROM payments WHERE paystack_ref=$1",
                ref,
            )
            if not payment or payment["status"] in ("completed", "refunded"):
                return

            await conn.execute(
                "UPDATE payments SET status='failed', updated_at=NOW() WHERE paystack_ref=$1",
                ref,
            )

            # Refund points
            await conn.execute(
                "UPDATE users SET total_points = total_points + $1, updated_at=NOW() WHERE id=$2",
                payment["points_spent"],
                str(payment["user_id"]),
            )

            print(
                f"[WEBHOOK] Refunded {payment['points_spent']} points to user {payment['user_id']}"
            )

    # ------------------------------------------------------------------
    # Paystack API helpers
    # ------------------------------------------------------------------

    async def _create_momo_recipient(
        self, name: str, account_number: str, bank_code: str
    ) -> str:
        """Create a Paystack transfer recipient for MoMo."""
        payload = {
            "type": "mobile_money",
            "name": name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": "GHS",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/transferrecipient",
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            data = response.json()

        if not data.get("status"):
            raise Exception(f"Failed to create MoMo recipient: {data.get('message')}")

        return data["data"]["recipient_code"]

    async def _initiate_transfer(
        self,
        amount_ghs: float,
        recipient_code: str,
        reference: str,
        reason: str,
    ) -> dict:
        """Initiate a Paystack transfer."""
        payload = {
            "source": "balance",
            "amount": int(amount_ghs * 100),  # pesewas
            "recipient": recipient_code,
            "reference": reference,
            "reason": reason,
            "currency": "GHS",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/transfer",
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            data = response.json()

        if not data.get("status"):
            raise Exception(f"Transfer failed: {data.get('message')}")

        return data["data"]

    # ------------------------------------------------------------------
    # Phone number helpers
    # ------------------------------------------------------------------

    def _normalise_phone(self, phone: str) -> str:
        """Normalise Ghana phone to 10-digit local format (0XXXXXXXXX)."""
        phone = phone.strip().replace(" ", "").replace("-", "")

        if phone.startswith("+233"):
            phone = "0" + phone[4:]
        elif phone.startswith("233"):
            phone = "0" + phone[3:]

        if len(phone) != 10 or not phone.startswith("0"):
            raise ValueError(f"Invalid Ghana phone number: {phone}")

        return phone

    def _detect_provider(self, phone: str) -> Optional[str]:
        """Detect MoMo provider from phone prefix."""
        prefix = phone[:3]

        if prefix in MTN_PREFIXES:
            return "mtn"
        elif prefix in VODAFONE_PREFIXES:
            return "vodafone"
        elif prefix in AIRTELTIGO_PREFIXES:
            return "airteltigo"

        return None

    def _get_momo_bank_code(self, provider: str) -> str:
        """Paystack bank codes for Ghana MoMo providers."""
        codes = {
            "mtn": "MTN",
            "vodafone": "VOD",
            "airteltigo": "ATL",
        }
        return codes[provider]
