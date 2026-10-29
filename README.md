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
- **Account**: customer id (there is no login), service area, and partner tools: add a maid, load the three sample maids (it skips ones already there), and **Manage maids**.
- **Manage maids**: remove a maid, or all sample maids. Removing hides her from search and booking while old bookings keep her name. If she has upcoming visits the removal is refused, with an option to cancel those visits (full refunds, since the maid is leaving) and remove her.

"Upcoming", "in progress" and "completed" are derived in the browser from the server clock (`GET /api/meta`); the API itself only stores pending, confirmed and cancelled.

Browser test (needs Node and the `playwright` package): `PYTHON=python ./python/e2e/run.sh` starts a fresh in-memory server and runs 55 checks across every screen (plus 18 on hold expiry against a clock the test moves, and the "Book now" runs), including slot greying, a payment decline, series payment and cancellation, removing maids and phone width, then 18 more on "Book now" against a server with a fixed clock (`e2e/fixed_clock_server.py`): a daytime run where an instant booking goes through to an in-progress visit, and a night run where nobody is free. Set `DATABASE_URL` to run the same flow against Postgres (the database must be empty).

## Holds and idempotency

**Unpaid holds expire.** Booking holds the slot for `HOLD_MINUTES` (default 10). Each unpaid visit carries a deadline (`holdExpiresAt` in the API).

- A lapsed hold stops blocking the maid immediately: availability, search and the start-time grid read "confirmed, or unpaid with a live hold", so nothing waits for a background job.
- A sweeper marks lapsed holds `EXPIRED` (a booking whose visits are all expired shows as `EXPIRED`). It runs in the app every `HOLD_SWEEP_SECONDS`, is safe on several instances at once, and also deletes old idempotency keys.
- **Paying late:** an expired visit can still be paid, but only while the slot is free. Under the maid lock, every visit being paid is re-checked before anything is charged. If someone else has the slot the answer is `409 HOLD_EXPIRED` and nothing is charged; if it is free the hold is renewed and the payment goes through. A visit whose time has passed cannot be paid.
- Expired visits cannot be cancelled and do not count as upcoming for removing a maid.
- The UI shows a countdown in the payment sheet and on the booking, an Expired state, and "Pay (we re-check the slot)".
- **Upgrading:** unpaid visits written by the previous release have no deadline, so they count as already lapsed: they stop blocking the maid, get swept, and can be paid again if the slot is free. Paid visits are untouched.

**Payment idempotency.** `Idempotency-Key` is scoped to the booking and checked under the maid lock.

| Case | Result |
|---|---|
| Same key, same request | the first result is returned, nothing is charged again |
| Same key, different request (method, instrument or visit) | `422 IDEMPOTENCY_KEY_REUSED` |
| Same key while an earlier attempt never finished (for example a crash after charging) | `409 IDEMPOTENCY_IN_PROGRESS`, with no new charge; check the booking first |
| A failed attempt (declined payment, expired hold, nothing to pay) | the key is released, so a corrected retry can reuse it |
| Key older than `IDEMPOTENCY_HOURS` | forgotten and purged by the sweeper |

The request fingerprint is a SHA-256 of method, instrument and visit, so the store never keeps the instrument itself. In production the instrument would already be a gateway token, never a card number. Keys written by the previous release have no fingerprint or expiry and are retired at upgrade.

## Scaling notes

What was changed for scale, and what is still left.

**Done**

- **Search filters run in the database.** Area, service, rating, hourly rate and gender are pushed into one indexed query (`MaidQuery`), with `limit`/`offset` and an `X-Total-Count` header. A `maid_services` table (one row per maid and service) makes service and rate filters and aggregates indexable. Only skills and the requested time slot are checked afterwards.
- **Availability is read in bulk.** `find_busy_slots` returns the busy slots of many maids in one query, so a time-slot search no longer queries once per maid, and the start-time grid reads a whole day with one query. A test counts the SQL statements to keep it that way.
- **Home and details screens use an aggregate.** `GET /api/services/summary` returns the maid count and lowest rate per service from one `GROUP BY`, and `GET /api/localities` lists areas, instead of loading every maid.
- **Existing databases upgrade themselves.** On startup the new table is created and filled from stored maids, and the new indexes (case-insensitive area, rating, occurrence start) are added to tables that already exist.

**Measured** (3,000 maids and 9,000 bookings in local Postgres 16, called in-process, median of 3 to 5 runs, first page of 20; your numbers will differ, the ratios are the point):

| Request | Before | After |
|---|---|---|
| Search: one area, service, time slot | 2,479 ms | 45 ms |
| Search: all areas, service, time slot | 12,251 ms | 230 ms |
| Search: one area, service, no slot | 251 ms | 16 ms |
| Free-maid count for every start time on a day | 2,030 ms | 148 ms |

The old no-slot search also returned every match (about 500) instead of a page, so part of that gain is pagination.

**Still to do**

- A Postgres exclusion constraint on a maid's overlapping active occurrences, with a migration, as a second guard behind the advisory lock.
- Move the payment gateway call out of the maid lock.
- Move side effects (notifications, invoices) behind an outbox with workers.
- Shard or partition by city or maid. A booking only competes with other bookings for the same maid, so one maid's requests can go to one worker.
- Cache availability only as a hint with a short TTL and re-check in the database when booking; never validate on a read replica.
- Searching all areas with a time slot still checks every candidate maid; at larger sizes that needs the busy-slot check inside the SQL query, or a precomputed slot grid.
- Shed load in order: recommendations, search, reminders, and keep booking and payment last.

## Persistence and configuration

| Env var | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string. Unset = in-memory. `postgres://` and `postgresql://` are both accepted. Tables are created on startup. |
| `APP_TIMEZONE` | Business timezone for "now" and availability windows (default `Asia/Kolkata`; servers on Render run UTC). |
| `HOLD_MINUTES` | How long an unpaid booking holds the maid's slot (default 10). |
| `HOLD_SWEEP_SECONDS` | How often expired holds are swept (default 30, 0 turns the sweeper off). |
| `IDEMPOTENCY_HOURS` | How long a payment `Idempotency-Key` is remembered (default 24). |
| `TEST_DATABASE_URL` | Enables the Postgres runs of the test suite (the service tests run on both backends: 121 tests). |

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
| Discover | `GET /api/maids/search?locality=&serviceType=&date=&startTime=&durationMinutes=&minRating=&maxHourlyRate=&gender=&skills=&limit=&offset=` (default 50, max 100; total in `X-Total-Count`) |
| Book | `POST /api/bookings` |
| Get booking | `GET /api/bookings/{id}` |
| List a customer's bookings | `GET /api/bookings?customerId=` |
| Remove a maid | `DELETE /api/maids/{id}[?cancelUpcoming=true]` (409 `MAID_HAS_UPCOMING_BOOKINGS` if she has upcoming visits and the flag is not set) |
| Free-maid count per start time | `GET /api/availability/slots?date=&durationMinutes=&serviceType=&locality=` |
| Areas and per-service summary | `GET /api/localities`, `GET /api/services/summary?locality=` |
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
