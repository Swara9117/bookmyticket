import hashlib
import hmac
import logging
from decimal import Decimal

from django.conf import settings

from .models import Order
from .services import _to_paise, confirm_order, mark_payment_failed

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    pass


def active_provider():
    configured = (getattr(settings, 'PAYMENT_PROVIDER', '') or '').lower()
    if configured in ('stripe', 'razorpay'):
        return configured
    if getattr(settings, 'RAZORPAY_KEY_ID', '') and getattr(settings, 'RAZORPAY_KEY_SECRET', ''):
        return 'razorpay'
    if getattr(settings, 'STRIPE_SECRET_KEY', ''):
        return 'stripe'
    return ''


def _site(path):
    base = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
    return base + path


def start_checkout(order, request):
    provider = active_provider()
    if not provider:
        raise PaymentError('Add Stripe or Razorpay keys before taking payments.')
    if provider == 'stripe':
        return _start_stripe(order)
    return _start_razorpay(order)


def _start_stripe(order):
    import stripe

    secret = settings.STRIPE_SECRET_KEY
    if not secret:
        raise PaymentError('STRIPE_SECRET_KEY is not set.')
    stripe.api_key = secret
    paise = _to_paise(order.amount)
    if order.provider == 'stripe' and order.provider_order_id:
        existing = stripe.checkout.Session.retrieve(order.provider_order_id)
        if existing.status == 'open' and existing.amount_total == paise:
            return {'redirect': existing.url}

    session = stripe.checkout.Session.create(
        mode='payment',
        client_reference_id=order.reference,
        metadata={'order_reference': order.reference},
        line_items=[{
            'quantity': 1,
            'price_data': {
                'currency': order.currency.lower(),
                'unit_amount': paise,
                'product_data': {
                    'name': f'{order.movie.name} at {order.theater.name}',
                },
            },
        }],
        success_url=_site(f'/movies/checkout/{order.reference}/return/?session_id={{CHECKOUT_SESSION_ID}}'),
        cancel_url=_site(f'/movies/checkout/{order.reference}/?cancelled=1'),
    )
    order.provider = 'stripe'
    order.provider_order_id = session.id
    order.save(update_fields=['provider', 'provider_order_id'])
    return {'redirect': session.url}


def _start_razorpay(order):
    import razorpay

    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise PaymentError('Razorpay keys are not set.')
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    paise = _to_paise(order.amount)
    if not (order.provider == 'razorpay' and order.provider_order_id):
        created = client.order.create({
            'amount': paise,
            'currency': order.currency,
            'receipt': order.reference[:40],
            'payment_capture': 1,
            'notes': {'order_reference': order.reference},
        })
        order.provider = 'razorpay'
        order.provider_order_id = created['id']
        order.save(update_fields=['provider', 'provider_order_id'])
    return {
        'key_id': settings.RAZORPAY_KEY_ID,
        'order_id': order.provider_order_id,
        'amount': paise,
        'currency': order.currency,
        'name': 'BookMySeat',
        'description': f'{order.movie.name} · {order.reference}',
        'reference': order.reference,
    }


def verify_stripe_session(order, session_id):
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    session = stripe.checkout.Session.retrieve(session_id)
    reference = (session.metadata or {}).get('order_reference') or session.client_reference_id
    if reference != order.reference:
        raise PaymentError('This payment does not belong to the booking.')
    if session.payment_status != 'paid':
        raise PaymentError('Payment is not complete.')
    amount = Decimal(session.amount_total) / Decimal('100')
    payment_id = session.payment_intent
    if isinstance(payment_id, dict):
        payment_id = payment_id.get('id', '')
    return confirm_order(
        order,
        provider='stripe',
        provider_payment_id=str(payment_id),
        provider_order_id=session.id,
        amount=amount,
    )


def handle_stripe_event(payload, signature):
    import stripe

    if not settings.STRIPE_WEBHOOK_SECRET:
        raise PaymentError('STRIPE_WEBHOOK_SECRET is not set.')
    stripe.api_key = settings.STRIPE_SECRET_KEY
    event = stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
    data = event['data']['object']
    kind = event['type']

    if kind == 'checkout.session.completed' and data.get('payment_status') == 'paid':
        order = Order.objects.filter(reference=data.get('client_reference_id')).first()
        if order is None:
            reference = (data.get('metadata') or {}).get('order_reference')
            order = Order.objects.filter(reference=reference).first()
        if order is None:
            logger.warning('Stripe session had no matching order')
            return
        amount = Decimal(data.get('amount_total') or 0) / Decimal('100')
        confirm_order(
            order,
            provider='stripe',
            provider_payment_id=str(data.get('payment_intent') or data.get('id')),
            provider_order_id=data.get('id') or '',
            amount=amount,
            event_id=event['id'],
        )
        return

    if kind in ('checkout.session.expired', 'checkout.session.async_payment_failed', 'payment_intent.payment_failed'):
        reference = data.get('client_reference_id') or (data.get('metadata') or {}).get('order_reference')
        order = Order.objects.filter(reference=reference).first() if reference else None
        if order is None and data.get('id'):
            order = Order.objects.filter(provider_order_id=data.get('id')).first()
        if order is None:
            return
        payment_id = str(data.get('payment_intent') or data.get('id') or '')
        mark_payment_failed(
            order,
            provider='stripe',
            provider_payment_id=payment_id,
            provider_order_id=str(data.get('id') or ''),
            reason=kind,
        )


def verify_razorpay_payment(order, razorpay_order_id, razorpay_payment_id, signature):
    secret = settings.RAZORPAY_KEY_SECRET or ''
    if not secret:
        raise PaymentError('RAZORPAY_KEY_SECRET is not set.')
    if razorpay_order_id != order.provider_order_id:
        raise PaymentError('Payment does not match this booking.')
    signed = f'{razorpay_order_id}|{razorpay_payment_id}'.encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ''):
        raise PaymentError('Payment signature could not be verified.')
    import razorpay
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    remote = client.payment.fetch(razorpay_payment_id)
    if str(remote.get('order_id')) != razorpay_order_id:
        raise PaymentError('Payment does not match the Razorpay order.')
    if remote.get('status') not in ('captured', 'authorized'):
        raise PaymentError('Payment was not captured.')
    amount = Decimal(remote.get('amount') or 0) / Decimal('100')
    return confirm_order(
        order,
        provider='razorpay',
        provider_payment_id=razorpay_payment_id,
        provider_order_id=razorpay_order_id,
        amount=amount,
    )


def handle_razorpay_webhook(payload, signature):
    secret = settings.RAZORPAY_WEBHOOK_SECRET or ''
    if not secret:
        raise PaymentError('RAZORPAY_WEBHOOK_SECRET is not set.')
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ''):
        raise PaymentError('Invalid webhook signature.')
    import json
    event = json.loads(payload.decode('utf-8'))
    kind = event.get('event')
    entity = ((event.get('payload') or {}).get('payment') or {}).get('entity') or {}
    order = Order.objects.filter(provider_order_id=entity.get('order_id')).first()
    if order is None:
        reference = (entity.get('notes') or {}).get('order_reference')
        if reference:
            order = Order.objects.filter(reference=reference).first()
    if order is None:
        return
    payment_id = entity.get('id') or ''
    if kind == 'payment.captured':
        amount = Decimal(entity.get('amount') or 0) / Decimal('100')
        confirm_order(
            order,
            provider='razorpay',
            provider_payment_id=payment_id,
            provider_order_id=entity.get('order_id') or '',
            amount=amount,
            event_id=event.get('event') or '',
        )
        return
    if kind == 'payment.failed':
        mark_payment_failed(
            order,
            provider='razorpay',
            provider_payment_id=payment_id,
            provider_order_id=entity.get('order_id') or '',
            reason=entity.get('error_description') or 'payment.failed',
        )
