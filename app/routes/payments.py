"""
routes/payments.py — Payment endpoints
"""

from fastapi import APIRouter, HTTPException, Request, Header, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from app.services.payment_service import PaymentService
from app.utils.jwt_handler import JWTHandler

router = APIRouter(tags=["payments"])
payment_service = PaymentService()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RedeemPointsRequest(BaseModel):
    points: int
    email: str
    callback_url: Optional[str] = None


class MoMoWithdrawalRequest(BaseModel):
    points: int
    momo_number: str
    momo_provider: str  # 'mtn', 'vodafone', 'airteltigo'


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


async def get_current_user_id(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    parts = auth.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization header"
        )
    try:
        return JWTHandler.get_user_id_from_token(parts[1])
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/payments/redeem-points")
async def redeem_points(request: Request, body: RedeemPointsRequest):
    """
    Convert points to GHS via Paystack.

    Returns an authorization_url — redirect the user there to complete payment.
    After payment, Paystack redirects to callback_url (if provided).
    """
    user_id = await get_current_user_id(request)
    try:
        result = await payment_service.redeem_points(
            user_id=user_id,
            points_to_redeem=body.points,
            email=body.email,
            callback_url=body.callback_url,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payments/verify/{reference}")
async def verify_payment(request: Request, reference: str):
    """
    Verify a Paystack payment by reference.
    Call this after user returns from Paystack payment page.
    """
    await get_current_user_id(request)
    try:
        result = await payment_service.verify_payment(reference)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payments/withdraw-momo")
async def withdraw_momo(request: Request, body: MoMoWithdrawalRequest):
    """
    Send GHS directly to a Mobile Money number.

    Providers: mtn, vodafone, airteltigo
    Phone format: 0241234567 or +233241234567
    """
    user_id = await get_current_user_id(request)
    try:
        result = await payment_service.withdraw_to_momo(
            user_id=user_id,
            points_to_redeem=body.points,
            momo_number=body.momo_number,
            momo_provider=body.momo_provider,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payments/webhook")
async def paystack_webhook(
    request: Request,
    x_paystack_signature: Optional[str] = Header(None),
):
    """
    Paystack webhook endpoint.
    Paystack sends events here for: charge.success, transfer.success, transfer.failed
    No auth required — verified by HMAC signature instead.
    """
    if not x_paystack_signature:
        raise HTTPException(status_code=400, detail="Missing Paystack signature")

    payload = await request.body()

    try:
        result = await payment_service.handle_webhook(payload, x_paystack_signature)
        return {"success": True, "data": result}
    except ValueError as e:
        # Invalid signature
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payments/history")
async def payment_history(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    payment_type: Optional[str] = None,
):
    """
    Get payment history for the current user.
    Optional filter: ?payment_type=redemption or ?payment_type=withdrawal
    """
    user_id = await get_current_user_id(request)
    try:
        result = await payment_service.get_payment_history(
            user_id=user_id,
            limit=limit,
            offset=offset,
            payment_type=payment_type,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payments/rates")
async def get_rates(request: Request):
    """
    Get current points → GHS conversion rates.
    Frontend uses this to show users how much their points are worth.
    """
    await get_current_user_id(request)
    return {
        "success": True,
        "data": {
            "points_to_ghs_rate": 0.01,
            "min_redemption_points": 500,
            "min_redemption_ghs": 5.00,
            "example": "500 points = GHS 5.00",
            "providers": {
                "mtn": "MTN Mobile Money",
                "vodafone": "Vodafone Cash",
                "airteltigo": "AirtelTigo Money",
            },
        },
    }
