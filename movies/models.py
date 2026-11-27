from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User


class Genre(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class City(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        verbose_name_plural = 'cities'
        ordering = ['name']

    def __str__(self):
        return self.name


class CastMember(models.Model):
    name = models.CharField(max_length=120)
    photo = models.ImageField(upload_to='cast/', blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Movie(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    image = models.ImageField(upload_to='movies/')
    rating = models.DecimalField(max_digits=3, decimal_places=1)
    cast = models.TextField()
    description = models.TextField(blank=True, null=True)
    trailer_url = models.URLField(
        blank=True,
        default='',
        help_text='YouTube watch or share link. Only YouTube URLs are embedded.',
    )
    age_certification = models.CharField(max_length=10, blank=True, default='U')
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    release_date = models.DateField(null=True, blank=True, db_index=True)
    popularity = models.PositiveIntegerField(default=0, db_index=True)
    average_rating = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    review_count = models.PositiveIntegerField(default=0)
    genres = models.ManyToManyField(Genre, blank=True, related_name='movies')
    languages = models.ManyToManyField(Language, blank=True, related_name='movies')
    cast_members = models.ManyToManyField(
        CastMember, through='MovieCast', blank=True, related_name='movies'
    )

    class Meta:
        indexes = [
            models.Index(fields=['-popularity', '-id'], name='movie_popularity_idx'),
            models.Index(fields=['-release_date'], name='movie_release_idx'),
        ]

    def __str__(self):
        return self.name

    @property
    def display_rating(self):
        if self.review_count:
            return self.average_rating
        return self.rating


class MovieCast(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='cast_roles')
    member = models.ForeignKey(CastMember, on_delete=models.CASCADE, related_name='roles')
    character = models.CharField(max_length=120, blank=True, default='')

    class Meta:
        unique_together = ('movie', 'member')

    def __str__(self):
        return f'{self.member.name} in {self.movie.name}'


class MoviePoster(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='posters')
    image = models.ImageField(upload_to='posters/')
    caption = models.CharField(max_length=120, blank=True, default='')

    def __str__(self):
        return self.caption or f'Poster for {self.movie.name}'


class Theater(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='theaters')
    time = models.DateTimeField(db_index=True)
    city = models.ForeignKey(City, null=True, blank=True, on_delete=models.SET_NULL, related_name='theaters')
    language = models.ForeignKey(
        Language, null=True, blank=True, on_delete=models.SET_NULL, related_name='theaters'
    )
    screen = models.CharField(max_length=50, blank=True, default='Screen 1')
    ticket_price = models.DecimalField(max_digits=8, decimal_places=2, default=200)

    class Meta:
        indexes = [
            models.Index(fields=['movie', 'time'], name='theater_movie_time_idx'),
            models.Index(fields=['city', 'name'], name='theater_city_name_idx'),
        ]

    def __str__(self):
        return f'{self.name} - {self.movie.name} at {self.time}'


class Seat(models.Model):
    AVAILABLE = 'available'
    RESERVED = 'reserved'
    BOOKED = 'booked'
    STATUS_CHOICES = [
        (AVAILABLE, 'Available'),
        (RESERVED, 'Reserved'),
        (BOOKED, 'Booked'),
    ]

    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='seats')
    seat_number = models.CharField(max_length=10)
    is_booked = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=AVAILABLE, db_index=True)
    reserved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='held_seats'
    )
    reserved_until = models.DateTimeField(null=True, blank=True, db_index=True)
    price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text='Leave blank to use the show ticket price.',
    )

    class Meta:
        unique_together = ('theater', 'seat_number')
        indexes = [
            models.Index(fields=['theater', 'status'], name='seat_theater_status_idx'),
            models.Index(fields=['status', 'reserved_until'], name='seat_hold_expiry_idx'),
        ]

    def __str__(self):
        return f'{self.seat_number} in {self.theater.name}'

    @property
    def ticket_price(self):
        if self.price is not None:
            return self.price
        return self.theater.ticket_price

    def save(self, *args, **kwargs):
        if self.is_booked and self.status != self.BOOKED:
            self.status = self.BOOKED
        self.is_booked = self.status == self.BOOKED
        super().save(*args, **kwargs)


class Order(models.Model):
    PENDING = 'pending'
    PAID = 'paid'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    EXPIRED = 'expired'
    NEEDS_REFUND = 'needs_refund'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PAID, 'Paid'),
        (FAILED, 'Failed'),
        (CANCELLED, 'Cancelled'),
        (EXPIRED, 'Expired'),
        (NEEDS_REFUND, 'Needs refund'),
    ]

    reference = models.CharField(max_length=24, unique=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='orders')
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='INR')
    provider = models.CharField(max_length=20, blank=True, default='')
    provider_order_id = models.CharField(max_length=120, blank=True, default='', db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at'], name='order_status_created_idx'),
            models.Index(fields=['user', '-created_at'], name='order_user_created_idx'),
        ]

    def __str__(self):
        return self.reference


class SeatHold(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='holds')
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, related_name='holds')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seat_holds')
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        unique_together = ('order', 'seat')


class Booking(models.Model):
    CONFIRMED = 'confirmed'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (CONFIRMED, 'Confirmed'),
        (CANCELLED, 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, related_name='bookings')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='bookings')
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='bookings')
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.CASCADE, related_name='bookings')
    booked_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=CONFIRMED, db_index=True)
    booking_code = models.CharField(max_length=24, unique=True, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'booked_at'], name='booking_status_time_idx'),
            models.Index(fields=['movie', 'status'], name='booking_movie_status_idx'),
            models.Index(fields=['theater', 'status'], name='booking_theater_status_idx'),
            models.Index(fields=['user', 'booked_at'], name='booking_user_time_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['seat'],
                condition=Q(status='confirmed'),
                name='one_confirmed_booking_per_seat',
            ),
        ]

    def __str__(self):
        return f'Booking by {self.user.username} for {self.seat.seat_number} at {self.theater.name}'


class Payment(models.Model):
    CREATED = 'created'
    CAPTURED = 'captured'
    FAILED = 'failed'
    STATUS_CHOICES = [
        (CREATED, 'Created'),
        (CAPTURED, 'Captured'),
        (FAILED, 'Failed'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    provider = models.CharField(max_length=20)
    provider_order_id = models.CharField(max_length=120, blank=True, default='')
    provider_payment_id = models.CharField(max_length=120, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at'], name='payment_status_time_idx'),
            models.Index(fields=['provider', 'provider_order_id'], name='payment_provider_order_idx'),
        ]

    def __str__(self):
        return f'{self.provider}:{self.provider_payment_id}'


class Refund(models.Model):
    PENDING = 'pending'
    PROCESSED = 'processed'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PROCESSED, 'Processed'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='refunds')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    reason = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at'], name='refund_status_time_idx'),
        ]

    def __str__(self):
        return f'Refund {self.amount} for {self.order.reference}'


class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='reviews')
    score = models.PositiveSmallIntegerField()
    body = models.TextField()
    is_hidden = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'movie')
        constraints = [
            models.CheckConstraint(
                check=Q(score__gte=1, score__lte=5),
                name='review_score_between_1_and_5',
            ),
        ]

    def __str__(self):
        return f'{self.user.username} on {self.movie.name}'


class ReviewReport(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='reports')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='review_reports')
    reason = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('review', 'user')

    def __str__(self):
        return f'Report by {self.user.username}'


class MovieView(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='movie_views')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='views')
    viewed_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        unique_together = ('user', 'movie')
        indexes = [
            models.Index(fields=['user', '-viewed_at'], name='movieview_user_time_idx'),
        ]

    def __str__(self):
        return f'{self.user.username} viewed {self.movie.name}'


class EmailDelivery(models.Model):
    QUEUED = 'queued'
    SENDING = 'sending'
    SENT = 'sent'
    FAILED = 'failed'
    STATUS_CHOICES = [
        (QUEUED, 'Queued'),
        (SENDING, 'Sending'),
        (SENT, 'Sent'),
        (FAILED, 'Failed'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='email_deliveries')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=QUEUED, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True, default='')
    next_retry_at = models.DateTimeField(db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'next_retry_at'], name='email_retry_idx'),
        ]

    def __str__(self):
        return f'Email for {self.order.reference} ({self.status})'
