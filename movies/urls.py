from django.urls import path
from . import views

urlpatterns = [
    path('', views.movie_list, name='movie_list'),
    path('<int:movie_id>/', views.movie_detail, name='movie_detail'),
    path('<int:movie_id>/theaters', views.theater_list, name='theater_list'),
    path('theater/<int:theater_id>/seats/book/', views.book_seats, name='book_seats'),
    path('booking/release-locks/', views.release_locks, name='release_locks'),
    path('theater/<int:theater_id>/seat-status/', views.seat_status, name='seat_status'),
    path('payment/initiate/', views.initiate_payment, name='initiate_payment'),
    path('payment/confirm/', views.confirm_payment, name='confirm_payment'),
    path('payment/webhook/', views.razorpay_webhook, name='razorpay_webhook'),
]