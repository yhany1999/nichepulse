import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

import stripe
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

load_dotenv(Path(__file__).parent.parent / ".env")

from .database import Base, engine, get_db
from .models import User, Subscription
from .auth import authenticate_user, create_user, get_user_by_email, get_user_by_id
from . import scheduler as sched

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    sched.start()
    yield
    sched.stop()


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "change-me-in-production"))

BASE_DIR = Path(__file__).parent
# cache_size=0 avoids a weakref/dict hashability bug in Python 3.14
_jinja_env = Environment(
    loader=FileSystemLoader(str(BASE_DIR / "templates")),
    cache_size=0,
)
templates = Jinja2Templates(env=_jinja_env)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ── Helpers ──────────────────────────────────────────────────────────────────

def flash(request: Request, message: str, category: str = "info"):
    request.session.setdefault("flashes", []).append({"msg": message, "cat": category})


def get_flashes(request: Request):
    return request.session.pop("flashes", [])


def current_user(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("user_id")
    return get_user_by_id(db, uid) if uid else None


def require_login(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


# ── Public routes ─────────────────────────────────────────────────────────────

from fastapi.responses import PlainTextResponse

@app.get("/", response_class=PlainTextResponse)
def home():
    return "working"

@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse(request, "signup.html", {
        "flashes": get_flashes(request),
    })


@app.post("/signup")
def signup(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    db: Session = Depends(get_db),
):
    if len(password) < 8:
        flash(request, "Password must be at least 8 characters.", "error")
        return RedirectResponse("/signup", status_code=303)
    if get_user_by_email(db, email):
        flash(request, "An account with that email already exists.", "error")
        return RedirectResponse("/signup", status_code=303)
    user = create_user(db, email.lower().strip(), password)
    request.session["user_id"] = user.id
    flash(request, "Account created — welcome!", "success")
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {
        "flashes": get_flashes(request),
    })


@app.post("/login")
def login(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, email.lower().strip(), password)
    if not user:
        flash(request, "Invalid email or password.", "error")
        return RedirectResponse("/login", status_code=303)
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "flashes": get_flashes(request),
        "keywords_str": "\n".join(user.keywords or []),
    })


@app.post("/dashboard/keywords")
def update_keywords(
    request: Request,
    keywords: str = Form(),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    kw_list = [k.strip() for k in keywords.splitlines() if k.strip()][:20]
    user.keywords = kw_list
    db.commit()
    flash(request, f"Keywords updated ({len(kw_list)} saved).", "success")
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/dashboard/send-now")
def send_now(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user.is_subscribed:
        flash(request, "You need an active subscription to send reports.", "error")
        return RedirectResponse("/dashboard", status_code=303)

    import datetime
    from .youtube import run_report
    from .mailer import send_email

    try:
        report = run_report(user.keywords or [])
        week = datetime.date.today().strftime("%B %d, %Y")
        send_email(
            subject=f"YouTube Niche Trending Report — {week}",
            body=report,
            to_addr=user.email,
        )
        flash(request, "Report sent to your inbox!", "success")
    except Exception as e:
        log.exception("send-now failed")
        flash(request, f"Failed to send report: {e}", "error")

    return RedirectResponse("/dashboard", status_code=303)


# ── Stripe subscription ───────────────────────────────────────────────────────

@app.post("/subscription/create")
def create_subscription(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)

    if not STRIPE_PRICE_ID:
        flash(request, "Stripe is not configured yet.", "error")
        return RedirectResponse("/dashboard", status_code=303)

    # Reuse existing Stripe customer or create one
    sub = user.subscription
    customer_id = sub.stripe_customer_id if sub else None

    if not customer_id:
        customer = stripe.Customer.create(email=user.email, metadata={"user_id": user.id})
        customer_id = customer.id
        if not sub:
            sub = Subscription(user_id=user.id, stripe_customer_id=customer_id)
            db.add(sub)
        else:
            sub.stripe_customer_id = customer_id
        db.commit()

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        mode="subscription",
        success_url=f"{APP_URL}/subscription/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{APP_URL}/dashboard",
    )
    return RedirectResponse(session.url, status_code=303)


@app.get("/subscription/success")
def subscription_success(request: Request, session_id: str, db: Session = Depends(get_db)):
    user = require_login(request, db)
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
        stripe_sub = session.subscription
        sub = user.subscription
        if sub and stripe_sub:
            sub.stripe_subscription_id = stripe_sub.id
            sub.status = "active"
            db.commit()
    except Exception:
        log.exception("Failed to activate subscription from success URL")
    flash(request, "Subscription activated — welcome aboard!", "success")
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/subscription/cancel")
def cancel_subscription(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    sub = user.subscription

    if not sub or not sub.stripe_subscription_id:
        flash(request, "No active subscription found.", "error")
        return RedirectResponse("/dashboard", status_code=303)

    try:
        stripe.Subscription.cancel(sub.stripe_subscription_id)
        sub.status = "cancelled"
        db.commit()
        flash(request, "Subscription cancelled. You'll keep access until the period ends.", "info")
    except Exception as e:
        flash(request, f"Could not cancel: {e}", "error")

    return RedirectResponse("/dashboard", status_code=303)


# ── Stripe webhook ────────────────────────────────────────────────────────────

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    data = event["data"]["object"]

    if event["type"] == "customer.subscription.updated":
        _sync_subscription(db, data)
    elif event["type"] == "customer.subscription.deleted":
        _sync_subscription(db, data, force_status="cancelled")
    elif event["type"] == "invoice.payment_failed":
        customer_id = data.get("customer")
        sub = db.query(Subscription).filter(
            Subscription.stripe_customer_id == customer_id
        ).first()
        if sub:
            sub.status = "past_due"
            db.commit()

    return {"ok": True}


def _sync_subscription(db: Session, stripe_sub, force_status: str = None):
    import datetime

    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_sub["id"]
    ).first()
    if not sub:
        return

    sub.status = force_status or stripe_sub.get("status", "inactive")
    period_end = stripe_sub.get("current_period_end")
    if period_end:
        sub.period_end = datetime.datetime.utcfromtimestamp(period_end)
    db.commit()
