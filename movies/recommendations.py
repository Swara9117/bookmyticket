from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import Booking, Genre, Movie, MovieView


def trending_movies(limit=8):
    since = timezone.now() - timedelta(days=7)
    return Movie.objects.annotate(
        recent_bookings=Count(
            'bookings',
            filter=Q(bookings__status=Booking.CONFIRMED, bookings__booked_at__gte=since),
        )
    ).order_by('-recent_bookings', '-popularity', '-id')[:limit]


def recent_releases(limit=8):
    return Movie.objects.exclude(release_date__isnull=True).order_by('-release_date', '-id')[:limit]


def similar_movies(movie, limit=6):
    genre_ids = movie.genres.values('id')
    language_ids = movie.languages.values('id')
    if not movie.genres.exists() and not movie.languages.exists():
        return Movie.objects.none()
    return (
        Movie.objects.filter(Q(genres__in=genre_ids) | Q(languages__in=language_ids))
        .exclude(pk=movie.pk)
        .distinct()
        .order_by('-popularity', '-id')[:limit]
    )


def recommended_for_user(user, limit=8):
    if user is None or not getattr(user, 'is_authenticated', False):
        return trending_movies(limit)

    booked_ids = Booking.objects.filter(user=user, status=Booking.CONFIRMED).values('movie_id')
    genre_ids = Genre.objects.filter(
        Q(movies__bookings__user=user, movies__bookings__status=Booking.CONFIRMED)
        | Q(movies__views__user=user)
    ).values('id').distinct()
    personalized = (
        Movie.objects.filter(genres__in=genre_ids)
        .exclude(id__in=booked_ids)
        .distinct()
        .order_by('-popularity', '-id')
    )
    if personalized.exists():
        return personalized[:limit]
    recent_ids = MovieView.objects.filter(user=user).order_by('-viewed_at').values_list('movie_id', flat=True)[:limit]
    recent = Movie.objects.filter(id__in=list(recent_ids)).exclude(id__in=booked_ids)
    if recent.exists():
        return recent
    return trending_movies(limit)


def for_home(user):
    return {
        'recommended': recommended_for_user(user),
        'trending': trending_movies(),
        'new_releases': recent_releases(),
    }
