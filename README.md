# Maid Booking System (Python)

Python 3.10+ / FastAPI backend for the Rupeek SDE-3 machine-coding question (Maid Booking System). In-memory persistence.

## Build and run

```bash
cd python && pip install -r requirements.txt
python -m pytest                          # 37 unit + API tests
uvicorn maidbooking.api:app --reload      # http://localhost:8000, docs at /docs
```

## API

| Operation | Endpoint |
|---|---|
| Add maid | `POST /api/maids` |
| Get maid | `GET /api/maids/{id}` |
| Discover | `GET /api/maids/search?locality=&serviceType=&date=&startTime=&durationMinutes=&minRating=&maxHourlyRate=&gender=&skills=` |
| Book | `POST /api/bookings` |
| Get booking | `GET /api/bookings/{id}` |
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
