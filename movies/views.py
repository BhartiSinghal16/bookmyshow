import hmac
import hashlib
import json
import razorpay

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.conf import settings

from .models import Movie, Theater, Seat, Booking, PaymentRecord, LOCK_DURATION_MINUTES

TICKET_PRICE = 20000  # Rs 200 per seat in paise


def movie_list(request):
    search_query = request.GET.get('search')
    if search_query:
        movies = Movie.objects.filter(name__icontains=search_query)
    else:
        movies = Movie.objects.all()
    return render(request, 'movies/movie_list.html', {'movies': movies})


def movie_detail(request, movie_id):
    movie        = get_object_or_404(Movie, id=movie_id)
    safe_trailer = movie.get_safe_trailer_url()
    theaters     = Theater.objects.filter(movie=movie)
    return render(request, 'movies/movie_detail.html', {
        'movie':        movie,
        'safe_trailer': safe_trailer,
        'theaters':     theaters,
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
                if seat.is_locked() and seat.locked_by != request.user:
                    conflict.append(f'{seat.seat_number} (held by another user)')
                    continue
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
        'theaters': theater,
        'seats':    seats,
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
        elif seat.is_locked():
            status = 'mine' if seat.locked_by == request.user else 'locked'
        else:
            status = 'available'
        data.append({
            'id':          seat.id,
            'seat_number': seat.seat_number,
            'status':      status,
            'seconds_left': seat.seconds_until_unlock() if seat.is_locked() else 0,
        })
    return JsonResponse({'seats': data})


# ── Feature C: Initiate Razorpay Payment ─────────────────────
@login_required(login_url='/login/')
def initiate_payment(request):
    seat_ids   = request.session.get('locked_seat_ids', [])
    theater_id = request.session.get('theater_id')

    if not seat_ids or not theater_id:
        return redirect('movie_list')

    theater = get_object_or_404(Theater, id=theater_id)
    seats   = Seat.objects.filter(id__in=seat_ids, locked_by=request.user)
    valid_seats = [s for s in seats if s.is_locked()]

    if not valid_seats:
        return render(request, 'movies/booking_expired.html', {'theater': theater})

    amount = len(valid_seats) * TICKET_PRICE

    # Create Razorpay order
    client   = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )
    rz_order = client.order.create({
        'amount':          amount,
        'currency':        'INR',
        'payment_capture': 1,
    })

    # Save idempotency record
    PaymentRecord.objects.get_or_create(
        idempotency_key=rz_order['id'],
        defaults={
            'user':       request.user,
            'amount':     amount,
            'status':     'created',
            'seat_ids':   ','.join(str(s.id) for s in valid_seats),
            'theater_id': theater_id,
        }
    )

    request.session['razorpay_order_id'] = rz_order['id']
    seconds_left = min(s.seconds_until_unlock() for s in valid_seats)

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


# ── Feature C: Server-side payment verification ───────────────
@login_required(login_url='/login/')
@require_POST
def confirm_payment(request):
    razorpay_order_id   = request.POST.get('razorpay_order_id')
    razorpay_payment_id = request.POST.get('razorpay_payment_id')
    razorpay_signature  = request.POST.get('razorpay_signature')
    seat_ids            = request.session.get('locked_seat_ids', [])

    # HMAC-SHA256 signature verification
    # Prevents fraud — frontend cannot fake successful payment
    payload  = f'{razorpay_order_id}|{razorpay_payment_id}'
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, razorpay_signature):
        return render(request, 'movies/payment_failed.html', {
            'reason': 'Payment signature verification failed. Possible fraud attempt.'
        })

    # Idempotency check
    try:
        record = PaymentRecord.objects.get(idempotency_key=razorpay_order_id)
    except PaymentRecord.DoesNotExist:
        return render(request, 'movies/payment_failed.html', {
            'reason': 'Unknown order.'
        })

    if record.status == 'paid':
        return redirect('profile')

    # Finalize booking atomically
    with transaction.atomic():
        seats = Seat.objects.select_for_update().filter(
            id__in=seat_ids, locked_by=request.user
        )
        for seat in seats:
            if seat.is_booked:
                continue
            Booking.objects.create(
                user=request.user,
                seat=seat,
                movie=seat.theater.movie,
                theater=seat.theater,
                payment_id=razorpay_payment_id,
                payment_status='paid'
            )
            seat.is_booked = True
            seat.locked_by = None
            seat.locked_at = None
            seat.save()

        record.razorpay_payment_id = razorpay_payment_id
        record.status = 'paid'
        record.save()

    request.session.pop('locked_seat_ids', None)
    request.session.pop('razorpay_order_id', None)

    return render(request, 'movies/payment_success.html', {
        'order_id': razorpay_order_id,
        'payment_id': razorpay_payment_id,
    })


# ── Feature C: Razorpay Webhook ───────────────────────────────
@csrf_exempt
@require_POST
def razorpay_webhook(request):
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    received_sig   = request.headers.get('X-Razorpay-Signature', '')
    body           = request.body

    # Verify webhook signature — prevents replay attacks
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

        with transaction.atomic():
            try:
                record = PaymentRecord.objects.select_for_update().get(
                    idempotency_key=order_id
                )
            except PaymentRecord.DoesNotExist:
                return HttpResponse(status=200)

            if record.status == 'paid':
                return HttpResponse(status=200)

            record.razorpay_payment_id = payment_id
            record.status = 'paid'
            record.save()

    elif event == 'payment.failed':
        order_id = payload['payload']['payment']['entity']['order_id']
        try:
            record = PaymentRecord.objects.get(idempotency_key=order_id)
            if record.status != 'paid':
                record.status = 'failed'
                record.save()
                seat_ids = [int(x) for x in record.seat_ids.split(',') if x]
                Seat.objects.filter(id__in=seat_ids).update(
                    locked_by=None, locked_at=None
                )
        except PaymentRecord.DoesNotExist:
            pass

    return HttpResponse(status=200)