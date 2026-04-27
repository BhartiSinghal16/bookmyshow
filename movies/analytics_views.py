import json
from datetime import timedelta

from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncDay, ExtractHour
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from movies.models import Booking, Theater

CACHE_KEY     = 'admin_analytics_v1'
CACHE_TIMEOUT = 300  # 5 minutes


def admin_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('analytics_dashboard')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user     = authenticate(request, username=username, password=password)
        if user is not None and user.is_staff:
            login(request, user)
            return redirect('analytics_dashboard')
        else:
            error = 'Invalid credentials or insufficient permissions.'
    return render(request, 'analytics/login.html', {'error': error})


def admin_logout(request):
    logout(request)
    return redirect('admin_login')


def get_analytics():
    cached = cache.get(CACHE_KEY)
    if cached:
        return cached

    now   = timezone.now()
    today = now.date()

    paid_bookings = Booking.objects.filter(payment_status='paid')

    def revenue(qs):
        result = qs.aggregate(total=Sum('ticket_price'))
        return float(result['total'] or 0)

    daily_revenue   = revenue(paid_bookings.filter(booked_at__date=today))
    weekly_revenue  = revenue(paid_bookings.filter(
        booked_at__date__gte=today - timedelta(days=7)
    ))
    monthly_revenue = revenue(paid_bookings.filter(
        booked_at__year=now.year, booked_at__month=now.month
    ))

    daily_chart = list(
        paid_bookings
        .filter(booked_at__date__gte=today - timedelta(days=29))
        .annotate(day=TruncDay('booked_at'))
        .values('day')
        .annotate(revenue=Sum('ticket_price'), count=Count('id'))
        .order_by('day')
    )

    popular_movies = list(
        paid_bookings
        .values('movie__name')
        .annotate(total_bookings=Count('id'), revenue=Sum('ticket_price'))
        .order_by('-total_bookings')[:10]
    )

    theater_stats = list(
        Theater.objects
        .annotate(
            total_seats=Count('seats'),
            booked_seats=Count('seats', filter=Q(seats__is_booked=True)),
        )
        .values('name', 'total_seats', 'booked_seats', 'movie__name')
        .order_by('-booked_seats')[:10]
    )
    for t in theater_stats:
        total = t['total_seats'] or 1
        t['occupancy_rate'] = round((t['booked_seats'] / total) * 100, 1)

    peak_hours = list(
        paid_bookings
        .filter(booked_at__date__gte=today - timedelta(days=30))
        .annotate(hour=ExtractHour('booked_at'))
        .values('hour')
        .annotate(count=Count('id'))
        .order_by('hour')
    )

    total_bookings     = Booking.objects.count()
    cancelled_bookings = Booking.objects.filter(payment_status='cancelled').count()
    failed_bookings    = Booking.objects.filter(payment_status='failed').count()
    cancel_rate        = round(
        (cancelled_bookings / total_bookings * 100) if total_bookings > 0 else 0, 1
    )
    total_users = Booking.objects.values('user').distinct().count()
    avg_ticket  = float(
        paid_bookings.aggregate(avg=Avg('ticket_price'))['avg'] or 0
    )

    data = {
        'daily_revenue':      daily_revenue,
        'weekly_revenue':     weekly_revenue,
        'monthly_revenue':    monthly_revenue,
        'daily_chart': [
            {
                'day':     d['day'].strftime('%b %d') if d['day'] else '',
                'revenue': float(d['revenue'] or 0),
                'count':   d['count'],
            }
            for d in daily_chart
        ],
        'popular_movies': [
            {
                'name':           m['movie__name'],
                'total_bookings': m['total_bookings'],
                'revenue':        float(m['revenue'] or 0),
            }
            for m in popular_movies
        ],
        'theater_stats':      theater_stats,
        'peak_hours':         peak_hours,
        'total_bookings':     total_bookings,
        'cancelled_bookings': cancelled_bookings,
        'failed_bookings':    failed_bookings,
        'cancel_rate':        cancel_rate,
        'total_users':        total_users,
        'avg_ticket':         avg_ticket,
        'generated_at':       now.strftime('%Y-%m-%d %H:%M:%S'),
    }

    cache.set(CACHE_KEY, data, CACHE_TIMEOUT)
    return data


@staff_member_required(login_url='admin_login')
def analytics_dashboard(request):
    data = get_analytics()
    return render(request, 'analytics/dashboard.html', {
        'data':                data,
        'daily_chart_json':    json.dumps(data['daily_chart']),
        'peak_hours_json':     json.dumps(data['peak_hours']),
        'popular_movies_json': json.dumps(data['popular_movies']),
    })


@staff_member_required(login_url='admin_login')
@require_GET
def analytics_api(request):
    data = get_analytics()
    return JsonResponse(data)


@staff_member_required(login_url='admin_login')
def clear_cache(request):
    cache.delete(CACHE_KEY)
    return redirect('analytics_dashboard')