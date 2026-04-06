"""
Multi-channel alert dispatcher: Email (SMTP/SendGrid), SMS (Twilio),
Telegram bot, and Pushover.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx

from ..config import get_settings
from .crypto import decrypt

logger = logging.getLogger(__name__)
settings = get_settings()


def _format_alert_body(user_product, result, reason: str) -> tuple[str, str]:
    """Return (subject, html_body) for the alert."""
    product = user_product.product
    title = product.title if product else result.asin
    price = f"${result.price:.2f}" if result.price else "N/A"
    list_p = f"${result.list_price:.2f}" if result.list_price else ""
    discount = f"{result.discount_pct:.0f}% off" if result.discount_pct else ""
    url = product.product_url if product else f"https://www.amazon.com/dp/{result.asin}"
    badge = f"<br><strong>Deal:</strong> {result.deal_badge}" if result.deal_badge else ""

    subject = f"Price Alert: {title[:60]} — {reason}"
    html = f"""
<html><body style="font-family:sans-serif;max-width:600px;margin:auto">
  <h2 style="color:#FF9900">Amazon Price Alert</h2>
  <h3>{title}</h3>
  <p><strong>Current Price:</strong> {price}
     {f'<s style="color:#999">{list_p}</s>' if list_p else ''}
     {f'<span style="color:green"> ({discount})</span>' if discount else ''}
  </p>
  <p><strong>Reason:</strong> {reason}{badge}</p>
  <a href="{url}" style="background:#FF9900;color:white;padding:10px 20px;
     text-decoration:none;border-radius:4px;display:inline-block;margin-top:8px">
    View on Amazon
  </a>
  <p style="color:#999;font-size:12px;margin-top:24px">
    Sent by Amazon Price Tracker at jack-hoy.com/amazon
  </p>
</body></html>"""
    return subject, html


async def _send_email(to: str, subject: str, html: str):
    """Send via SMTP or SendGrid based on config."""
    if settings.EMAIL_PROVIDER == "sendgrid" and settings.SENDGRID_API_KEY:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
                json={
                    "personalizations": [{"to": [{"email": to}]}],
                    "from": {"email": settings.SMTP_FROM},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": html}],
                },
            )
            if resp.status_code not in (200, 202):
                logger.error("SendGrid failed %s: %s", resp.status_code, resp.text[:200])
    else:
        # SMTP
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        msg.attach(MIMEText(html, "html"))
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
                s.starttls()
                if settings.SMTP_USER:
                    s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.sendmail(settings.SMTP_FROM, [to], msg.as_string())
        except Exception as exc:
            logger.error("SMTP failed: %s", exc)


async def _send_sms(to: str, body: str):
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN):
        return
    try:
        async with httpx.AsyncClient(
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        ) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
                data={"From": settings.TWILIO_FROM_NUMBER, "To": to, "Body": body[:160]},
            )
            if resp.status_code not in (200, 201):
                logger.error("Twilio failed %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.error("SMS failed: %s", exc)


async def _send_telegram(chat_id: str, text: str):
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
    except Exception as exc:
        logger.error("Telegram failed: %s", exc)


async def _send_pushover(user_key: str, title: str, message: str, url: str):
    if not settings.PUSHOVER_APP_TOKEN:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": settings.PUSHOVER_APP_TOKEN,
                    "user": user_key,
                    "title": title,
                    "message": message,
                    "url": url,
                    "url_title": "View on Amazon",
                },
            )
    except Exception as exc:
        logger.error("Pushover failed: %s", exc)


async def send_price_alert(user, user_product, result, reason: str):
    """Dispatch alerts via all configured channels for this user/product."""
    subject, html = _format_alert_body(user_product, result, reason)
    product = user_product.product
    product_url = product.product_url if product else f"https://www.amazon.com/dp/{result.asin}"
    title = product.title if product else result.asin
    sms_body = f"Price Alert: {title[:40]} — {reason}. {product_url}"

    # Email
    if user_product.notify_email and user.alert_email:
        email = user.alert_email
        # Try decrypting in case it's encrypted
        try:
            email = decrypt(email)
        except Exception:
            pass
        await _send_email(email, subject, html)

    # SMS
    if user_product.notify_sms and user.alert_sms:
        await _send_sms(user.alert_sms, sms_body)

    # Telegram
    if user_product.notify_telegram and user.alert_telegram_chat_id:
        tg_text = (
            f"<b>Price Alert</b>\n{title}\n"
            f"<b>{reason}</b>\n"
            f'<a href="{product_url}">View on Amazon</a>'
        )
        await _send_telegram(user.alert_telegram_chat_id, tg_text)

    # Pushover
    if user_product.notify_pushover and user.alert_pushover_user_key:
        await _send_pushover(
            user.alert_pushover_user_key,
            f"Price Alert: {reason}",
            title[:100],
            product_url,
        )
