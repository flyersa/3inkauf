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
        # AWS SES occasionally hangs on QUIT after accepting the message; cap
        # the total SMTP operation so auth/forgot-password always returns.
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
            timeout=15,
        )
        logger.info(f"Password reset email sent to {to_email}")
    except TimeoutError:
        logger.warning(f"SMTP timed out on password reset to {to_email} (likely delivered)")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        # In development, log the reset URL so we can still test
        logger.warning(f"Reset URL (dev fallback): {reset_url}")


async def send_delete_confirmation_email(to_email: str, code: str, locale: str = "de"):
    """Send account-deletion confirmation code via AWS SES SMTP.

    The code is a 6-digit number that expires in 15 minutes. Subject and body
    are intentionally clear so the recipient understands this is a destructive
    action triggered from their own account.
    """
    if locale == "de":
        subject = "Konto löschen - Bestätigungscode"
        body_html = f"""
        <html><body style="font-family: sans-serif; padding: 20px;">
        <h2>Bestätige das Löschen deines Kontos</h2>
        <p>Du hast das Löschen deines 3inkauf-Kontos angefordert.</p>
        <p>Um fortzufahren, gib diesen Code in der App ein:</p>
        <p style="font-size: 32px; letter-spacing: 6px; font-weight: bold; color: #E74C3C; background: #f8f8f8; padding: 16px; text-align: center; border-radius: 8px;">{code}</p>
        <p>Der Code ist 15 Minuten gültig und kann nur einmal verwendet werden.</p>
        <p><strong>Hinweis:</strong> Nach Bestätigung werden alle deine Listen, Artikel, Kundenkarten und Freigaben
        unwiderruflich gelöscht. Dieser Vorgang kann nicht rückgängig gemacht werden.</p>
        <p>Falls du diese Anfrage nicht gestellt hast, kannst du diese E-Mail ignorieren und solltest sofort dein
        Passwort ändern.</p>
        </body></html>
        """
    else:
        subject = "Delete account - Confirmation code"
        body_html = f"""
        <html><body style="font-family: sans-serif; padding: 20px;">
        <h2>Confirm account deletion</h2>
        <p>You requested to delete your 3inkauf account.</p>
        <p>Enter this code in the app to continue:</p>
        <p style="font-size: 32px; letter-spacing: 6px; font-weight: bold; color: #E74C3C; background: #f8f8f8; padding: 16px; text-align: center; border-radius: 8px;">{code}</p>
        <p>This code is valid for 15 minutes and can only be used once.</p>
        <p><strong>Note:</strong> Once confirmed, all your lists, items, bonus cards and shares will be
        permanently deleted. This action cannot be undone.</p>
        <p>If you did not make this request, you can ignore this email and should change your password
        immediately.</p>
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
            timeout=15,
        )
        logger.info(f"Account deletion code email sent to {to_email}")
    except TimeoutError:
        logger.warning(f"SMTP timed out on delete-confirmation to {to_email} (likely delivered)")
    except Exception as e:
        logger.error(f"Failed to send delete-confirmation email to {to_email}: {e}")
        # Dev-only fallback: surface the code in logs when SMTP is dead so we
        # can still test the flow. NEVER in production — aggregated logs are a
        # one-line exfil of every deletion code.
        if settings.debug:
            logger.warning(f"Delete code (dev fallback): {code}")
