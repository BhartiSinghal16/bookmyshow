import re
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

YOUTUBE_EMBED_REGEX = re.compile(
    r'^https://www\.youtube\.com/embed/[\w-]{11}(\?[\w=&%-]*)?$'
)

def is_valid_youtube_embed(url):
    if not url:
        return True
    return bool(YOUTUBE_EMBED_REGEX.match(url))

LOCK_DURATION_MINUTES = 2


class Movie(models.Model):
    name        = models.CharField(max_length=255)
    image       = models.ImageField(upload_to="movies/")
    rating      = models.DecimalField(max_digits=3, decimal_places=1)
    cast        = models.TextField()
    description = models.TextField(blank=True, null=True)
    trailer_url = models.URLField(
        blank=True, null=True,
        help_text="Paste YouTube embed URL: https://www.youtube.com/embed/VIDEO_ID"
    )

    def get_safe_trailer_url(self):
        if self.trailer_url and is_valid_youtube_embed(self.trailer_url):
            return self.trailer_url
        return None

    def __str__(self):
        return self.name


class Theater(models.Model):
    SCREEN_CHOICES = [
        ('2D',   '2D'),
        ('3D',   '3D'),
        ('IMAX', 'IMAX 3D'),
    ]
    name        = models.CharField(max_length=255)
    movie       = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='theaters')
    time        = models.DateTimeField()
    screen_type = models.CharField(max_length=10, choices=SCREEN_CHOICES, default='2D')

    def __str__(self):
        return f'{self.name} - {self.movie.name} at {self.time}'


class Seat(models.Model):
    theater     = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='seats')
    seat_number = models.CharField(max_length=10)
    is_booked   = models.BooleanField(default=False)
    locked_by   = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='locked_seats'
    )
    locked_at   = models.DateTimeField(null=True, blank=True)

    def is_locked(self):
        if self.locked_by_id and self.locked_at:
            expiry = self.locked_at + timedelta(minutes=LOCK_DURATION_MINUTES)
            return timezone.now() < expiry
        return False

    def seconds_until_unlock(self):
        if self.locked_at:
            expiry    = self.locked_at + timedelta(minutes=LOCK_DURATION_MINUTES)
            remaining = (expiry - timezone.now()).total_seconds()
            return max(0, int(remaining))
        return 0

    def __str__(self):
        return f'{self.seat_number} in {self.theater.name}'


class Booking(models.Model):
    PAYMENT_STATUS = [
        ('pending',   'Pending'),
        ('paid',      'Paid'),
        ('failed',    'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    user           = models.ForeignKey(User, on_delete=models.CASCADE)
    seat           = models.OneToOneField(Seat, on_delete=models.CASCADE)
    movie          = models.ForeignKey(Movie, on_delete=models.CASCADE)
    theater        = models.ForeignKey(Theater, on_delete=models.CASCADE)
    booked_at      = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS, default='pending'
    )
    payment_id     = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f'Booking by {self.user.username} for {self.seat.seat_number}'


class PaymentRecord(models.Model):
    STATUS_CHOICES = [
        ('created', 'Created'),
        ('paid',    'Paid'),
        ('failed',  'Failed'),
    ]
    idempotency_key     = models.CharField(max_length=255, unique=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True)
    user                = models.ForeignKey(User, on_delete=models.CASCADE)
    amount              = models.PositiveIntegerField()
    status              = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='created'
    )
    seat_ids            = models.TextField()
    theater_id          = models.IntegerField()
    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Payment {self.idempotency_key} - {self.status}'