import csv
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages

from .analytics import booking_export_queryset, dashboard_context
from .discovery import filter_movies, sort_movies
from .embeds import youtube_embed_url
from .forms import ReviewForm
from .models import (
    Booking,
    City,
    Genre,
    Language,
    Movie,
    MovieView,
    Order,
    Review,
    ReviewReport,
    Theater,
)
from .payments import (
    PaymentError,
    active_provider,
    handle_razorpay_webhook,
    handle_stripe_event,
    start_checkout,
    verify_razorpay_payment,
    verify_stripe_session,
)
from .recommendations import recent_releases, recommended_for_user, similar_movies, trending_movies
from .services import (
    SeatUnavailable,
    cancel_paid_order,
    process_background_jobs,
    recompute_movie_rating,
    release_order,
    reserve_seats,
    seat_map,
    user_can_review,
)
from .tickets import render_legacy_ticket_pdf, render_ticket_pdf


def _staff_analytics(view):
    @login_required(login_url='/login/')
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        allowed = user.is_staff and (user.is_superuser or user.has_perm('movies.view_booking'))
        if not allowed:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def movie_list(request):
    filtered = filter_movies(request.GET)
    ordered = sort_movies(filtered, request.GET.get('sort'))
    page_obj = Paginator(ordered, 12).get_page(request.GET.get('page'))
    page_obj.object_list = page_obj.object_list.prefetch_related('genres', 'languages')
    query = request.GET.copy()
    query.pop('page', None)
    return render(request, 'movies/movie_list.html', {
        'page_obj': page_obj,
        'movies': page_obj.object_list,
        'match_count': page_obj.paginator.count,
        'filters_query': query.urlencode(),
        'genres': Genre.objects.all(),
        'languages': Language.objects.all(),
        'cities': City.objects.all(),
        'sort': request.GET.get('sort') or 'popularity',
        'theater_names': Theater.objects.order_by('name').values_list('name', flat=True).distinct(),
        'recommended': recommended_for_user(request.user, 4),
    })


def match_count(request):
    return JsonResponse({'count': filter_movies(request.GET).count()})


def movie_detail(request, movie_id):
    movie = get_object_or_404(
        Movie.objects.prefetch_related('genres', 'languages', 'posters', 'cast_roles__member'),
        id=movie_id,
    )
    if request.user.is_authenticated:
        MovieView.objects.update_or_create(user=request.user, movie=movie)
    reviews = (
        movie.reviews.filter(is_hidden=False)
        .select_related('user')
        .order_by('-created_at')
    )
    can_review = user_can_review(request.user, movie)
    own_review = None
    if request.user.is_authenticated:
        own_review = Review.objects.filter(user=request.user, movie=movie).first()
    return render(request, 'movies/movie_detail.html', {
        'movie': movie,
        'embed_url': youtube_embed_url(movie.trailer_url),
        'reviews': reviews,
        'can_review': can_review and own_review is None,
        'own_review': own_review,
        'review_form': ReviewForm(),
        'similar': similar_movies(movie),
        'trending': trending_movies(4),
        'new_releases': recent_releases(4),
        'recommended': recommended_for_user(request.user, 4),
    })


def theater_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    theaters = Theater.objects.filter(movie=movie).select_related('city', 'language').order_by('time')
    return render(request, 'movies/theater_list.html', {'movie': movie, 'theaters': theaters})


@login_required(login_url='/login/')
def book_seats(request, theater_id):
    theater = get_object_or_404(Theater.objects.select_related('movie'), id=theater_id)
    if request.method == 'POST':
        selected = request.POST.getlist('seats')
        if not selected:
            messages.error(request, 'No seat selected.')
            return redirect('book_seats', theater_id=theater.id)
        try:
            order = reserve_seats(request.user, theater, selected)
        except (SeatUnavailable, ValueError) as exc:
            messages.error(request, str(exc))
            return redirect('book_seats', theater_id=theater.id)
        return redirect('checkout', reference=order.reference)

    state = seat_map(theater, request.user)
    status_by_id = {row['id']: row['status'] for row in state['seats']}
    seats = list(theater.seats.order_by('seat_number', 'id'))
    for seat in seats:
        seat.live_status = status_by_id.get(seat.id, 'available')
    return render(request, 'movies/seat_selection.html', {
        'theaters': theater,
        'theater': theater,
        'seats': seats,
        'hold_expires_at': state['hold_expires_at'],
    })


@login_required(login_url='/login/')
def seat_status(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)
    return JsonResponse(seat_map(theater, request.user))


def _user_order(request, reference):
    return get_object_or_404(
        Order.objects.select_related('movie', 'theater', 'user'),
        reference=reference,
        user=request.user,
    )


@login_required(login_url='/login/')
def checkout(request, reference):
    order = _user_order(request, reference)
    holds = order.holds.select_related('seat').order_by('seat__seat_number')
    if order.status == Order.PENDING and order.expires_at <= timezone.now():
        release_order(order, Order.EXPIRED, 'Hold expired')
        order.refresh_from_db()
        messages.error(request, 'Your seat hold expired. Choose the seats again.')
    if request.GET.get('cancelled'):
        messages.info(request, 'Payment was cancelled. Your seats stay held until the timer ends, so you can try again.')
    provider = active_provider()
    return render(request, 'movies/checkout.html', {
        'order': order,
        'holds': holds,
        'provider': provider,
        'razorpay_key': '',
        'seconds_left': max(0, int((order.expires_at - timezone.now()).total_seconds())) if order.status == Order.PENDING else 0,
    })


@login_required(login_url='/login/')
@require_POST
def start_payment(request, reference):
    order = _user_order(request, reference)
    if order.status != Order.PENDING:
        messages.error(request, 'This booking is no longer waiting for payment.')
        return redirect('checkout', reference=order.reference)
    if order.expires_at <= timezone.now():
        release_order(order, Order.EXPIRED, 'Hold expired')
        messages.error(request, 'Your seat hold expired. Choose the seats again.')
        return redirect('book_seats', theater_id=order.theater_id)
    try:
        payload = start_checkout(order, request)
    except PaymentError as exc:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect('checkout', reference=order.reference)
    if payload.get('redirect'):
        return redirect(payload['redirect'])
    return JsonResponse(payload)


@login_required(login_url='/login/')
def payment_return(request, reference):
    order = _user_order(request, reference)
    session_id = request.GET.get('session_id', '')
    if not session_id:
        messages.error(request, 'Missing payment session.')
        return redirect('checkout', reference=order.reference)
    try:
        verify_stripe_session(order, session_id)
    except PaymentError as exc:
        messages.error(request, str(exc))
        return redirect('checkout', reference=order.reference)
    order.refresh_from_db()
    if order.status == Order.PAID:
        messages.success(request, 'Payment confirmed. Your ticket is ready to download.')
        return redirect('profile')
    if order.status == Order.NEEDS_REFUND:
        messages.error(request, 'Payment was received after the seats were released. A refund has been queued.')
    else:
        messages.error(request, 'Payment could not be confirmed.')
    return redirect('profile')


@login_required(login_url='/login/')
@require_POST
def razorpay_verify(request, reference):
    order = _user_order(request, reference)
    try:
        verify_razorpay_payment(
            order,
            request.POST.get('razorpay_order_id', ''),
            request.POST.get('razorpay_payment_id', ''),
            request.POST.get('razorpay_signature', ''),
        )
    except PaymentError as exc:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect('checkout', reference=order.reference)
    order.refresh_from_db()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': order.status == Order.PAID, 'status': order.status})
    messages.success(request, 'Payment confirmed. Your ticket is ready to download.')
    return redirect('profile')


@csrf_exempt
@require_POST
def stripe_webhook(request):
    try:
        handle_stripe_event(request.body, request.headers.get('Stripe-Signature', ''))
    except Exception as exc:
        return HttpResponse(str(exc), status=400)
    return HttpResponse(status=200)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    try:
        handle_razorpay_webhook(request.body, request.headers.get('X-Razorpay-Signature', ''))
    except Exception as exc:
        return HttpResponse(str(exc), status=400)
    return HttpResponse(status=200)


@login_required(login_url='/login/')
@require_POST
def cancel_checkout(request, reference):
    order = _user_order(request, reference)
    if order.status == Order.PENDING:
        release_order(order, Order.CANCELLED, 'Cancelled before payment')
        messages.info(request, 'Seat hold released.')
    return redirect('movie_detail', movie_id=order.movie_id)


@login_required(login_url='/login/')
@require_POST
def cancel_order(request, reference):
    order = _user_order(request, reference)
    try:
        cancel_paid_order(order, request.user)
    except SeatUnavailable as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, 'Booking cancelled. A refund has been recorded for the admin team.')
    return redirect('profile')


@login_required(login_url='/login/')
def download_ticket(request, reference):
    order = _user_order(request, reference)
    if order.status != Order.PAID:
        messages.error(request, 'A ticket is available after payment is confirmed.')
        return redirect('profile')
    pdf = render_ticket_pdf(order)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="ticket-{order.reference}.pdf"'
    return response


@login_required(login_url='/login/')
def download_legacy_ticket(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related('movie', 'theater', 'seat', 'user'),
        pk=booking_id,
        user=request.user,
    )
    pdf = render_legacy_ticket_pdf(booking)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="ticket-{booking.pk}.pdf"'
    return response


@login_required(login_url='/login/')
@require_POST
def submit_review(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    if not user_can_review(request.user, movie):
        messages.error(request, 'You can review a movie after you have booked it and the show has started.')
        return redirect('movie_detail', movie_id=movie.id)
    if Review.objects.filter(user=request.user, movie=movie).exists():
        messages.error(request, 'You already reviewed this movie. You can edit that review.')
        return redirect('movie_detail', movie_id=movie.id)
    form = ReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Check the rating and review text.')
        return redirect('movie_detail', movie_id=movie.id)
    form.instance.user = request.user
    form.instance.movie = movie
    form.save()
    recompute_movie_rating(movie.id)
    messages.success(request, 'Thanks. Your verified review is live.')
    return redirect('movie_detail', movie_id=movie.id)


@login_required(login_url='/login/')
def edit_review(request, review_id):
    review = get_object_or_404(Review, pk=review_id, user=request.user)
    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            recompute_movie_rating(review.movie_id)
            messages.success(request, 'Review updated.')
            return redirect('movie_detail', movie_id=review.movie_id)
    else:
        form = ReviewForm(instance=review)
    return render(request, 'movies/review_edit.html', {'form': form, 'review': review})


@login_required(login_url='/login/')
@require_POST
def report_review(request, review_id):
    review = get_object_or_404(Review, pk=review_id)
    reason = (request.POST.get('reason') or '').strip()
    if not reason:
        messages.error(request, 'Add a short reason for the report.')
        return redirect('movie_detail', movie_id=review.movie_id)
    _, created = ReviewReport.objects.get_or_create(
        review=review,
        user=request.user,
        defaults={'reason': reason[:300]},
    )
    if created and review.reports.count() >= 3:
        review.is_hidden = True
        review.save(update_fields=['is_hidden'])
        recompute_movie_rating(review.movie_id)
    messages.success(request, 'Report submitted. Moderators can see it in the admin.')
    return redirect('movie_detail', movie_id=review.movie_id)


@_staff_analytics
def dashboard(request):
    return render(request, 'movies/dashboard.html', dashboard_context(request.GET))


@_staff_analytics
def export_dashboard(request):
    class Echo:
        def write(self, value):
            return value

    writer = csv.writer(Echo())
    header = [
        'booking_id', 'booking_code', 'order_reference', 'username', 'movie',
        'theater', 'seat', 'amount', 'status', 'booked_at', 'payment_reference',
    ]

    def rows():
        yield writer.writerow(header)
        for row in booking_export_queryset(request.GET).iterator(chunk_size=2000):
            yield writer.writerow(row)

    response = StreamingHttpResponse(rows(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="bookings.csv"'
    return response


def run_jobs(request):
    from django.conf import settings as django_settings
    secret = getattr(django_settings, 'CRON_SECRET', '')
    if not secret or request.headers.get('Authorization', '') != f'Bearer {secret}':
        return HttpResponse(status=403)
    return JsonResponse(process_background_jobs())
