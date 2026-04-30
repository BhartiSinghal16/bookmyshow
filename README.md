# 🎬 BookMySeat — Online Movie Ticket Booking System

A full-featured movie booking web application built with Django and Python, inspired by BookMyShow.

## 🌐 Live Demo
**Live Website:** https://web-production-e27de.up.railway.app

**Admin Panel:** https://web-production-e27de.up.railway.app/admin

**Analytics Dashboard:** https://web-production-e27de.up.railway.app/admin-dashboard/

---

## 👩‍💻 Developer
- **Name:** Bharti Singhal
- **Course:** B.Tech CSE
- **University:** Manav Rachna University

---

## 🛠️ Tech Stack
- Python 3.12
- Django 3.2
- PostgreSQL (Neon)
- Razorpay Payment Gateway
- APScheduler
- Bootstrap 4
- Railway (Deployment)

---

## ✅ Features

### Task A — Secure YouTube Trailer Embedding
- Server-side URL validation using regex
- Lazy loading — video loads only on click
- XSS prevention using sandbox attribute
- Graceful fallback when trailer unavailable

### Task B — Concurrency-Safe Seat Reservation
- select_for_update() for DB row-level locking
- 2-minute temporary seat lock before payment
- APScheduler auto-releases expired locks every 60 seconds
- Handles tab close, network drop, multi-device

### Task C — Payment Gateway Integration
- Real Razorpay payment integration
- HMAC-SHA256 server-side signature verification
- Idempotency keys prevent duplicate transactions
- Webhook security blocks replay attacks

### Task D — Admin Analytics Dashboard
- Real-time revenue (daily, weekly, monthly)
- Most popular movies and busiest theaters
- Peak booking hours chart
- Role-based access control
- 5-minute in-memory caching

### Task 5 — Genre & Language Filtering
- Multi-select genre and language filters
- Dynamic filter counts
- Pagination and sorting
- Composite DB indexes for performance

### Task 6 — Automated Email Confirmation
- Booking confirmation email after payment
- Background threading — non-blocking
- Retry logic — 3 attempts
- Django template engine for HTML email

---

## 🚀 Installation

```bash
git clone https://github.com/BhartiSinghal16/bookmyshow.git
cd bookmyshow
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

---

## 📊 Admin Credentials
- **Username:** Bharti
- **Password:** Admin@1234

---

## 💳 Test Payment Details
- **Card:** 4111 1111 1111 1111
- **Expiry:** 12/26
- **CVV:** 123
- **OTP:** 1234
