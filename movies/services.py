import logging
import secrets
import threading
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    Booking,
    EmailDelivery,
    Movie,
    Order,
    Payment,
    Refund,
    Review,
    Seat,
    SeatHold,
)
from .tickets import render_ticket_pdf

logger = logging.getLogger(__name__)

HOLD_MINUTES = 2


class SeatUnavailable(Exception):
    pass


def make_code(prefix):
    return prefix + secrets.token_hex(5).upper()


def release_expired_holds():
    """Free seats whose 2-minute hold has lapsed. Safe to call often."""
    now = timezone.now()
    Seat.objects.filter(status=Seat.RESERVED, reserved_until__lt=now).update(
        status=Seat.AVAILABLE,
        is_booked=False,
        reserved_by=None,
        reserved_until=None,
    )
    expired_ids = list(
        Order.objects.filter(status=Order.PENDING, expires_at__lt=now).values_list('id', flat=True)[:500]
    )
    if expired_ids:
        SeatHold.objects.filter(order_id__in=expired_ids).delete()
        Order.objects.filter(id__in=expired_ids).update(status=Order.EXPIRED)
    SeatHold.objects.filter(expires_at__lt=now).delete()
    return len(expired_ids)


def _lock_seats(theater, seat_ids):
    cleaned = []
    for raw in seat_ids:
        cleaned.append(int(raw))
    cleaned = sorted(set(cleaned))
    if not cleaned:
        raise SeatUnavailable('Select at least one seat.')
    seats = list(
        Seat.objects.select_for_update()
        .filter(id__in=cleaned, theater=theater)
        .order_by('id')
    )
    if len(seats) != len(cleaned):
        raise SeatUnavailable('One or more seats are not part of this show.')
    return seats


def _seat_is_held_by_someone_else(seat, user, now):
    if seat.status == Seat.BOOKED or seat.is_booked:
        return True
    if (
        seat.status == Seat.RESERVED
        and seat.reserved_until
        and seat.reserved_until > now
        and seat.reserved_by_id not in (None, user.id)
    ):
        return True
    confirmed = seat.bookings.filter(status=Booking.CONFIRMED).exists()
    return confirmed


def reserve_seats(user, theater, seat_ids):
    """Hold seats for two minutes. Replaces this user's unpaid hold for the show.

    Row locks are taken in seat-id order so two shoppers cannot book the same seat.
    """
    release_expired_holds()
    now = timezone.now()
    expires = now + timedelta(minutes=HOLD_MINUTES)
    with transaction.atomic():
        seats = _lock_seats(theater, seat_ids)
        taken = [seat.seat_number for seat in seats if _seat_is_held_by_someone_else(seat, user, now)]
        if taken:
            raise SeatUnavailable(f"These seats are no longer available: {', '.join(taken)}.")

        order = (
            Order.objects.select_for_update()
            .filter(user=user, theater=theater, status=Order.PENDING, expires_at__gt=now)
            .first()
        )
        if order is None:
            order = Order.objects.create(
                reference=make_code('ORD'),
                user=user,
                movie=theater.movie,
                theater=theater,
                status=Order.PENDING,
                currency='INR',
                expires_at=expires,
            )
        else:
            previous_ids = list(order.holds.values_list('seat_id', flat=True))
            Seat.objects.filter(
                id__in=previous_ids, status=Seat.RESERVED, reserved_by=user
            ).update(
                status=Seat.AVAILABLE,
                is_booked=False,
                reserved_by=None,
                reserved_until=None,
            )
            order.holds.all().delete()
            order.provider = ''
            order.provider_order_id = ''

        total = Decimal('0.00')
        for seat in seats:
            price = seat.price if seat.price is not None else theater.ticket_price
            total += price
            seat.status = Seat.RESERVED
            seat.is_booked = False
            seat.reserved_by = user
            seat.reserved_until = expires
            seat.save(update_fields=['status', 'is_booked', 'reserved_by', 'reserved_until'])
            SeatHold.objects.create(order=order, seat=seat, user=user, expires_at=expires)

        if total <= 0:
            raise SeatUnavailable('Ticket price is not set for this show.')

        order.amount = total
        order.expires_at = expires
        order.movie = theater.movie
        order.status = Order.PENDING
        order.save()
        return order


def release_order(order, new_status, reason=''):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == Order.PAID:
            return order
        seat_ids = list(order.holds.values_list('seat_id', flat=True))
        Seat.objects.filter(
            id__in=seat_ids, status=Seat.RESERVED, reserved_by=order.user
        ).update(
            status=Seat.AVAILABLE,
            is_booked=False,
            reserved_by=None,
            reserved_until=None,
        )
        order.holds.all().delete()
        order.status = new_status
        if reason:
            order.failure_reason = reason[:255]
        order.save(update_fields=['status', 'failure_reason'])
        return order


def _to_paise(amount):
    return int((Decimal(amount).quantize(Decimal('0.01'))) * 100)


def confirm_order(order, provider, provider_payment_id, provider_order_id, amount, event_id=''):
    """Confirm a paid order once. A repeated payment id never creates another booking."""
    if not provider_payment_id:
        raise ValueError('Missing payment id.')
    paid_now = False
    with transaction.atomic():
        order = Order.objects.select_for_update().select_related('movie', 'theater', 'user').get(pk=order.pk)
        if order.status == Order.PAID:
            return order

        existing = Payment.objects.select_for_update().filter(provider_payment_id=provider_payment_id).first()
        if existing and existing.order_id != order.id:
            logger.warning('Payment %s already belongs to another order', provider_payment_id)
            return order
        if existing and existing.status == Payment.CAPTURED and order.status == Order.PAID:
            return order

        if _to_paise(amount) != _to_paise(order.amount):
            order.failure_reason = 'Paid amount did not match the order.'
            order.status = Order.FAILED
            order.save(update_fields=['failure_reason', 'status'])
            seat_ids = list(order.holds.values_list('seat_id', flat=True))
            Seat.objects.filter(id__in=seat_ids, status=Seat.RESERVED, reserved_by=order.user).update(
                status=Seat.AVAILABLE, is_booked=False, reserved_by=None, reserved_until=None,
            )
            order.holds.all().delete()
            return order

        holds = list(
            SeatHold.objects.select_for_update().filter(order=order).select_related('seat')
        )
        seats = []
        for hold in holds:
            seat = Seat.objects.select_for_update().get(pk=hold.seat_id)
            blocked = seat.bookings.filter(status=Booking.CONFIRMED).exclude(order=order).exists()
            held_by_other = (
                seat.status == Seat.RESERVED
                and seat.reserved_by_id not in (None, order.user_id)
            )
            if blocked or held_by_other or (seat.status == Seat.BOOKED and not seat.bookings.filter(order=order).exists()):
                order.status = Order.NEEDS_REFUND
                order.failure_reason = 'Payment captured after the seat hold expired.'
                order.provider = provider
                order.provider_order_id = provider_order_id or order.provider_order_id
                order.save()
                Refund.objects.get_or_create(
                    order=order,
                    status=Refund.PENDING,
                    defaults={'amount': order.amount, 'reason': order.failure_reason},
                )
                if existing is None:
                    Payment.objects.create(
                        order=order,
                        provider=provider,
                        provider_order_id=provider_order_id or '',
                        provider_payment_id=provider_payment_id,
                        status=Payment.CAPTURED,
                        amount=order.amount,
                    )
                return order
            seats.append(seat)

        if not seats:
            order.status = Order.NEEDS_REFUND
            order.failure_reason = 'Payment captured after the seat hold expired.'
            order.save()
            Refund.objects.get_or_create(
                order=order,
                status=Refund.PENDING,
                defaults={'amount': order.amount, 'reason': order.failure_reason},
            )
            return order

        if existing is None:
            try:
                Payment.objects.create(
                    order=order,
                    provider=provider,
                    provider_order_id=provider_order_id or '',
                    provider_payment_id=provider_payment_id,
                    status=Payment.CAPTURED,
                    amount=order.amount,
                )
            except IntegrityError:
                return Order.objects.get(pk=order.pk)
        else:
            existing.status = Payment.CAPTURED
            existing.provider_order_id = provider_order_id or existing.provider_order_id
            existing.save(update_fields=['status', 'provider_order_id'])

        for seat in seats:
            price = seat.price if seat.price is not None else order.theater.ticket_price
            Booking.objects.create(
                user=order.user,
                seat=seat,
                movie=order.movie,
                theater=order.theater,
                order=order,
                status=Booking.CONFIRMED,
                booking_code=make_code('BK'),
                amount=price,
            )
            seat.status = Seat.BOOKED
            seat.is_booked = True
            seat.reserved_by = None
            seat.reserved_until = None
            seat.save(update_fields=['status', 'is_booked', 'reserved_by', 'reserved_until'])

        order.holds.all().delete()
        order.status = Order.PAID
        order.provider = provider
        if provider_order_id:
            order.provider_order_id = provider_order_id
        order.paid_at = timezone.now()
        order.failure_reason = ''
        order.save()
        Movie.objects.filter(pk=order.movie_id).update(popularity=F('popularity') + len(seats))
        paid_now = True

    if paid_now:
        enqueue_ticket_email(order.id)
    return order


def mark_payment_failed(order, provider, provider_payment_id, reason, provider_order_id=''):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == Order.PAID:
            return order
        if provider_payment_id and not Payment.objects.filter(provider_payment_id=provider_payment_id).exists():
            Payment.objects.create(
                order=order,
                provider=provider,
                provider_order_id=provider_order_id or order.provider_order_id,
                provider_payment_id=provider_payment_id,
                status=Payment.FAILED,
                amount=order.amount,
            )
    return release_order(order, Order.FAILED, reason or 'Payment failed')


def cancel_paid_order(order, user):
    if order.user_id != user.id and not user.is_staff:
        raise SeatUnavailable('You cannot cancel this booking.')
    with transaction.atomic():
        order = Order.objects.select_for_update().select_related('theater').get(pk=order.pk)
        if order.status != Order.PAID:
            raise SeatUnavailable('Only a paid booking can be cancelled.')
        if order.theater.time <= timezone.now():
            raise SeatUnavailable('This show has already started.')
        bookings = list(order.bookings.select_for_update().filter(status=Booking.CONFIRMED))
        for booking in bookings:
            booking.status = Booking.CANCELLED
            booking.save(update_fields=['status'])
            Seat.objects.filter(pk=booking.seat_id).update(
                status=Seat.AVAILABLE,
                is_booked=False,
                reserved_by=None,
                reserved_until=None,
            )
        order.status = Order.CANCELLED
        order.save(update_fields=['status'])
        Refund.objects.create(
            order=order,
            amount=order.amount,
            status=Refund.PENDING,
            reason='Cancelled by customer',
        )
        return order


def recompute_movie_rating(movie_id):
    from django.db.models import Avg, Count

    stats = Review.objects.filter(movie_id=movie_id, is_hidden=False).aggregate(
        avg=Avg('score'),
        total=Count('id'),
    )
    Movie.objects.filter(pk=movie_id).update(
        average_rating=stats['avg'] or 0,
        review_count=stats['total'] or 0,
    )


def user_can_review(user, movie):
    if not user.is_authenticated:
        return False
    return Booking.objects.filter(
        user=user,
        movie=movie,
        status=Booking.CONFIRMED,
        theater__time__lte=timezone.now(),
    ).exists()


def enqueue_ticket_email(order_id):
    delivery = EmailDelivery.objects.create(
        order_id=order_id,
        status=EmailDelivery.QUEUED,
        next_retry_at=timezone.now(),
    )

    def _kick():
        if not getattr(settings, 'CELERY_BROKER_URL', ''):
            return
        try:
            from .tasks import send_ticket_email
            send_ticket_email.delay(delivery.id)
        except Exception:
            logger.warning('Could not enqueue ticket email %s', delivery.id, exc_info=True)

    transaction.on_commit(lambda: threading.Thread(target=_kick, daemon=True).start())
    return delivery


def deliver_ticket_email(delivery_id):
    with transaction.atomic():
        delivery = EmailDelivery.objects.select_for_update().select_related(
            'order__user', 'order__movie', 'order__theater'
        ).get(pk=delivery_id)
        if delivery.status == EmailDelivery.SENT:
            return delivery
        if delivery.attempts >= 5:
            delivery.status = EmailDelivery.FAILED
            delivery.save(update_fields=['status'])
            return delivery
        delivery.attempts += 1
        delivery.status = EmailDelivery.SENDING
        delivery.save(update_fields=['attempts', 'status'])
        order = delivery.order
        attempt = delivery.attempts

    recipient = (order.user.email or '').strip()
    if not recipient:
        EmailDelivery.objects.filter(pk=delivery_id).update(
            status=EmailDelivery.FAILED,
            attempts=5,
            last_error='User has no email address.',
        )
        return

    try:
        pdf = render_ticket_pdf(order)
        message = EmailMessage(
            subject=f'Your tickets for {order.movie.name}',
            body=(
                f'Booking {order.reference} is confirmed for {order.movie.name} '
                f'at {order.theater.name}. Your PDF ticket is attached.'
            ),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None) or None,
            to=[recipient],
        )
        message.attach(f'ticket-{order.reference}.pdf', pdf, 'application/pdf')
        message.send(fail_silently=False)
    except Exception as exc:
        EmailDelivery.objects.filter(pk=delivery_id).update(
            status=EmailDelivery.FAILED,
            last_error=str(exc)[:500],
            next_retry_at=timezone.now() + timedelta(minutes=2 ** min(attempt, 5)),
        )
        raise

    EmailDelivery.objects.filter(pk=delivery_id).update(
        status=EmailDelivery.SENT,
        sent_at=timezone.now(),
        last_error='',
    )


def process_background_jobs():
    released = release_expired_holds()
    now = timezone.now()
    delivery_ids = list(
        EmailDelivery.objects.filter(
            status__in=[EmailDelivery.QUEUED, EmailDelivery.FAILED],
            attempts__lt=5,
            next_retry_at__lte=now,
        ).order_by('id').values_list('id', flat=True)[:15]
    )
    sent = 0
    failed = 0
    for delivery_id in delivery_ids:
        try:
            deliver_ticket_email(delivery_id)
            sent += 1
        except Exception:
            logger.exception('Ticket email %s failed', delivery_id)
            failed += 1
    return {'released_orders': released, 'emails_processed': sent, 'emails_failed': failed}


def seat_map(theater, user):
    release_expired_holds()
    now = timezone.now()
    payload = []
    hold_expires = None
    seats = Seat.objects.filter(theater=theater).order_by('seat_number', 'id')
    for seat in seats:
        status = 'available'
        if seat.status == Seat.BOOKED or seat.is_booked:
            status = 'booked'
        elif seat.status == Seat.RESERVED and seat.reserved_until and seat.reserved_until > now:
            if getattr(user, 'is_authenticated', False) and seat.reserved_by_id == user.id:
                status = 'mine'
                hold_expires = seat.reserved_until
            else:
                status = 'reserved'
        payload.append({
            'id': seat.id,
            'number': seat.seat_number,
            'status': status,
            'price': str(seat.price if seat.price is not None else theater.ticket_price),
        })
    return {
        'seats': payload,
        'hold_expires_at': hold_expires.isoformat() if hold_expires else None,
    }
