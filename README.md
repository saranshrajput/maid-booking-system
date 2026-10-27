# Maid Booking System

Backend for a home-services platform: discover maids, book them (instant / scheduled / recurring), pay, and cancel with a refund policy. Java 17, Spring Boot 3, in-memory persistence.

## Build and run

```bash
mvn test                 # 36 unit + integration tests
mvn spring-boot:run      # http://localhost:8080
```

Swagger UI: `http://localhost:8080/swagger-ui.html`

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

```bash
# onboard
curl -XPOST localhost:8080/api/maids -H 'Content-Type: application/json' -d '{
  "name":"Asha","locality":"Koramangala","gender":"FEMALE","rating":4.5,
  "hourlyRates":{"CLEANING":200,"COOKING":250},"skills":["deep-cleaning"],
  "availability":[{"day":"SUNDAY","start":"08:00","end":"18:00"}]}'

# recurring booking: every Sunday 09:00, 4 times
curl -XPOST localhost:8080/api/bookings -H 'Content-Type: application/json' -d '{
  "customerId":"c1","maidId":"<id>","serviceType":"CLEANING","bookingType":"RECURRING","durationMinutes":60,
  "recurrence":{"daysOfWeek":["SUNDAY"],"startDate":"2030-01-06","startTime":"09:00","occurrences":4}}'

# pay (all unpaid occurrences, or pass "occurrenceId" for one)
curl -XPOST localhost:8080/api/bookings/<id>/payments -H 'Idempotency-Key: k1' -H 'Content-Type: application/json' \
  -d '{"method":"UPI","instrument":"asha@upi"}'
```

Mock gateway: an instrument starting with `fail` is declined; UPI needs `@`, card needs 12-19 digits, wallet any non-blank id.

## Design

```
domain/        Maid, Booking, BookingOccurrence, Payment, TimeSlot, AvailabilityWindow, RecurrenceRule (no Spring)
repository/    interfaces + in-memory implementations
booking/       BookingStrategy per type (Instant, Scheduled, Recurring) + registry
search/        MaidFilterProvider per filter + MaidSearchService
payment/       PaymentProcessor per method (mock gateway) + registry
pricing/       PricingStrategy (hourly)
cancellation/  CancellationPolicy (time-based refunds)
service/       orchestration: Booking, Payment, Cancellation, Availability, Maid
web/           controllers, DTOs, error mapping
```

- **Booking = occurrences.** Every booking owns a list of `BookingOccurrence`s (one for instant/scheduled, many for recurring). Availability, payment and cancellation all work per occurrence, which gives per-occurrence payment and single-vs-series cancellation with no special cases.
- **Extension points** (add one `@Component`, change nothing else): new booking type -> `BookingStrategy`; new payment method -> `PaymentProcessor`; new search filter -> `MaidFilterProvider`; new refund rules -> `CancellationPolicy`; dynamic pricing -> `PricingStrategy`. Enums (`BookingType`, `PaymentMethodType`) get one new constant.
- **State transitions.** Occurrence: `PENDING_PAYMENT -> CONFIRMED -> CANCELLED` (or `PENDING_PAYMENT -> CANCELLED`), enforced in the entity. `BookingStatus` is derived from its occurrences, so it cannot drift.
- **Availability.** A slot is free when it sits inside one of the maid's weekly windows and overlaps no active occurrence (half-open intervals, so back-to-back is fine). Search reuses the same check.
- **Concurrency.** Book, pay and cancel run under a per-maid lock (`MaidLockManager`), so check-then-save is atomic and concurrent requests cannot double-book; covered by a 16-thread test.
- **Idempotency.** `Idempotency-Key` on pay replays the original result without charging again; the lookup and charge happen under the maid lock.
- **Refunds.** `TimeBasedCancellationPolicy`: 24h+ before start 100%, 2h+ 50%, otherwise 0%. Unpaid occurrences cancel with no refund.

## Assumptions

- Slots are local date-times in the server's zone and cannot span midnight; availability windows are weekly and per day.
- Recurring bookings are all-or-nothing: if any generated occurrence is unavailable the whole booking is rejected. Occurrences whose start has already passed are skipped.
- Booking holds the slot immediately (`PENDING_PAYMENT`); payment confirms it. Recurring occurrences are paid individually, or all at once (one charge per occurrence).
- Instant booking starts at the current minute; it is still cancellable until it ends (refund 0%).
- Rating is supplied at onboarding. Skills filter requires all requested skills.
- Customers are just a `customerId` string (no auth, per scope).

## With more time

- Expire unpaid holds (TTL) so abandoned bookings free the slot.
- Occurrence `COMPLETED` state driven by a scheduler; rating updates from reviews.
- Dynamic/surge `PricingStrategy`, timezone-aware slots, pagination on search.
- Replace the per-maid in-process lock with optimistic locking / DB constraints for multi-instance deployment; persist idempotency keys with TTL.
- Retry/compensation for partial failures when paying a series.
