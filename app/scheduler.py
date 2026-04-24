import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()
log = logging.getLogger(__name__)


def _weekly_job():
    from .database import SessionLocal
    from .models import Subscription
    from .youtube import run_report
    from .mailer import send_email
    import datetime

    db = SessionLocal()
    try:
        active = db.query(Subscription).filter(Subscription.status == "active").all()
        week = datetime.date.today().strftime("%B %d, %Y")
        log.info(f"Weekly job: sending reports to {len(active)} subscriber(s)")

        for sub in active:
            try:
                keywords = sub.user.keywords or []
                if not keywords:
                    continue
                report = run_report(keywords)
                send_email(
                    subject=f"YouTube Niche Trending Report — {week}",
                    body=report,
                    to_addr=sub.user.email,
                )
                log.info(f"  Sent to {sub.user.email}")
            except Exception:
                log.exception(f"  Failed for user {sub.user_id}")
    finally:
        db.close()


def start(send_day: str = "sun", send_hour: int = 6):
    scheduler.add_job(
        _weekly_job,
        CronTrigger(day_of_week=send_day, hour=send_hour, minute=0),
        id="weekly_report",
        replace_existing=True,
    )
    scheduler.start()
    log.info(f"Scheduler started — reports run every {send_day} at {send_hour:02d}:00 UTC")


def stop():
    if scheduler.running:
        scheduler.shutdown()
