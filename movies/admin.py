from django.contrib import admin
from .models import (
    Booking, CastMember, City, EmailDelivery, Genre, Language, Movie, MovieCast,
    MoviePoster, Order, Payment, Refund, Review, ReviewReport, Seat, SeatHold, Theater,
)


class MovieCastInline(admin.TabularInline):
    model = MovieCast
    extra = 1


class MoviePosterInline(admin.TabularInline):
    model = MoviePoster
    extra = 1


class SeatInline(admin.TabularInline):
    model = Seat
    extra = 0
    fields = ('seat_number', 'status', 'is_booked', 'price', 'reserved_until')


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['name', 'rating', 'average_rating', 'review_count', 'age_certification', 'release_date', 'popularity']
    search_fields = ['name', 'cast']
    list_filter = ['age_certification', 'genres', 'languages', 'release_date']
    filter_horizontal = ['genres', 'languages']
    inlines = [MovieCastInline, MoviePosterInline]


@admin.register(Theater)
class TheaterAdmin(admin.ModelAdmin):
    list_display = ['name', 'movie', 'city', 'screen', 'language', 'time', 'ticket_price']
    list_filter = ['city', 'language']
    search_fields = ['name', 'movie__name']
    inlines = [SeatInline]


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ['theater', 'seat_number', 'status', 'is_booked', 'reserved_until']
    list_filter = ['status', 'is_booked']
    search_fields = ['seat_number', 'theater__name']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['user', 'seat', 'movie', 'theater', 'status', 'amount', 'booked_at']
    list_filter = ['status', 'booked_at']
    search_fields = ['user__username', 'booking_code', 'movie__name']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['reference', 'user', 'movie', 'status', 'amount', 'provider', 'created_at']
    list_filter = ['status', 'provider']
    search_fields = ['reference', 'provider_order_id', 'user__username']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['provider_payment_id', 'order', 'provider', 'status', 'amount', 'created_at']
    list_filter = ['provider', 'status']
    search_fields = ['provider_payment_id', 'provider_order_id']


admin.site.register(Genre)
admin.site.register(Language)
admin.site.register(City)
admin.site.register(CastMember)
admin.site.register(Refund)
admin.site.register(Review)
admin.site.register(ReviewReport)
admin.site.register(SeatHold)
admin.site.register(EmailDelivery)
