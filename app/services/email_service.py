"""
email_service.py — Gmail SMTP email sending
Handles: OTP emails, welcome emails, notification emails
"""

import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import config


class EmailService:

    def __init__(self):
        self.sender_email = config.GMAIL_SENDER_EMAIL
        self.app_password = config.GMAIL_APP_PASSWORD
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 587

    # ------------------------------------------------------------------
    # Core send method
    # ------------------------------------------------------------------

    def _send(self, to_email: str, subject: str, html_body: str) -> bool:
        """
        Send an email via Gmail SMTP.
        Always wrapped in try/except — email failures must never crash requests.
        """
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Tankas 🌍 <{self.sender_email}>"
            msg["To"] = to_email

            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self.smtp_host, 587) as server:
                server.ehlo()
                server.starttls()
                server.login(self.sender_email, self.app_password)
                server.sendmail(self.sender_email, to_email, msg.as_string())

            print(f"[EMAIL] Sent '{subject}' to {to_email}")
            return True

        except Exception as e:
            print(f"[EMAIL] Failed to send '{subject}' to {to_email}: {e}")
            return False

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
