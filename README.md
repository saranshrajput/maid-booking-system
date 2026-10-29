# Maid Booking System (Python)

Python 3.10+ / FastAPI backend for the Rupeek SDE-3 machine-coding question (Maid Booking System). In-memory by default; Postgres when `DATABASE_URL` is set.

## Build and run

```bash
cd python && pip install -r requirements.txt
python -m pytest                          # API and service tests on the in-memory backend
uvicorn maidbooking.api:app --reload      # http://localhost:8000, docs at /docs
```

## Web UI

The same FastAPI app serves a mobile-first web UI at `/` (files in `python/maidbooking/static/`, no build step), so a single deploy gives you both. It is a bottom-tab app with these screens:

- **Home**: pick your area, then a service tile (cleaning, cooking, dishwashing, laundry, babysitting). Tiles show the lowest hourly rate and how many maids serve the area. A banner books a maid instantly.
- **Choose service details**: Now, One day, Multiple days (a date range up to 14 days) or Weekly (pick weekdays and number of visits); a calendar, duration cards with prices, and start times in 15-minute steps. Times nobody can take are greyed out (`GET /api/availability/slots`).
- **Choose your maid**: maids free for that exact slot, best rated first, with the total price. Booking holds the slot and opens the payment sheet (card, UPI or wallet; one visit or all unpaid visits).
- **Your bookings**: All, Single, Multiple and Recurring filters, status pills (upcoming, in progress, completed, awaiting payment, cancelled), and expandable visit lists.
- **Booking details**: status banner with time left while a visit is running, maid, date, payment status, a dot per visit, Pay and Cancel (one visit or the whole series, refund shown).
- **Account**: customer id (there is no login), service area, and partner onboarding (add a maid, or load three sample maids).

"Upcoming", "in progress" and "completed" are derived in the browser from the server clock (`GET /api/meta`); the API itself only stores pending, confirmed and cancelled.

Browser test (needs Node and the `playwright` package): `PYTHON=python ./python/e2e/run.sh` starts a fresh in-memory server and runs 43 checks across every screen, including slot greying, a payment decline, series payment and cancellation, and phone width. Set `DATABASE_URL` to run the same flow against Postgres (the database must be empty).

## Persistence and configuration

| Env var | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string. Unset = in-memory. `postgres://` and `postgresql://` are both accepted. Tables are created on startup. |
| `APP_TIMEZONE` | Business timezone for "now" and availability windows (default `Asia/Kolkata`; servers on Render run UTC). |
| `TEST_DATABASE_URL` | Enables the Postgres runs of the test suite (the service tests run on both backends: 71 tests). |

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
| Free-maid count per start time | `GET /api/availability/slots?date=&durationMinutes=&serviceType=&locality=` |
| Server clock | `GET /api/meta` |
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
