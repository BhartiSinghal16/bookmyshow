from django.db import models
from django.contrib.auth.models import User


GENRE_CHOICES = [
    ('action',    'Action'),
    ('comedy',    'Comedy'),
    ('drama',     'Drama'),
    ('horror',    'Horror'),
    ('romance',   'Romance'),
    ('thriller',  'Thriller'),
    ('sci_fi',    'Sci-Fi'),
    ('animation', 'Animation'),
    ('biography', 'Biography'),
    ('fantasy',   'Fantasy'),
]

LANGUAGE_CHOICES = [
    ('hindi',     'Hindi'),
    ('english',   'English'),
    ('tamil',     'Tamil'),
    ('telugu',    'Telugu'),
    ('kannada',   'Kannada'),
    ('malayalam', 'Malayalam'),
    ('punjabi',   'Punjabi'),
    ('bengali',   'Bengali'),
]

SORT_CHOICES = [
    ('name',        'Name A-Z'),
    ('-name',       'Name Z-A'),
    ('-rating',     'Rating High-Low'),
    ('rating',      'Rating Low-High'),
    ('-created_at', 'Newest First'),
]


class Movie(models.Model):
    name        = models.CharField(max_length=255, db_index=True)
    image       = models.ImageField(upload_to="movies/")
    rating      = models.DecimalField(max_digits=3, decimal_places=1, db_index=True)
    cast        = models.TextField()
    description = models.TextField(blank=True, null=True)
    trailer_url = models.URLField(blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True, null=True, db_index=True)
    genre       = models.CharField(
        max_length=20, choices=GENRE_CHOICES,
        default='action', db_index=True
    )
    language    = models.CharField(
        max_length=20, choices=LANGUAGE_CHOICES,
        default='hindi', db_index=True
    )

    class Meta:
        indexes = [
            models.Index(fields=['genre', 'language'], name='movie_genre_lang_idx'),
            models.Index(fields=['genre', 'rating'],   name='movie_genre_rating_idx'),
            models.Index(fields=['language', 'rating'],name='movie_lang_rating_idx'),
        ]

    def get_safe_trailer_url(self):
        import re
        YOUTUBE_REGEX = re.compile(
            r'^https://www\.youtube\.com/embed/[\w-]{11}(\?[\w=&%-]*)?$'
        )
        if self.trailer_url and YOUTUBE_REGEX.match(self.trailer_url):
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
    movie          = models.ForeignKey(Movie, on_delete=models.CASCADE, db_index=True)
    theater        = models.ForeignKey(Theater, on_delete=models.CASCADE, db_index=True)
    booked_at      = models.DateTimeField(auto_now_add=True, db_index=True)
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS,
        default='paid', db_index=True
    )
    payment_id     = models.CharField(max_length=255, blank=True, null=True)
    ticket_price   = models.DecimalField(max_digits=8, decimal_places=2, default=200.00)

    class Meta:
        indexes = [
            models.Index(fields=['booked_at', 'payment_status']),
            models.Index(fields=['movie', 'booked_at']),
            models.Index(fields=['theater', 'booked_at']),
        ]

    def __str__(self):
        return f'Booking by {self.user.username} for {self.seat.seat_number}'