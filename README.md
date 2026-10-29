# Maid Booking System (Python)

Python 3.10+ / FastAPI backend for the Rupeek SDE-3 machine-coding question (Maid Booking System). In-memory by default; Postgres when `DATABASE_URL` is set.

## Build and run

```bash
cd python && pip install -r requirements.txt
python -m pytest                          # API and service tests on the in-memory backend
uvicorn maidbooking.api:app --reload      # http://localhost:8000, docs at /docs
```

## Web UI

The same FastAPI app serves a no-build web UI at `/` (files in `python/maidbooking/static/`), so a single deploy gives you both. Screens:

- **Find a maid**: filters for area, service, rating, max rate, gender, skills, and an optional date and start time that limits results to maids free then. Each maid card opens the booking dialog.
- **Booking dialog**: instant, scheduled or recurring (pick weekdays and number of visits) with a live price estimate, then a payment step (card, UPI, wallet) that supports paying one visit or all unpaid visits.
- **My bookings**: lists bookings for the customer id typed in the header ("Booking as", no login), with Pay and Cancel per visit and Cancel whole series. Refund amounts show after cancelling.
- **Add a maid**: onboarding form with services, rates and weekly hours, plus a button that loads three sample maids.

`GET /api/bookings?customerId=` backs the My bookings screen.

Browser test (needs Node and the `playwright` package): `PYTHON=python ./python/e2e/run.sh` starts a fresh in-memory server and runs 34 checks across every screen, including a payment decline, a double-booking conflict, series payment and cancellation, and phone width. Set `DATABASE_URL` to run the same flow against Postgres (the database must be empty).

## Persistence and configuration

| Env var | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string. Unset = in-memory. `postgres://` and `postgresql://` are both accepted. Tables are created on startup. |
| `APP_TIMEZONE` | Business timezone for "now" and availability windows (default `Asia/Kolkata`; servers on Render run UTC). |
| `TEST_DATABASE_URL` | Enables the Postgres runs of the test suite (the service tests run on both backends: 70 tests). |

Run the same suite against Postgres: `TEST_DATABASE_URL=postgresql://user:pass@localhost/db python -m pytest`.

Double-booking protection with Postgres: each book, pay or cancel for a maid takes an in-process lock and then a Postgres advisory lock keyed on the maid id, so it holds across several app instances. A test with two app instances sharing one database fails if the advisory lock is removed.

## Deploy on Render

`render.yaml` at the repo root is a Blueprint for a web service plus a managed Postgres database.

1. Push this repo to GitHub.
2. In the Render dashboard choose **New > Blueprint**, pick the repo, and apply. Render creates `maid-booking-db` and `maid-booking-api` and wires `DATABASE_URL` into the service.
3. When the deploy is live, open `https://<service>.onrender.com/docs` and call `/health` (it reports `"storage": "postgres"`).

Notes: run a single worker (the start command already does); the schema is created by the app on startup, with no migration tool yet; check the plan names and free-tier limits in the Render dashboard before relying on them.

## API

| Operation | Endpoint |
|---|---|
| Add maid | `POST /api/maids` |
| Get maid | `GET /api/maids/{id}` |
| Discover | `GET /api/maids/search?locality=&serviceType=&date=&startTime=&durationMinutes=&minRating=&maxHourlyRate=&gender=&skills=` |
| Book | `POST /api/bookings` |
| Get booking | `GET /api/bookings/{id}` |
| List a customer's bookings | `GET /api/bookings?customerId=` |
| Pay | `POST /api/bookings/{id}/payments` (optional `Idempotency-Key` header) |
| Cancel | `POST /api/bookings/{id}/cancel[?occurrenceId=]` (no id = whole series) |

Request bodies are JSON as in the Swagger UI at /docs; `day` / `daysOfWeek` take weekday numbers 0 (Monday) to 6 (Sunday). Mock gateway: an instrument starting with `fail` is declined; UPI needs `@`, card needs 12-19 digits.

## Design

```
domain.py               Maid, Booking, BookingOccurrence, Payment, TimeSlot, AvailabilityWindow, RecurrenceRule
repositories.py         ABCs + in-memory implementations
booking_strategies.py   BookingStrategy per type (Instant, Scheduled, Recurring) + registry
search.py               filter providers (one function per filter) + MaidSearchService
payment_processors.py   PaymentProcessor per method (mock gateway) + registry
pricing.py              PricingStrategy (hourly)
cancellation_policy.py  CancellationPolicy (time-based refunds)
services.py             Booking, Payment, Cancellation, Availability, Maid services + per-maid lock
api.py                  FastAPI app, DTOs, error mapping
```

- A booking is a list of occurrences; availability, payment and cancellation work per occurrence, so recurring bookings need no special cases.
- Extension points: new booking type -> `BookingStrategy`; payment method -> `PaymentProcessor`; filter -> provider function; refund rules -> `CancellationPolicy`; pricing -> `PricingStrategy`.
- Occurrence states: `PENDING_PAYMENT -> CONFIRMED -> CANCELLED`, enforced in the entity; booking status is derived.
- Book, pay and cancel run under a per-maid lock, so concurrent requests cannot double-book (16-thread test).
- `Idempotency-Key` on pay replays the original result without charging again.
- Refunds: 24h+ before start 100%, 2h+ 50%, otherwise 0%.

## Assumptions and next steps

Slots are naive local date-times that cannot span midnight, recurring bookings are all-or-nothing, unpaid bookings hold the slot (no TTL yet), customers are just an id. Next: hold expiry, completed state, dynamic pricing, DB-backed locking for multi-instance use.
