import logging
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_password_reset_email(to_email: str, reset_token: str, locale: str = "de"):
    """Send password reset email via AWS SES SMTP."""
    reset_url = f"{settings.base_url}/#/reset-password/{reset_token}"

    if locale == "de":
        subject = "Passwort zurücksetzen - Einkaufsliste"
        body_html = f"""
        <html><body style="font-family: sans-serif; padding: 20px;">
        <h2>Passwort zurücksetzen</h2>
        <p>Du hast eine Anfrage zum Zurücksetzen deines Passworts gestellt.</p>
        <p>Klicke auf den folgenden Link, um dein Passwort zurückzusetzen:</p>
        <p><a href="{reset_url}" style="background: #4A90D9; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">Passwort zurücksetzen</a></p>
        <p>Dieser Link ist 1 Stunde gültig.</p>
        <p>Falls du diese Anfrage nicht gestellt hast, ignoriere diese E-Mail.</p>
        </body></html>
        """
    else:
        subject = "Reset Password - Grocery List"
        body_html = f"""
        <html><body style="font-family: sans-serif; padding: 20px;">
        <h2>Reset Your Password</h2>
        <p>You requested a password reset.</p>
        <p>Click the link below to reset your password:</p>
        <p><a href="{reset_url}" style="background: #4A90D9; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">Reset Password</a></p>
        <p>This link expires in 1 hour.</p>
        <p>If you did not request this, please ignore this email.</p>
        </body></html>
        """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_sender
    msg["To"] = to_email
    msg.attach(MIMEText(body_html, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info(f"Password reset email sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        # In development, log the reset URL so we can still test
        logger.warning(f"Reset URL (dev fallback): {reset_url}")
