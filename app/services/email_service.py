"""
email_service.py — transactional email

Three transports, chosen by EMAIL_PROVIDER or by whichever is configured
first: Resend (HTTPS), Brevo (HTTPS) and Gmail SMTP.

Hosts commonly block outbound SMTP — Railway does on Free/Trial/Hobby — so a
deploy generally needs one of the HTTPS options even though Gmail SMTP works
fine locally.

Handles OTP, welcome and notification emails.
"""

import asyncio
import random
import smtplib
import string

import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import config


# smtplib blocks with no timeout by default, so an unreachable or slow SMTP
# server can hang a request indefinitely. Bound it.
SMTP_TIMEOUT_SECONDS = 15

# Cap the Resend HTTPS call too, for the same reason.
HTTP_TIMEOUT_SECONDS = 15


def _log(message: str) -> None:
    """
    Console logging that cannot raise. Subjects contain emoji, and on a console
    with a non-UTF-8 encoding (Windows cp1252) print() throws
    UnicodeEncodeError — which, from inside an except block, would turn a failed
    send into an exception escaping into the caller.
    """
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", "backslashreplace").decode("ascii"))


# Log the active transport once, so "which provider is actually sending?" is
# answerable from the deploy logs instead of by guesswork.
_announced: set[str] = set()


# Strong references to in-flight background sends. Without this the event loop
# can garbage-collect a task that nothing is awaiting, cancelling it mid-send.
_background_sends: set[asyncio.Task] = set()


def fire_and_forget(coro) -> None:
    """
    Run a coroutine without awaiting it, so the caller returns immediately.

    Used for transactional email: the OTP row is already committed, so delivery
    is not something the HTTP response should wait on. Failures are logged by
    `EmailService._send` and the user can hit "resend".
    """
    try:
        task = asyncio.create_task(coro)
    except RuntimeError:
        # No running loop (e.g. called from a sync context or a script).
        # Fall back to sending inline rather than dropping the mail silently.
        asyncio.run(coro)
        return
    _background_sends.add(task)
    task.add_done_callback(_background_sends.discard)


class EmailService:

    def __init__(self):
        self.sender_email = config.GMAIL_SENDER_EMAIL
        self.app_password = config.GMAIL_APP_PASSWORD
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 587
        self.resend_api_key = config.RESEND_API_KEY
        self.resend_from = config.RESEND_FROM
        self.brevo_api_key = config.BREVO_API_KEY
        self.brevo_sender_email = config.BREVO_SENDER_EMAIL
        self.brevo_sender_name = config.BREVO_SENDER_NAME

    # ------------------------------------------------------------------
    # Core send method
    # ------------------------------------------------------------------

    def _resolve_provider(self) -> str:
        """
        Which transport to use.

        EMAIL_PROVIDER pins it explicitly ("resend" | "brevo" | "smtp").
        Left unset, the first configured transport wins, in that order — which
        means simply having RESEND_API_KEY present silently beats Brevo. Set
        EMAIL_PROVIDER when you want to be sure which one is in play.
        """
        pinned = (config.EMAIL_PROVIDER or "").strip().lower()
        if pinned in {"resend", "brevo", "smtp"}:
            return pinned
        if self.resend_api_key:
            return "resend"
        if self.brevo_api_key:
            return "brevo"
        return "smtp"

    def _send(self, to_email: str, subject: str, html_body: str) -> bool:
        """
        Send an email over the resolved transport.

        Both HTTPS options exist because Railway blocks outbound SMTP on Free,
        Trial and Hobby plans — SMTP fails there with "[Errno 101] Network is
        unreachable" no matter how the client is configured, while port 443 is
        never blocked. Gmail SMTP is fine locally; it is the host that refuses.

        Resend needs a verified *domain* to reach anyone but the account owner.
        Brevo reaches anyone from a verified *sender address*, so it is the
        option that works without owning a domain.

        Always wrapped in try/except — email failures must never crash requests.
        """
        provider = self._resolve_provider()

        if provider not in _announced:
            _announced.add(provider)
            detail = {
                "resend": f"from {self.resend_from}",
                "brevo": f"from {self.brevo_sender_name} <{self.brevo_sender_email}>",
                "smtp": f"via {self.smtp_host} as {self.sender_email}",
            }[provider]
            pinned = "pinned by EMAIL_PROVIDER" if config.EMAIL_PROVIDER else "auto-selected"
            _log(f"[EMAIL] transport = {provider} ({pinned}), {detail}")

        if provider == "resend":
            return self._send_via_resend(to_email, subject, html_body)
        if provider == "brevo":
            return self._send_via_brevo(to_email, subject, html_body)
        return self._send_via_smtp(to_email, subject, html_body)

    def _send_via_brevo(self, to_email: str, subject: str, html_body: str) -> bool:
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
                r = client.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={
                        "api-key": self.brevo_api_key,
                        "content-type": "application/json",
                        "accept": "application/json",
                    },
                    json={
                        "sender": {
                            "name": self.brevo_sender_name,
                            "email": self.brevo_sender_email,
                        },
                        "to": [{"email": to_email}],
                        "subject": subject,
                        "htmlContent": html_body,
                    },
                )

            if r.status_code >= 400:
                # Usually an unverified sender address.
                _log(
                    f"[EMAIL] Brevo rejected '{subject}' to {to_email}: "
                    f"{r.status_code} {r.text[:300]}"
                )
                return False

            _log(f"[EMAIL] Sent '{subject}' to {to_email} via Brevo")
            return True

        except Exception as e:
            _log(f"[EMAIL] Brevo failed for '{subject}' to {to_email}: {e}")
            return False

    def _send_via_resend(self, to_email: str, subject: str, html_body: str) -> bool:
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
                r = client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {self.resend_api_key}"},
                    json={
                        "from": self.resend_from,
                        "to": [to_email],
                        "subject": subject,
                        "html": html_body,
                    },
                )

            if r.status_code >= 400:
                # Resend returns a JSON body explaining the rejection — an
                # unverified sending domain is the usual cause.
                _log(
                    f"[EMAIL] Resend rejected '{subject}' to {to_email}: "
                    f"{r.status_code} {r.text[:300]}"
                )
                return False

            _log(f"[EMAIL] Sent '{subject}' to {to_email} via Resend")
            return True

        except Exception as e:
            _log(f"[EMAIL] Resend failed for '{subject}' to {to_email}: {e}")
            return False

    def _send_via_smtp(self, to_email: str, subject: str, html_body: str) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Tankas 🌍 <{self.sender_email}>"
            msg["To"] = to_email

            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(
                self.smtp_host, self.smtp_port, timeout=SMTP_TIMEOUT_SECONDS
            ) as server:
                server.ehlo()
                server.starttls()
                server.login(self.sender_email, self.app_password)
                server.sendmail(self.sender_email, to_email, msg.as_string())

            _log(f"[EMAIL] Sent '{subject}' to {to_email}")
            return True

        except Exception as e:
            _log(f"[EMAIL] Failed to send '{subject}' to {to_email}: {e}")
            return False

    # ------------------------------------------------------------------
    # Async variants
    #
    # `_send` blocks, on either transport. Calling it straight from a coroutine
    # stalls the whole event loop — every other in-flight request waits on that
    # one round-trip. These hand the work to a worker thread instead.
    # ------------------------------------------------------------------

    async def send_otp_async(
        self, to_email: str, otp_code: str, username: str
    ) -> bool:
        return await asyncio.to_thread(self.send_otp, to_email, otp_code, username)

    async def send_welcome_async(self, to_email: str, username: str) -> bool:
        return await asyncio.to_thread(self.send_welcome, to_email, username)

    # ------------------------------------------------------------------
    # OTP email
    # ------------------------------------------------------------------

    def send_otp(self, to_email: str, otp_code: str, username: str) -> bool:
        subject = "Your Tankas verification code"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #16a34a; padding: 24px; text-align: center;">
                <h1 style="color: white; margin: 0;">🌍 Tankas</h1>
                <p style="color: #dcfce7; margin: 4px 0 0;">Snap. Clean. Earn.</p>
            </div>

            <div style="padding: 32px; background: #f9fafb;">
                <h2 style="color: #111827;">Hi {username}!</h2>
                <p style="color: #4b5563;">Your verification code is:</p>

                <div style="background: white; border: 2px solid #16a34a; border-radius: 12px;
                            padding: 24px; text-align: center; margin: 24px 0;">
                    <span style="font-size: 42px; font-weight: bold; letter-spacing: 12px;
                                 color: #16a34a;">{otp_code}</span>
                </div>

                <p style="color: #6b7280; font-size: 14px;">
                    This code expires in <strong>10 minutes</strong>.<br>
                    If you didn't request this, you can safely ignore this email.
                </p>
            </div>

            <div style="padding: 16px; text-align: center; background: #f3f4f6;">
                <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                    © 2026 Tankas · Ghana's Environmental Cleanup Platform
                </p>
            </div>
        </div>
        """
        return self._send(to_email, subject, html)

    # ------------------------------------------------------------------
    # Welcome email
    # ------------------------------------------------------------------

    def send_welcome(self, to_email: str, username: str) -> bool:
        subject = "Welcome to Tankas! 🌍"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #16a34a; padding: 24px; text-align: center;">
                <h1 style="color: white; margin: 0;">🌍 Tankas</h1>
                <p style="color: #dcfce7; margin: 4px 0 0;">Snap. Clean. Earn.</p>
            </div>

            <div style="padding: 32px; background: #f9fafb;">
                <h2 style="color: #111827;">Welcome, {username}! 🎉</h2>
                <p style="color: #4b5563;">
                    You're now part of Ghana's environmental cleanup movement.
                    Here's how to get started:
                </p>

                <div style="background: white; border-radius: 12px; padding: 24px; margin: 24px 0;">
                    <div style="margin-bottom: 16px;">
                        <span style="font-size: 24px;">📸</span>
                        <strong style="color: #111827;"> Snap</strong>
                        <p style="color: #6b7280; margin: 4px 0 0 32px;">
                            Report environmental issues in your community with a photo.
                            Earn 15 points instantly.
                        </p>
                    </div>
                    <div style="margin-bottom: 16px;">
                        <span style="font-size: 24px;">🧹</span>
                        <strong style="color: #111827;"> Clean</strong>
                        <p style="color: #6b7280; margin: 4px 0 0 32px;">
                            Join cleanup groups and earn up to 60 points per cleanup.
                        </p>
                    </div>
                    <div>
                        <span style="font-size: 24px;">💰</span>
                        <strong style="color: #111827;"> Earn</strong>
                        <p style="color: #6b7280; margin: 4px 0 0 32px;">
                            Redeem your points for GHS via Mobile Money.
                            100 points = GHS 1.
                        </p>
                    </div>
                </div>

                <p style="color: #4b5563;">
                    Your account starts with <strong style="color: #16a34a;">Bronze tier</strong>.
                    Earn 100 points to reach Silver! 🥈
                </p>
            </div>

            <div style="padding: 16px; text-align: center; background: #f3f4f6;">
                <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                    © 2026 Tankas · Ghana's Environmental Cleanup Platform
                </p>
            </div>
        </div>
        """
        return self._send(to_email, subject, html)

    # ------------------------------------------------------------------
    # Issue reported confirmation
    # ------------------------------------------------------------------

    def send_issue_reported(
        self, to_email: str, username: str, title: str, points: int
    ) -> bool:
        subject = f"Issue reported — you earned {points} points! 🌱"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #16a34a; padding: 24px; text-align: center;">
                <h1 style="color: white; margin: 0;">🌍 Tankas</h1>
            </div>
            <div style="padding: 32px; background: #f9fafb;">
                <h2 style="color: #111827;">Nice work, {username}! 📸</h2>
                <p style="color: #4b5563;">
                    Your issue <strong>"{title}"</strong> has been reported successfully.
                </p>
                <div style="background: #dcfce7; border-radius: 12px; padding: 16px;
                            text-align: center; margin: 24px 0;">
                    <p style="color: #15803d; font-size: 24px; font-weight: bold; margin: 0;">
                        +{points} points earned! 🎯
                    </p>
                </div>
                <p style="color: #6b7280; font-size: 14px;">
                    Volunteers in your area will be notified. 
                    You'll earn more points when the issue is cleaned up!
                </p>
            </div>
            <div style="padding: 16px; text-align: center; background: #f3f4f6;">
                <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                    © 2026 Tankas · Ghana's Environmental Cleanup Platform
                </p>
            </div>
        </div>
        """
        return self._send(to_email, subject, html)

    # ------------------------------------------------------------------
    # Payment received
    # ------------------------------------------------------------------

    def send_payment_received(
        self, to_email: str, username: str, amount_ghs: float, points_spent: int
    ) -> bool:
        subject = f"GHS {amount_ghs} is on its way! 💰"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #16a34a; padding: 24px; text-align: center;">
                <h1 style="color: white; margin: 0;">🌍 Tankas</h1>
            </div>
            <div style="padding: 32px; background: #f9fafb;">
                <h2 style="color: #111827;">Payment processed, {username}! 💸</h2>
                <div style="background: white; border: 2px solid #16a34a; border-radius: 12px;
                            padding: 24px; text-align: center; margin: 24px 0;">
                    <p style="color: #6b7280; margin: 0;">Amount sent</p>
                    <p style="font-size: 36px; font-weight: bold; color: #16a34a; margin: 8px 0;">
                        GHS {amount_ghs}
                    </p>
                    <p style="color: #6b7280; margin: 0;">{points_spent} points redeemed</p>
                </div>
                <p style="color: #6b7280; font-size: 14px;">
                    Your Mobile Money payment is being processed.
                    It should arrive within a few minutes.
                </p>
            </div>
            <div style="padding: 16px; text-align: center; background: #f3f4f6;">
                <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                    © 2026 Tankas · Ghana's Environmental Cleanup Platform
                </p>
            </div>
        </div>
        """
        return self._send(to_email, subject, html)

    # ------------------------------------------------------------------
    # OTP code generator
    # ------------------------------------------------------------------

    @staticmethod
    def generate_otp(length: int = 6) -> str:
        """Generate a numeric OTP code."""
        return "".join(random.choices(string.digits, k=length))
