from django.urls import path
from . import views

urlpatterns = [
    path('', views.movie_list, name='movie_list'),
    path('api/match-count/', views.match_count, name='match_count'),
    path('<int:movie_id>/', views.movie_detail, name='movie_detail'),
    path('<int:movie_id>/theaters', views.theater_list, name='theater_list'),
    path('<int:movie_id>/reviews/', views.submit_review, name='submit_review'),
    path('reviews/<int:review_id>/edit/', views.edit_review, name='edit_review'),
    path('reviews/<int:review_id>/report/', views.report_review, name='report_review'),
    path('theater/<int:theater_id>/seats/book/', views.book_seats, name='book_seats'),
    path('theater/<int:theater_id>/seats/status/', views.seat_status, name='seat_status'),
    path('checkout/<str:reference>/', views.checkout, name='checkout'),
    path('checkout/<str:reference>/pay/', views.start_payment, name='start_payment'),
    path('checkout/<str:reference>/return/', views.payment_return, name='payment_return'),
    path('checkout/<str:reference>/verify/', views.razorpay_verify, name='razorpay_verify'),
    path('checkout/<str:reference>/cancel/', views.cancel_checkout, name='cancel_checkout'),
    path('payments/stripe/webhook/', views.stripe_webhook, name='stripe_webhook'),
    path('payments/razorpay/webhook/', views.razorpay_webhook, name='razorpay_webhook'),
    path('tickets/<str:reference>/', views.download_ticket, name='download_ticket'),
    path('tickets/booking/<int:booking_id>/', views.download_legacy_ticket, name='download_legacy_ticket'),
    path('orders/<str:reference>/cancel/', views.cancel_order, name='cancel_order'),
]
