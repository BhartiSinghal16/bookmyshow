import logging
import threading
import time

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

logger = logging.getLogger('bookmyseat.email')


class EmailQueue:
    MAX_RETRIES = 3
    RETRY_DELAY = 5

    @classmethod
    def send_booking_confirmation(cls, booking_data):
        thread = threading.Thread(
            target=cls._send_with_retry,
            args=(booking_data,),
            daemon=True
        )
        thread.start()
        logger.info(
            f"[EmailQueue] Booking confirmation queued for "
            f"user={booking_data.get('username')} "
            f"booking_id={booking_data.get('booking_id')}"
        )

    @classmethod
    def _send_with_retry(cls, booking_data):
        recipient  = booking_data.get('user_email')
        booking_id = booking_data.get('booking_id')

        for attempt in range(1, cls.MAX_RETRIES + 1):
            try:
                cls._send_email(booking_data)
                logger.info(
                    f"[EmailQueue] SUCCESS: Email sent to {recipient} "
                    f"booking_id={booking_id} attempt={attempt}"
                )
                return

            except Exception as e:
                logger.warning(
                    f"[EmailQueue] FAILED: attempt={attempt}/{cls.MAX_RETRIES} "
                    f"booking_id={booking_id} error={type(e).__name__}: {str(e)}"
                )
                if attempt < cls.MAX_RETRIES:
                    logger.info(f"[EmailQueue] Retrying in {cls.RETRY_DELAY}s...")
                    time.sleep(cls.RETRY_DELAY)

        logger.error(
            f"[EmailQueue] DELIVERY FAILED after {cls.MAX_RETRIES} attempts "
            f"booking_id={booking_id} recipient={recipient}"
        )

    @classmethod
    def _send_email(cls, booking_data):
        subject = (
            f"Booking Confirmed! — {booking_data.get('movie_name')} "
            f"| BookMySeat"
        )

        html_content = render_to_string(
            'emails/booking_confirmation.html',
            booking_data
        )
        text_content = strip_tags(html_content)

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[booking_data['user_email']],
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)