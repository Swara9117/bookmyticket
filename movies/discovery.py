from datetime import datetime

from django.db.models import Exists, F, Min, OuterRef, Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time

from .models import Language, Movie, Theater


def _positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def filter_movies(params):
    """Apply discovery filters with joins that do not multiply movie rows.

    Relational filters use EXISTS so a movie with many shows is counted once.
    Title search stays on the indexed name column.
    """
    qs = Movie.objects.all()
    search = (params.get('search') or '').strip()
    if search:
        qs = qs.filter(name__icontains=search)

    genre_id = _positive_int(params.get('genre'))
    if genre_id:
        qs = qs.filter(Exists(
            Movie.genres.through.objects.filter(movie_id=OuterRef('pk'), genre_id=genre_id)
        ))

    language_id = _positive_int(params.get('language'))
    if language_id:
        on_movie = Language.objects.filter(pk=language_id, movies__id=OuterRef('pk'))
        on_show = Theater.objects.filter(movie_id=OuterRef('pk'), language_id=language_id)
        qs = qs.filter(Exists(on_movie) | Exists(on_show))

    shows = Theater.objects.filter(movie_id=OuterRef('pk'))
    city_id = _positive_int(params.get('city'))
    if city_id:
        shows = shows.filter(city_id=city_id)
        qs = qs.filter(Exists(shows))

    theater_name = (params.get('theater') or '').strip()
    if theater_name:
        qs = qs.filter(Exists(
            Theater.objects.filter(movie_id=OuterRef('pk'), name__icontains=theater_name)
        ))

    release_from = parse_date(params.get('release_from') or '')
    release_to = parse_date(params.get('release_to') or '')
    if release_from:
        qs = qs.filter(release_date__gte=release_from)
    if release_to:
        qs = qs.filter(release_date__lte=release_to)

    rating = params.get('rating')
    if rating not in (None, ''):
        try:
            minimum = float(rating)
        except (TypeError, ValueError):
            minimum = None
        if minimum is not None:
            qs = qs.filter(
                Q(review_count__gt=0, average_rating__gte=minimum)
                | Q(review_count=0, rating__gte=minimum)
            )

    show_date = parse_date(params.get('show_date') or '')
    show_from = parse_time(params.get('show_from') or '')
    show_to = parse_time(params.get('show_to') or '')
    if show_date or show_from or show_to:
        timed = Theater.objects.filter(movie_id=OuterRef('pk'))
        if city_id:
            timed = timed.filter(city_id=city_id)
        if theater_name:
            timed = timed.filter(name__icontains=theater_name)
        if show_date:
            start, end = _day_bounds(show_date)
            timed = timed.filter(time__gte=start, time__lte=end)
        if show_from:
            timed = timed.filter(time__time__gte=show_from)
        if show_to:
            timed = timed.filter(time__time__lte=show_to)
        qs = qs.filter(Exists(timed))
    elif city_id:
        pass

    return qs


def _day_bounds(day):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()), tz)
    end = timezone.make_aware(datetime.combine(day, datetime.max.time()), tz)
    return start, end


def sort_movies(qs, sort_key):
    sort_key = sort_key or 'popularity'
    if sort_key == 'newest':
        return qs.order_by(F('release_date').desc(nulls_last=True), '-popularity', '-id')
    if sort_key == 'rating':
        return qs.order_by('-average_rating', '-rating', '-popularity')
    if sort_key == 'price':
        return qs.annotate(min_price=Min('theaters__ticket_price')).order_by(
            F('min_price').asc(nulls_last=True), 'name'
        )
    return qs.order_by('-popularity', '-id')
