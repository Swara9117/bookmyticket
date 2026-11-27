"""Dashboard aggregates.

Performance notes for a table of 100,000+ bookings
--------------------------------------------------
Every figure on the dashboard is a SQL aggregate. Booking rows are not loaded
into Python.

Indexes that make those aggregates index range scans instead of full table reads:

* booking_status_time_idx (status, booked_at)
  Revenue, trends, peak hours and the CSV export all filter confirmed or
  cancelled bookings inside a datetime window. The planner can walk this
  composite index and aggregate in the database.
* booking_movie_status_idx / booking_theater_status_idx
  "Most booked movies" and "top theatres" group by a foreign key after
  filtering status, without scanning unrelated bookings.
* booking_user_time_idx
  Profile history and per-user recommendation seeds stay on the user's slice.
* seat_theater_status_idx
  Occupancy is COUNT per theatre with a FILTER on booked seats.
* order_status_created_idx and payment_status_time_idx
  Payment history and refund totals use the same pattern.

Daily, weekly, monthly and yearly revenue are one conditional SUM, not four
queries that each pull rows. Trunc/Extract bucketing (hour, day, week, month,
year) returns one row per bucket. CSV export uses queryset.iterator so rows
are streamed in chunks of 2,000.
"""
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.db.models import Count, F, FloatField, OuterRef, Q, Subquery, Sum
from django.db.models.expressions import ExpressionWrapper
from django.db.models.functions import ExtractHour, TruncDate, TruncMonth, TruncWeek, TruncYear
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import Booking, Payment, Refund, Seat


def _aware(day, end=False):
    clock = time.max if end else time.min
    naive = datetime.combine(day, clock)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def resolve_range(params):
    today = timezone.localdate()
    start = parse_date(params.get('start') or '') or (today - timedelta(days=30))
    end = parse_date(params.get('end') or '') or today
    if end < start:
        start, end = end, start
    return start, end, _aware(start), _aware(end, end=True)


def dashboard_context(params):
    start_date, end_date, start_dt, end_dt = resolve_range(params)
    confirmed = Booking.objects.filter(status=Booking.CONFIRMED, booked_at__gte=start_dt, booked_at__lte=end_dt)
    cancelled = Booking.objects.filter(status=Booking.CANCELLED, booked_at__gte=start_dt, booked_at__lte=end_dt)

    now = timezone.localtime()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())
    month_start = day_start.replace(day=1)
    year_start = day_start.replace(month=1, day=1)
    period_revenue = Booking.objects.filter(status=Booking.CONFIRMED).aggregate(
        today=Sum('amount', filter=Q(booked_at__gte=day_start)),
        week=Sum('amount', filter=Q(booked_at__gte=week_start)),
        month=Sum('amount', filter=Q(booked_at__gte=month_start)),
        year=Sum('amount', filter=Q(booked_at__gte=year_start)),
    )

    range_totals = confirmed.aggregate(revenue=Sum('amount'), bookings=Count('id'))
    cancel_totals = cancelled.aggregate(bookings=Count('id'))
    refunds = Refund.objects.filter(created_at__gte=start_dt, created_at__lte=end_dt).aggregate(
        count=Count('id'),
        amount=Sum('amount'),
        pending=Count('id', filter=Q(status=Refund.PENDING)),
    )
    new_users = User.objects.filter(date_joined__gte=start_dt, date_joined__lte=end_dt).count()

    daily = list(
        confirmed.annotate(bucket=TruncDate('booked_at'))
        .values('bucket')
        .annotate(total=Count('id'), revenue=Sum('amount'))
        .order_by('bucket')
    )
    weekly = list(
        confirmed.annotate(bucket=TruncWeek('booked_at'))
        .values('bucket')
        .annotate(total=Count('id'), revenue=Sum('amount'))
        .order_by('bucket')
    )
    monthly = list(
        confirmed.annotate(bucket=TruncMonth('booked_at'))
        .values('bucket')
        .annotate(total=Count('id'), revenue=Sum('amount'))
        .order_by('bucket')
    )
    yearly = list(
        confirmed.annotate(bucket=TruncYear('booked_at'))
        .values('bucket')
        .annotate(total=Count('id'), revenue=Sum('amount'))
        .order_by('bucket')
    )
    peak_hours = list(
        confirmed.annotate(hour=ExtractHour('booked_at'))
        .values('hour')
        .annotate(total=Count('id'))
        .order_by('-total')[:8]
    )
    top_movies = list(
        confirmed.values('movie__name')
        .annotate(total=Count('id'), revenue=Sum('amount'))
        .order_by('-total')[:8]
    )
    top_theaters = list(
        confirmed.values('theater__name')
        .annotate(total=Count('id'), revenue=Sum('amount'))
        .order_by('-revenue')[:8]
    )
    occupancy = list(
        Seat.objects.values('theater_id', 'theater__name', 'theater__movie__name')
        .annotate(
            total=Count('id'),
            booked=Count('id', filter=Q(status=Seat.BOOKED) | Q(is_booked=True)),
        )
        .annotate(
            occupancy=ExpressionWrapper(
                100.0 * F('booked') / F('total'),
                output_field=FloatField(),
            )
        )
        .order_by('-occupancy')[:20]
    )
    user_growth = list(
        User.objects.filter(date_joined__gte=start_dt, date_joined__lte=end_dt)
        .annotate(bucket=TruncDate('date_joined'))
        .values('bucket')
        .annotate(total=Count('id'))
        .order_by('bucket')
    )
    peak_daily = max((row['total'] for row in daily), default=1) or 1

    return {
        'start': start_date,
        'end': end_date,
        'period_revenue': period_revenue,
        'range_revenue': range_totals['revenue'] or 0,
        'range_bookings': range_totals['bookings'] or 0,
        'cancellations': cancel_totals['bookings'] or 0,
        'refunds': refunds,
        'new_users': new_users,
        'daily': daily,
        'weekly': weekly,
        'monthly': monthly,
        'yearly': yearly,
        'peak_hours': peak_hours,
        'top_movies': top_movies,
        'top_theaters': top_theaters,
        'occupancy': occupancy,
        'user_growth': user_growth,
        'peak_daily': peak_daily,
        'performance_notes': __doc__,
    }


def booking_export_queryset(params):
    _, _, start_dt, end_dt = resolve_range(params)
    payment_ref = Payment.objects.filter(
        order_id=OuterRef('order_id'),
        status=Payment.CAPTURED,
    ).order_by('-id').values('provider_payment_id')[:1]
    return (
        Booking.objects.filter(booked_at__gte=start_dt, booked_at__lte=end_dt)
        .annotate(payment_ref=Subquery(payment_ref))
        .order_by('booked_at', 'id')
        .values_list(
            'id',
            'booking_code',
            'order__reference',
            'user__username',
            'movie__name',
            'theater__name',
            'seat__seat_number',
            'amount',
            'status',
            'booked_at',
            'payment_ref',
        )
    )
