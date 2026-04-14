import logging
import threading
import time
from html import escape

from django.conf import settings
from django.core.mail import send_mail
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from .email_templates import render_email_template

logger = logging.getLogger(__name__)


def _send_via_sendgrid(subject, message, html_message, recipient_list):
    api_key = getattr(settings, "SENDGRID_API_KEY", None)
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)

    if not api_key:
        return False

    sg = SendGridAPIClient(api_key)
    for recipient in recipient_list:
        mail = Mail(
            from_email=from_email,
            to_emails=recipient,
            subject=subject,
            plain_text_content=message or "",
            html_content=html_message or "",
        )
        response = sg.send(mail)
        if not 200 <= int(response.status_code) < 300:
            raise RuntimeError(
                f"SendGrid returned status {response.status_code} for {recipient}"
            )

    logger.info("SendGrid email sent: %s -> %s", subject, recipient_list)
    return True


def _build_branded_html(subject, message):
        logo_url = getattr(settings, "TALENTOHUB_LOGO_URL", "")
        safe_subject = escape(subject or "Notificacion Talento Hub")
        safe_message = escape(message or "").replace("\n", "<br>")

        logo_block = ""
        if logo_url:
                logo_block = (
                        f'<img src="{escape(logo_url)}" alt="Talento Hub" '
                        'style="max-height:56px; width:auto; margin-bottom:12px;"/>'
                )

        return f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1f2937; background: #f5f7fb; padding: 24px;">
                <div style="max-width: 640px; margin: 0 auto; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden;">
                    <div style="background: linear-gradient(135deg, #0b5ed7, #0a4eb6); color: #ffffff; padding: 24px; text-align: center;">
                        {logo_block}
                        <h2 style="margin: 0; font-size: 22px;">{safe_subject}</h2>
                    </div>
                    <div style="padding: 24px; font-size: 15px; color: #374151;">
                        {safe_message}
                    </div>
                    <div style="padding: 16px 24px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; text-align: center;">
                        Talento Hub · Gestion de Candidatos
                    </div>
                </div>
            </body>
        </html>
        """


def _send_with_retry(send_fn, fail_silently, context_label):
    max_retries = max(0, int(getattr(settings, "EMAIL_MAX_RETRIES", 2)))
    backoff_seconds = float(getattr(settings, "EMAIL_RETRY_BACKOFF_SECONDS", 1.0))

    for attempt in range(max_retries + 1):
        try:
            return send_fn()
        except Exception:
            is_last = attempt >= max_retries
            logger.exception(
                "Email send failed (%s). attempt=%s/%s",
                context_label,
                attempt + 1,
                max_retries + 1,
            )
            if is_last:
                if fail_silently:
                    return False
                raise
            sleep_for = backoff_seconds * (2 ** attempt)
            time.sleep(sleep_for)


def send_plain_email(subject, message, recipient_list, fail_silently=False, async_send=False):
    """Send plain-text email using configured Django backend."""

    def _send():
        def _do_send():
            branded_html = _build_branded_html(subject, message)
            sent = send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=recipient_list,
                html_message=branded_html,
                fail_silently=fail_silently,
            )
            if sent:
                logger.info("Email sent: %s -> %s", subject, recipient_list)
            else:
                error_msg = f"Email not sent (0 messages): {subject} -> {recipient_list}"
                logger.warning(error_msg)
                if not fail_silently:
                    raise RuntimeError(error_msg)
            return bool(sent)

        try:
            sent = _send_with_retry(_do_send, fail_silently, f"plain:{subject}")
            if sent:
                return True
        except Exception as smtp_error:
            logger.warning("SMTP failed for %s, trying SendGrid fallback: %s", subject, smtp_error)
            if not getattr(settings, "SENDGRID_API_KEY", None):
                if fail_silently:
                    return False
                raise

        try:
            return _send_via_sendgrid(subject, message, _build_branded_html(subject, message), recipient_list)
        except Exception:
            logger.exception("SendGrid fallback failed for %s", subject)
            if fail_silently:
                return False
            raise

    if async_send:
        threading.Thread(target=_send, daemon=False).start()
        return True

    return _send()


def send_html_email(subject, html_message, recipient_list, message="", fail_silently=False, async_send=False):
    """Send HTML email using configured Django backend."""

    def _send():
        def _do_send():
            sent = send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=fail_silently,
            )
            if sent:
                logger.info("HTML email sent: %s -> %s", subject, recipient_list)
            else:
                error_msg = f"HTML email not sent (0 messages): {subject} -> {recipient_list}"
                logger.warning(error_msg)
                if not fail_silently:
                    raise RuntimeError(error_msg)
            return bool(sent)

        try:
            sent = _send_with_retry(_do_send, fail_silently, f"html:{subject}")
            if sent:
                return True
        except Exception as smtp_error:
            logger.warning("SMTP failed for %s, trying SendGrid fallback: %s", subject, smtp_error)
            if not getattr(settings, "SENDGRID_API_KEY", None):
                if fail_silently:
                    return False
                raise

        try:
            return _send_via_sendgrid(subject, message, html_message, recipient_list)
        except Exception:
            logger.exception("SendGrid fallback failed for %s", subject)
            if fail_silently:
                return False
            raise

    if async_send:
        threading.Thread(target=_send, daemon=False).start()
        return True

    return _send()


def send_message_async(email_message):
    """Send a Django EmailMessage instance in a background thread."""

    def _send():
        def _do_send():
            email_message.send(fail_silently=False)
            logger.info("EmailMessage sent to %s", getattr(email_message, "to", []))
            return True

        _send_with_retry(_do_send, fail_silently=True, context_label="email_message_async")

    threading.Thread(target=_send, daemon=False).start()


def send_template_email(template_key, recipient_list, context=None, fail_silently=False, async_send=False):
    merged_context = {
        "logo_url": getattr(settings, "TALENTOHUB_LOGO_URL", ""),
        "support_email": getattr(settings, "DEFAULT_FROM_EMAIL", ""),
    }
    merged_context.update(context or {})

    subject, text, html = render_email_template(template_key, merged_context)
    if html:
        return send_html_email(
            subject=subject,
            html_message=html,
            message=text,
            recipient_list=recipient_list,
            fail_silently=fail_silently,
            async_send=async_send,
        )
    return send_plain_email(
        subject=subject,
        message=text,
        recipient_list=recipient_list,
        fail_silently=fail_silently,
        async_send=async_send,
    )
