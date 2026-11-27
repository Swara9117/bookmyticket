from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def mark_booked_seats(apps, schema_editor):
    Seat = apps.get_model('movies', 'Seat')
    Seat.objects.filter(is_booked=True).update(status='booked')


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('movies', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Genre',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, unique=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Language',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, unique=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='City',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
            ],
            options={'ordering': ['name'], 'verbose_name_plural': 'cities'},
        ),
        migrations.CreateModel(
            name='CastMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('photo', models.ImageField(blank=True, null=True, upload_to='cast/')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.AddField(
            model_name='movie',
            name='trailer_url',
            field=models.URLField(blank=True, default='', help_text='YouTube watch or share link. Only YouTube URLs are embedded.'),
        ),
        migrations.AddField(
            model_name='movie',
            name='age_certification',
            field=models.CharField(default='U', max_length=10),
        ),
        migrations.AddField(
            model_name='movie',
            name='duration_minutes',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='movie',
            name='release_date',
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='movie',
            name='popularity',
            field=models.PositiveIntegerField(db_index=True, default=0),
        ),
        migrations.AddField(
            model_name='movie',
            name='average_rating',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=4),
        ),
        migrations.AddField(
            model_name='movie',
            name='review_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='movie',
            name='name',
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name='movie',
            name='genres',
            field=models.ManyToManyField(blank=True, related_name='movies', to='movies.genre'),
        ),
        migrations.AddField(
            model_name='movie',
            name='languages',
            field=models.ManyToManyField(blank=True, related_name='movies', to='movies.language'),
        ),
        migrations.CreateModel(
            name='MovieCast',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('character', models.CharField(blank=True, default='', max_length=120)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='roles', to='movies.castmember')),
                ('movie', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cast_roles', to='movies.movie')),
            ],
            options={'unique_together': {('movie', 'member')}},
        ),
        migrations.AddField(
            model_name='movie',
            name='cast_members',
            field=models.ManyToManyField(blank=True, related_name='movies', through='movies.MovieCast', to='movies.castmember'),
        ),
        migrations.CreateModel(
            name='MoviePoster',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='posters/')),
                ('caption', models.CharField(blank=True, default='', max_length=120)),
                ('movie', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='posters', to='movies.movie')),
            ],
        ),
        migrations.AddIndex(
            model_name='movie',
            index=models.Index(fields=['-popularity', '-id'], name='movie_popularity_idx'),
        ),
        migrations.AddIndex(
            model_name='movie',
            index=models.Index(fields=['-release_date'], name='movie_release_idx'),
        ),
        migrations.AddField(
            model_name='theater',
            name='city',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='theaters', to='movies.city'),
        ),
        migrations.AddField(
            model_name='theater',
            name='language',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='theaters', to='movies.language'),
        ),
        migrations.AddField(
            model_name='theater',
            name='screen',
            field=models.CharField(default='Screen 1', max_length=50),
        ),
        migrations.AddField(
            model_name='theater',
            name='ticket_price',
            field=models.DecimalField(decimal_places=2, default=200, max_digits=8),
        ),
        migrations.AlterField(
            model_name='theater',
            name='name',
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='theater',
            name='time',
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AddIndex(
            model_name='theater',
            index=models.Index(fields=['movie', 'time'], name='theater_movie_time_idx'),
        ),
        migrations.AddIndex(
            model_name='theater',
            index=models.Index(fields=['city', 'name'], name='theater_city_name_idx'),
        ),
        migrations.AddField(
            model_name='seat',
            name='status',
            field=models.CharField(choices=[('available', 'Available'), ('reserved', 'Reserved'), ('booked', 'Booked')], db_index=True, default='available', max_length=12),
        ),
        migrations.AddField(
            model_name='seat',
            name='reserved_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='held_seats', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='seat',
            name='reserved_until',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='seat',
            name='price',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Leave blank to use the show ticket price.', max_digits=8, null=True),
        ),
        migrations.AlterUniqueTogether(
            name='seat',
            unique_together={('theater', 'seat_number')},
        ),
        migrations.AddIndex(
            model_name='seat',
            index=models.Index(fields=['theater', 'status'], name='seat_theater_status_idx'),
        ),
        migrations.AddIndex(
            model_name='seat',
            index=models.Index(fields=['status', 'reserved_until'], name='seat_hold_expiry_idx'),
        ),
        migrations.RunPython(mark_booked_seats, migrations.RunPython.noop),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(db_index=True, max_length=24, unique=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed'), ('cancelled', 'Cancelled'), ('expired', 'Expired'), ('needs_refund', 'Needs refund')], db_index=True, default='pending', max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('currency', models.CharField(default='INR', max_length=3)),
                ('provider', models.CharField(blank=True, default='', max_length=20)),
                ('provider_order_id', models.CharField(blank=True, db_index=True, default='', max_length=120)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('failure_reason', models.CharField(blank=True, default='', max_length=255)),
                ('movie', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='movies.movie')),
                ('theater', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='movies.theater')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['status', 'created_at'], name='order_status_created_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['user', '-created_at'], name='order_user_created_idx'),
        ),
        migrations.AlterField(
            model_name='booking',
            name='seat',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to='movies.seat'),
        ),
        migrations.AlterField(
            model_name='booking',
            name='movie',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to='movies.movie'),
        ),
        migrations.AlterField(
            model_name='booking',
            name='theater',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to='movies.theater'),
        ),
        migrations.AlterField(
            model_name='booking',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='booking',
            name='order',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to='movies.order'),
        ),
        migrations.AddField(
            model_name='booking',
            name='status',
            field=models.CharField(choices=[('confirmed', 'Confirmed'), ('cancelled', 'Cancelled')], db_index=True, default='confirmed', max_length=20),
        ),
        migrations.AddField(
            model_name='booking',
            name='booking_code',
            field=models.CharField(blank=True, max_length=24, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['status', 'booked_at'], name='booking_status_time_idx'),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['movie', 'status'], name='booking_movie_status_idx'),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['theater', 'status'], name='booking_theater_status_idx'),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['user', 'booked_at'], name='booking_user_time_idx'),
        ),
        migrations.AddConstraint(
            model_name='booking',
            constraint=models.UniqueConstraint(condition=models.Q(status='confirmed'), fields=('seat',), name='one_confirmed_booking_per_seat'),
        ),
        migrations.CreateModel(
            name='SeatHold',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='holds', to='movies.order')),
                ('seat', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='holds', to='movies.seat')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='seat_holds', to=settings.AUTH_USER_MODEL)),
            ],
            options={'unique_together': {('order', 'seat')}},
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(max_length=20)),
                ('provider_order_id', models.CharField(blank=True, default='', max_length=120)),
                ('provider_payment_id', models.CharField(max_length=120, unique=True)),
                ('status', models.CharField(choices=[('created', 'Created'), ('captured', 'Captured'), ('failed', 'Failed')], db_index=True, max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='movies.order')),
            ],
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['status', 'created_at'], name='payment_status_time_idx'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['provider', 'provider_order_id'], name='payment_provider_order_idx'),
        ),
        migrations.CreateModel(
            name='Refund',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processed', 'Processed')], db_index=True, default='pending', max_length=20)),
                ('reason', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='refunds', to='movies.order')),
            ],
        ),
        migrations.AddIndex(
            model_name='refund',
            index=models.Index(fields=['status', 'created_at'], name='refund_status_time_idx'),
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('score', models.PositiveSmallIntegerField()),
                ('body', models.TextField()),
                ('is_hidden', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('movie', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='movies.movie')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to=settings.AUTH_USER_MODEL)),
            ],
            options={'unique_together': {('user', 'movie')}},
        ),
        migrations.AddConstraint(
            model_name='review',
            constraint=models.CheckConstraint(check=models.Q(('score__gte', 1), ('score__lte', 5)), name='review_score_between_1_and_5'),
        ),
        migrations.CreateModel(
            name='ReviewReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('review', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='movies.review')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='review_reports', to=settings.AUTH_USER_MODEL)),
            ],
            options={'unique_together': {('review', 'user')}},
        ),
        migrations.CreateModel(
            name='MovieView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('viewed_at', models.DateTimeField(auto_now=True, db_index=True)),
                ('movie', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='views', to='movies.movie')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='movie_views', to=settings.AUTH_USER_MODEL)),
            ],
            options={'unique_together': {('user', 'movie')}},
        ),
        migrations.AddIndex(
            model_name='movieview',
            index=models.Index(fields=['user', '-viewed_at'], name='movieview_user_time_idx'),
        ),
        migrations.CreateModel(
            name='EmailDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('sending', 'Sending'), ('sent', 'Sent'), ('failed', 'Failed')], db_index=True, default='queued', max_length=20)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('last_error', models.CharField(blank=True, default='', max_length=500)),
                ('next_retry_at', models.DateTimeField(db_index=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_deliveries', to='movies.order')),
            ],
        ),
        migrations.AddIndex(
            model_name='emaildelivery',
            index=models.Index(fields=['status', 'next_retry_at'], name='email_retry_idx'),
        ),
    ]
