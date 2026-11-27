from io import BytesIO

import qrcode
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .models import Payment


def _qr_png(payload):
    image = qrcode.make(payload)
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer


def render_ticket_pdf(order):
    bookings = list(
        order.bookings.select_related('seat').filter(status='confirmed').order_by('seat__seat_number')
    )
    payment = order.payments.filter(status=Payment.CAPTURED).order_by('-id').first()
    payment_ref = payment.provider_payment_id if payment else ''
    seats = ', '.join(booking.seat.seat_number for booking in bookings) or '—'
    qr_payload = f'BMS|{order.reference}|{payment_ref}'
    return _draw_ticket(
        title=order.movie.name,
        reference=order.reference,
        theater=order.theater.name,
        screen=order.theater.screen or 'Screen 1',
        when=order.theater.time.strftime('%d %b %Y, %H:%M UTC'),
        seats=seats,
        amount=f'{order.currency} {order.amount}',
        payment_ref=payment_ref or '—',
        certification=order.movie.age_certification or '',
        qr_payload=qr_payload,
        guest=order.user.get_full_name() or order.user.username,
    )


def render_legacy_ticket_pdf(booking):
    return _draw_ticket(
        title=booking.movie.name,
        reference=booking.booking_code or f'BK{booking.pk}',
        theater=booking.theater.name,
        screen=booking.theater.screen or 'Screen 1',
        when=booking.theater.time.strftime('%d %b %Y, %H:%M UTC'),
        seats=booking.seat.seat_number,
        amount=f'INR {booking.amount}' if booking.amount else '—',
        payment_ref='—',
        certification=booking.movie.age_certification or '',
        qr_payload=f'BMS|{booking.booking_code or booking.pk}|LEGACY',
        guest=booking.user.get_full_name() or booking.user.username,
    )


def _draw_ticket(title, reference, theater, screen, when, seats, amount, payment_ref, certification, qr_payload, guest):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A5)
    width, height = A5

    pdf.setFillColorRGB(0.09, 0.09, 0.12)
    pdf.rect(0, height - 28 * mm, width, 28 * mm, fill=1, stroke=0)
    pdf.setFillColorRGB(0.96, 0.78, 0.32)
    pdf.setFont('Times-Bold', 16)
    pdf.drawString(12 * mm, height - 12 * mm, 'BOOKMYSEAT')
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont('Times-Roman', 10)
    pdf.drawString(12 * mm, height - 19 * mm, 'Admit one · show this QR at the cinema')

    pdf.setFillColorRGB(0.1, 0.1, 0.12)
    pdf.setFont('Times-Bold', 14)
    y = height - 40 * mm
    pdf.drawString(12 * mm, y, title[:42])
    pdf.setFont('Times-Roman', 10)
    y -= 8 * mm
    if certification:
        pdf.drawString(12 * mm, y, f'Certification {certification}')
        y -= 7 * mm

    rows = [
        ('Guest', guest),
        ('Booking ID', reference),
        ('Theatre', theater),
        ('Screen', screen),
        ('Show time', when),
        ('Seats', seats),
        ('Amount', amount),
        ('Payment reference', payment_ref),
    ]
    for label, value in rows:
        pdf.setFillColorRGB(0.4, 0.4, 0.45)
        pdf.setFont('Times-Roman', 8)
        pdf.drawString(12 * mm, y, label.upper())
        y -= 5 * mm
        pdf.setFillColorRGB(0.1, 0.1, 0.12)
        pdf.setFont('Times-Bold', 11)
        pdf.drawString(12 * mm, y, str(value)[:48])
        y -= 8 * mm

    qr_buffer = _qr_png(qr_payload)
    pdf.drawImage(ImageReader(qr_buffer), width - 48 * mm, 16 * mm, 34 * mm, 34 * mm, mask='auto')
    pdf.setFillColorRGB(0.35, 0.35, 0.4)
    pdf.setFont('Times-Roman', 8)
    pdf.drawString(12 * mm, 14 * mm, 'Seats are confirmed only after payment verification.')
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
