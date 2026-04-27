import hmac
import hashlib
import json
import logging
import razorpay

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.db import transaction, IntegrityError
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.utils import timezone
from django.conf import settings

from .models import (
    Movie, Theater, Seat, Booking,
    GENRE_CHOICES, LANGUAGE_CHOICES, SORT_CHOICES
)
from .email_service import EmailQueue

logger = logging.getLogger('bookmyseat.email')

MOVIES_PER_PAGE       = 9
LOCK_DURATION_MINUTES = 2
TICKET_PRICE          = 20000


def _build_booking_data(user, booking, seat, theater, payment_id):
    return {
        'username':       user.username,
        'user_email':     user.email,
        'booking_id':     booking.id,
        'movie_name':     theater.movie.name,
        'theater_name':   theater.name,
        'show_time':      theater.time.strftime('%A, %d %B %Y at %I:%M %p'),
        'screen_type':    getattr(theater, 'screen_type', '2D'),
        'seat_numbers':   [seat.seat_number],
        'seat_count':     1,
        'price_per_seat': 200,
        'total_amount':   200,
        'payment_id':     payment_id or 'N/A',
        'booked_at':      booking.booked_at.strftime('%d %B %Y, %I:%M %p'),
    }


def movie_list(request):
    search_query    = request.GET.get('search', '').strip()
    selected_genres = request.GET.getlist('genre')
    selected_langs  = request.GET.getlist('language')
    sort_by         = request.GET.get('sort', '-rating')
    page_number     = request.GET.get('page', 1)

    movies = Movie.objects.only(
        'id', 'name', 'image', 'rating',
        'genre', 'language', 'description'
    )

    if search_query:
        movies = movies.filter(
            Q(name__icontains=search_query) |
            Q(cast__icontains=search_query)
        )
    if selected_genres:
        movies = movies.filter(genre__in=selected_genres)
    if selected_langs:
        movies = movies.filter(language__in=selected_langs)

    valid_sorts = [s[0] for s in SORT_CHOICES]
    if sort_by not in valid_sorts:
        sort_by = '-rating'
    movies = movies.order_by(sort_by)

    base_for_counts = Movie.objects.only('id', 'genre', 'language')
    if search_query:
        base_for_counts = base_for_counts.filter(
            Q(name__icontains=search_query) |
            Q(cast__icontains=search_query)
        )
    if selected_langs:
        base_for_counts = base_for_counts.filter(language__in=selected_langs)
    genre_counts = {
        g['genre']: g['count']
        for g in base_for_counts.values('genre').annotate(count=Count('id'))
    }

    base_for_lang = Movie.objects.only('id', 'genre', 'language')
    if search_query:
        base_for_lang = base_for_lang.filter(
            Q(name__icontains=search_query) |
            Q(cast__icontains=search_query)
        )
    if selected_genres:
        base_for_lang = base_for_lang.filter(genre__in=selected_genres)
    lang_counts = {
        l['language']: l['count']
        for l in base_for_lang.values('language').annotate(count=Count('id'))
    }

    paginator = Paginator(movies, MOVIES_PER_PAGE)
    page_obj  = paginator.get_page(page_number)

    genres_with_counts = [
        {
            'value':    g[0], 'label': g[1],
            'count':    genre_counts.get(g[0], 0),
            'selected': g[0] in selected_genres,
        }
        for g in GENRE_CHOICES
    ]
    langs_with_counts = [
        {
            'value':    l[0], 'label': l[1],
            'count':    lang_counts.get(l[0], 0),
            'selected': l[0] in selected_langs,
        }
        for l in LANGUAGE_CHOICES
    ]

    query_params = request.GET.copy()
    if 'page' in query_params:
        query_params.pop('page')

    return render(request, 'movies/movie_list.html', {
        'movies':          page_obj,
        'page_obj':        page_obj,
        'genres':          genres_with_counts,
        'languages':       langs_with_counts,
        'sort_choices':    SORT_CHOICES,
        'selected_genres': selected_genres,
        'selected_langs':  selected_langs,
        'sort_by':         sort_by,
        'search_query':    search_query,
        'total_count':     paginator.count,
        'query_string':    query_params.urlencode(),
    })


def movie_detail(request, movie_id):
    movie        = get_object_or_404(Movie, id=movie_id)
    safe_trailer = movie.get_safe_trailer_url()
    theaters     = Theater.objects.filter(movie=movie)
    return render(request, 'movies/movie_detail.html', {
        'movie': movie, 'safe_trailer': safe_trailer, 'theaters': theaters,
    })


def theater_list(request, movie_id):
    movie   = get_object_or_404(Movie, id=movie_id)
    theater = Theater.objects.filter(movie=movie)
    return render(request, 'movies/theater_list.html', {
        'movie': movie, 'theaters': theater
    })


@login_required(login_url='/login/')
def book_seats(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)
    seats   = Seat.objects.filter(theater=theater)

    if request.method == 'POST':
        selected_ids = request.POST.getlist('seats')
        if not selected_ids:
            return render(request, 'movies/seat_selection.html', {
                'theaters': theater, 'seats': seats,
                'error': 'Please select at least one seat.',
                'lock_duration': LOCK_DURATION_MINUTES,
            })

        locked_ok = []
        conflict  = []

        with transaction.atomic():
            rows = Seat.objects.select_for_update().filter(
                id__in=selected_ids, theater=theater
            )
            for seat in rows:
                if seat.is_booked:
                    conflict.append(f'{seat.seat_number} (already booked)')
                    continue
                if hasattr(seat, 'locked_by') and seat.is_locked() and seat.locked_by != request.user:
                    conflict.append(f'{seat.seat_number} (held by another user)')
                    continue
                if hasattr(seat, 'locked_by'):
                    seat.locked_by = request.user
                    seat.locked_at = timezone.now()
                    seat.save(update_fields=['locked_by', 'locked_at'])
                locked_ok.append(seat)

        if conflict:
            seats = Seat.objects.filter(theater=theater)
            return render(request, 'movies/seat_selection.html', {
                'theaters': theater, 'seats': seats,
                'error': f'Seats unavailable: {", ".join(conflict)}',
                'lock_duration': LOCK_DURATION_MINUTES,
            })

        request.session['locked_seat_ids'] = [s.id for s in locked_ok]
        request.session['theater_id']      = theater_id
        return redirect('initiate_payment')

    return render(request, 'movies/seat_selection.html', {
        'theaters': theater, 'seats': seats,
        'lock_duration': LOCK_DURATION_MINUTES,
    })


@login_required(login_url='/login/')
@require_POST
def release_locks(request):
    seat_ids = request.session.get('locked_seat_ids', [])
    if seat_ids:
        with transaction.atomic():
            Seat.objects.select_for_update().filter(
                id__in=seat_ids,
                locked_by=request.user,
                is_booked=False
            ).update(locked_by=None, locked_at=None)
        request.session.pop('locked_seat_ids', None)
    return JsonResponse({'status': 'released'})


def seat_status(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)
    seats   = Seat.objects.filter(theater=theater)
    data    = []
    for seat in seats:
        if seat.is_booked:
            status = 'booked'
        elif hasattr(seat, 'is_locked') and callable(seat.is_locked) and seat.is_locked():
            status = 'mine' if seat.locked_by == request.user else 'locked'
        else:
            status = 'available'
        data.append({
            'id': seat.id, 'seat_number': seat.seat_number, 'status': status,
            'seconds_left': seat.seconds_until_unlock() if hasattr(seat, 'seconds_until_unlock') and seat.is_locked() else 0,
        })
    return JsonResponse({'seats': data})


@login_required(login_url='/login/')
def initiate_payment(request):
    seat_ids   = request.session.get('locked_seat_ids', [])
    theater_id = request.session.get('theater_id')

    if not seat_ids or not theater_id:
        return redirect('movie_list')

    theater = get_object_or_404(Theater, id=theater_id)
    seats   = Seat.objects.filter(id__in=seat_ids)

    if hasattr(seats.first(), 'locked_by'):
        seats       = seats.filter(locked_by=request.user)
        valid_seats = [s for s in seats if s.is_locked()]
    else:
        valid_seats = list(seats)

    if not valid_seats:
        return render(request, 'movies/booking_expired.html', {'theater': theater})

    amount = len(valid_seats) * TICKET_PRICE

    try:
        client   = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
        rz_order = client.order.create({
            'amount': amount, 'currency': 'INR', 'payment_capture': 1,
        })
        request.session['razorpay_order_id'] = rz_order['id']
        seconds_left = min(
            s.seconds_until_unlock() for s in valid_seats
        ) if hasattr(valid_seats[0], 'seconds_until_unlock') else 120

        return render(request, 'movies/payment.html', {
            'theater':           theater,
            'seats':             valid_seats,
            'amount':            amount,
            'amount_display':    amount // 100,
            'razorpay_order_id': rz_order['id'],
            'razorpay_key':      settings.RAZORPAY_KEY_ID,
            'user_email':        request.user.email,
            'seconds_left':      seconds_left,
            'lock_duration':     LOCK_DURATION_MINUTES,
        })
    except Exception as e:
        return render(request, 'movies/payment_failed.html', {
            'reason': f'Payment gateway error: {str(e)}'
        })


@login_required(login_url='/login/')
@require_POST
def confirm_payment(request):
    razorpay_order_id   = request.POST.get('razorpay_order_id')
    razorpay_payment_id = request.POST.get('razorpay_payment_id')
    razorpay_signature  = request.POST.get('razorpay_signature')
    seat_ids            = request.session.get('locked_seat_ids', [])

    payload  = f'{razorpay_order_id}|{razorpay_payment_id}'
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, razorpay_signature):
        return render(request, 'movies/payment_failed.html', {
            'reason': 'Signature verification failed.'
        })

    created_bookings = []

    with transaction.atomic():
        seats = Seat.objects.select_for_update().filter(id__in=seat_ids)
        for seat in seats:
            if seat.is_booked:
                continue
            booking = Booking.objects.create(
                user=request.user,
                seat=seat,
                movie=seat.theater.movie,
                theater=seat.theater,
                payment_id=razorpay_payment_id,
                payment_status='paid'
            )
            seat.is_booked = True
            if hasattr(seat, 'locked_by'):
                seat.locked_by = None
                seat.locked_at = None
            seat.save()
            created_bookings.append((booking, seat))

    # TASK 6: Send email in background — does not block response
    for booking, seat in created_bookings:
        try:
            booking_data = _build_booking_data(
                user=request.user,
                booking=booking,
                seat=seat,
                theater=booking.theater,
                payment_id=razorpay_payment_id,
            )
            EmailQueue.send_booking_confirmation(booking_data)
        except Exception as e:
            logger.error(
                f"[Task6] Failed to queue email booking_id={booking.id} "
                f"error={type(e).__name__}"
            )

    request.session.pop('locked_seat_ids', None)
    request.session.pop('razorpay_order_id', None)

    return render(request, 'movies/payment_success.html', {
        'order_id':   razorpay_order_id,
        'payment_id': razorpay_payment_id,
    })


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    received_sig   = request.headers.get('X-Razorpay-Signature', '')
    body           = request.body

    expected = hmac.new(
        webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, received_sig):
        return HttpResponse(status=400)

    payload = json.loads(body)
    event   = payload.get('event')

    if event == 'payment.captured':
        order_id   = payload['payload']['payment']['entity']['order_id']
        payment_id = payload['payload']['payment']['entity']['id']
        try:
            from .models import PaymentRecord
            record = PaymentRecord.objects.get(idempotency_key=order_id)
            if record.status != 'paid':
                record.razorpay_payment_id = payment_id
                record.status = 'paid'
                record.save()
        except Exception:
            pass

    elif event == 'payment.failed':
        order_id = payload['payload']['payment']['entity']['order_id']
        try:
            from .models import PaymentRecord
            record = PaymentRecord.objects.get(idempotency_key=order_id)
            if record.status != 'paid':
                record.status = 'failed'
                record.save()
        except Exception:
            pass

    return HttpResponse(status=200)