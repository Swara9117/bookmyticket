from celery import shared_task


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def send_ticket_email(self, delivery_id):
    """Email the PDF ticket. Celery retries failed deliveries with backoff.

    The booking request only stores a delivery row and returns. It does not
    wait for SMTP.
    """
    from .services import deliver_ticket_email

    deliver_ticket_email(delivery_id)
