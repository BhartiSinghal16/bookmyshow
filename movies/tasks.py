from datetime import timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone

LOCK_DURATION_MINUTES = 2


def release_expired_locks():
    from movies.models import Seat
    cutoff   = timezone.now() - timedelta(minutes=LOCK_DURATION_MINUTES)
    released = Seat.objects.filter(
        locked_at__lt=cutoff,
        locked_by__isnull=False,
        is_booked=False
    ).update(locked_by=None, locked_at=None)
    if released:
        print(f'[Scheduler] Released {released} expired seat lock(s)')


def start():
    scheduler = BackgroundScheduler(timezone='UTC')
    scheduler.add_job(
        release_expired_locks,
        trigger='interval',
        seconds=60,
        id='release_expired_locks',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    print('[Scheduler] Auto-release scheduler started.')