import hashlib
import threading
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Optional, TypeVar

from .booking_strategies import BookingCommand, BookingStrategyRegistry
from .cancellation_policy import CancellationPolicy
from .domain import (Booking, BookingOccurrence, Gender, Maid, OccurrenceStatus, Payment, PaymentMethodType,
                     PaymentStatus, ServiceType, TimeSlot)
from .exceptions import (HoldExpiredError, IdempotencyInProgressError, IdempotencyKeyReusedError, InvalidRequestError,
                         InvalidStateError, NotFoundError, PaymentFailedError, SlotUnavailableError)
from .payment_processors import PaymentProcessorRegistry
from .pricing import PricingStrategy
from .repositories import BookingRepository, IdempotencyStore, MaidRepository, PaymentRepository

T = TypeVar("T")
MAX_DURATION_MINUTES = 12 * 60


class LockManager(ABC):
    @abstractmethod
    def with_lock(self, maid_id: str, action: Callable[[], T]) -> T: ...


class MaidLockManager(LockManager):
    """Serialises every mutation of a maid's inventory (book, pay, cancel) behind one lock per maid."""

    def __init__(self):
        self._locks = defaultdict(threading.RLock)
        self._guard = threading.Lock()

    def with_lock(self, maid_id: str, action: Callable[[], T]) -> T:
        with self._guard:
            lock = self._locks[maid_id]
        with lock:
            return action()


@dataclass(frozen=True)
class HoldPolicy:
    """How long an unpaid booking holds the maid's slot, and how long a payment idempotency key is remembered."""
    ttl: timedelta = timedelta(minutes=10)
    idempotency_ttl: timedelta = timedelta(hours=24)


class AvailabilityService:
    def __init__(self, bookings: BookingRepository, clock: Callable[[], datetime]):
        self._bookings = bookings
        self._clock = clock

    def is_available(self, maid: Maid, slot: TimeSlot) -> bool:
        busy = self._bookings.find_busy_slots([maid.id], slot, self._clock())
        return maid.works_during(slot) and not busy.get(maid.id)

    def free_maids(self, maids: list[Maid], slot: TimeSlot) -> list[Maid]:
        """The maids free for `slot`, using one bookings query for all of them."""
        working = [m for m in maids if m.works_during(slot)]
        busy = self._bookings.find_busy_slots([m.id for m in working], slot, self._clock())
        return [m for m in working if not busy.get(m.id)]

    def start_time_counts(self, maids: list[Maid], day: date, duration_minutes: int, not_before: datetime,
                          step_minutes: int = 15, earliest: time = time(6, 0), latest: time = time(22, 0)
                          ) -> list[tuple[time, int]]:
        """For each candidate start time on `day`, how many of `maids` are free for `duration_minutes`.
        Starts that are not after `not_before` count as 0. One bookings query covers the whole day."""
        midnight = datetime.combine(day, time(0, 0))
        busy = self._bookings.find_busy_slots([m.id for m in maids], TimeSlot(midnight, midnight + timedelta(days=1)), not_before)
        counts, start, last = [], datetime.combine(day, earliest), datetime.combine(day, latest)
        while start <= last:
            slot = TimeSlot.of(start, duration_minutes)
            free = 0 if start <= not_before else sum(
                1 for m in maids if m.works_during(slot) and not any(b.overlaps(slot) for b in busy.get(m.id, [])))
            counts.append((start.time(), free))
            start += timedelta(minutes=step_minutes)
        return counts


@dataclass(frozen=True)
class OnboardMaidCommand:
    name: str
    locality: str
    gender: Gender
    rating: float
    hourly_rates: dict
    skills: frozenset
    availability: list


class MaidService:
    def __init__(self, maids: MaidRepository, bookings: Optional[BookingRepository] = None,
                 clock: Optional[Callable[[], datetime]] = None):
        self._maids = maids
        self._bookings = bookings
        self._clock = clock

    def onboard(self, c: OnboardMaidCommand) -> Maid:
        return self._maids.save(Maid(str(uuid.uuid4()), c.name, c.locality, c.gender, c.rating,
                                     c.hourly_rates, c.skills or frozenset(), c.availability))

    def get(self, id: str) -> Maid:
        maid = self._maids.find_by_id(id)
        if maid is None:
            raise NotFoundError(f"Maid not found: {id}")
        return maid

    def count_upcoming_visits(self, maid_id: str) -> int:
        """Active visits that have not finished yet."""
        now = self._clock()
        return sum(1 for b in self._bookings.find_by_maid_id(maid_id) for o in b.occurrences
                   if o.blocks(now) and o.slot.end > now)

    def deactivate(self, maid_id: str) -> Maid:
        """Hide the maid from search and booking. Old bookings keep her name."""
        return self._maids.save(replace(self.get(maid_id), active=False))


class BookingService:
    def __init__(self, maids: MaidService, bookings: BookingRepository, strategies: BookingStrategyRegistry,
                 availability: AvailabilityService, pricing: PricingStrategy, locks: LockManager,
                 clock: Callable[[], datetime], holds: HoldPolicy = HoldPolicy()):
        self._maids = maids
        self._bookings = bookings
        self._strategies = strategies
        self._availability = availability
        self._pricing = pricing
        self._locks = locks
        self._clock = clock
        self._holds = holds

    def book(self, cmd: BookingCommand) -> Booking:
        self._validate(cmd)
        maid = self._maids.get(cmd.maid_id)
        if not maid.active:
            raise InvalidRequestError(f"{maid.name} is no longer available")
        if not maid.offers(cmd.service_type):
            raise InvalidRequestError(f"{maid.name} does not offer {cmd.service_type.value}")
        now = self._clock()
        slots = self._strategies.get(cmd.booking_type).resolve_slots(cmd, now)

        # Check-then-save is atomic per maid, so concurrent requests cannot double-book.
        def create() -> Booking:
            for slot in slots:
                if not self._availability.is_available(maid, slot):
                    raise SlotUnavailableError(f"{maid.name} is not available for {slot.start} - {slot.end}")
            hold_until = now + self._holds.ttl  # unpaid occurrences stop blocking the maid at this time
            occurrences = [BookingOccurrence(str(uuid.uuid4()), s, self._pricing.price(maid, cmd.service_type, s), hold_until)
                           for s in slots]
            return self._bookings.save(Booking(str(uuid.uuid4()), cmd.customer_id, maid.id, cmd.service_type,
                                               cmd.booking_type, occurrences))

        return self._locks.with_lock(maid.id, create)

    def get(self, booking_id: str) -> Booking:
        booking = self._bookings.find_by_id(booking_id)
        if booking is None:
            raise NotFoundError(f"Booking not found: {booking_id}")
        return booking

    # Newest visit first, so upcoming bookings lead the list.
    def list_for_customer(self, customer_id: str) -> list[Booking]:
        bookings = self._bookings.find_by_customer_id(customer_id)
        return sorted(bookings, key=lambda b: min(o.slot.start for o in b.occurrences), reverse=True)

    @staticmethod
    def _validate(c: BookingCommand):
        if not c.customer_id or not c.customer_id.strip():
            raise InvalidRequestError("customerId is required")
        if not c.maid_id or c.service_type is None or c.booking_type is None:
            raise InvalidRequestError("maidId, serviceType and bookingType are required")
        if not 0 < c.duration_minutes <= MAX_DURATION_MINUTES:
            raise InvalidRequestError(f"Duration must be between 1 and {MAX_DURATION_MINUTES} minutes")


@dataclass(frozen=True)
class PayCommand:
    method: Optional[PaymentMethodType]
    instrument: str
    occurrence_id: Optional[str] = None  # None means "pay every unpaid occurrence".


class PaymentService:
    def __init__(self, bookings: BookingRepository, payments: PaymentRepository, idempotency: IdempotencyStore,
                 processors: PaymentProcessorRegistry, locks: LockManager, maids: MaidService,
                 availability: AvailabilityService, clock: Callable[[], datetime], holds: HoldPolicy = HoldPolicy()):
        self._bookings = bookings
        self._payments = payments
        self._idempotency = idempotency
        self._processors = processors
        self._locks = locks
        self._maids = maids
        self._availability = availability
        self._clock = clock
        self._holds = holds

    def pay(self, booking_id: str, cmd: PayCommand, idempotency_key: Optional[str] = None) -> list[Payment]:
        if cmd.method is None:
            raise InvalidRequestError("Payment method is required")
        booking = self._load(booking_id)
        processor = self._processors.get(cmd.method)
        key = f"{booking_id}:{idempotency_key}" if idempotency_key and idempotency_key.strip() else None
        fingerprint = self._fingerprint(cmd)

        # Same lock as booking/cancel, so the key lookup, the slot check and the charge are atomic per maid.
        def run() -> list[Payment]:
            booking = self._load(booking_id)  # Re-read under the lock so state is current.
            now = self._clock()
            if key:
                replay = self._replay(key, fingerprint, now)
                if replay is not None:
                    return replay
            targets = self._payable(booking, cmd.occurrence_id, now)
            self._check_slots_still_free(booking, targets, now)
            if key:
                self._idempotency.begin(key, fingerprint, now + self._holds.idempotency_ttl)
            try:
                payments = [self._charge(booking, o, cmd, processor, now) for o in targets]
            except Exception:
                if key:
                    self._idempotency.release(key)  # a failed attempt may be retried with the same key
                raise
            if key:
                self._idempotency.complete(key, [p.id for p in payments])
            return payments

        return self._locks.with_lock(booking.maid_id, run)

    # The same key with the same request returns the first result; with a different request it is an error.
    def _replay(self, key: str, fingerprint: str, now: datetime) -> Optional[list[Payment]]:
        record = self._idempotency.find(key, now)
        if record is None:
            return None
        if record.fingerprint is not None and record.fingerprint != fingerprint:
            raise IdempotencyKeyReusedError("This Idempotency-Key was already used with a different payment request")
        if record.state == IdempotencyStore.PROCESSING:
            raise IdempotencyInProgressError(
                "An earlier attempt with this Idempotency-Key did not finish. Check the booking before paying again")
        return self._payments.find_by_ids(list(record.payment_ids))

    # Not the card or UPI id itself in the clear: a hash of the request, so the store never keeps the instrument.
    @staticmethod
    def _fingerprint(cmd: PayCommand) -> str:
        raw = f"{cmd.method.value}|{cmd.instrument}|{cmd.occurrence_id or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # A hold that ran out (or was swept) can still be paid, but only while the slot is free: the maid may have been
    # booked by someone else in the meantime. All visits are checked before anything is charged.
    def _check_slots_still_free(self, booking: Booking, targets: list[BookingOccurrence], now: datetime) -> None:
        lapsed = [o for o in targets if o.status == OccurrenceStatus.EXPIRED or o.hold_lapsed(now)]
        if not lapsed:
            return
        maid = self._maids.get(booking.maid_id)
        for occurrence in lapsed:
            if not maid.active or not self._availability.is_available(maid, occurrence.slot):
                raise HoldExpiredError("Your hold on this slot expired and the slot is no longer free")

    def _charge(self, booking, occurrence, cmd, processor, now) -> Payment:
        if occurrence.status == OccurrenceStatus.EXPIRED or occurrence.hold_lapsed(now):
            occurrence.renew_hold(now + self._holds.ttl)  # the slot was just confirmed free
        result = processor.charge(occurrence.price, cmd.instrument)
        status = PaymentStatus.SUCCESS if result.success else PaymentStatus.FAILED
        payment = self._payments.save(Payment(str(uuid.uuid4()), booking.id, occurrence.id, occurrence.price,
                                              cmd.method, status, result.reference, result.failure_reason))
        if not result.success:
            self._bookings.save(booking)
            raise PaymentFailedError(result.failure_reason)
        occurrence.confirm()
        self._bookings.save(booking)
        return payment

    def _load(self, booking_id: str) -> Booking:
        booking = self._bookings.find_by_id(booking_id)
        if booking is None:
            raise NotFoundError(f"Booking not found: {booking_id}")
        return booking

    @staticmethod
    def _payable(booking: Booking, occurrence_id: Optional[str], now: datetime) -> list[BookingOccurrence]:
        payable = (OccurrenceStatus.PENDING_PAYMENT, OccurrenceStatus.EXPIRED)
        if occurrence_id is not None:
            target = next((o for o in booking.occurrences if o.id == occurrence_id), None)
            if target is None:
                raise NotFoundError(f"Occurrence not found: {occurrence_id}")
            if target.status not in payable:
                raise InvalidStateError(f"Occurrence {occurrence_id} is {target.status.value}, not payable")
            if target.slot.end <= now:
                raise HoldExpiredError("This visit time has already passed")
            return [target]
        unpaid = [o for o in booking.occurrences if o.status in payable and o.slot.end > now]
        if not unpaid:
            if any(o.status in payable for o in booking.occurrences):
                raise HoldExpiredError("This visit time has already passed")
            raise InvalidStateError(f"Nothing to pay for booking {booking.id}")
        return unpaid


class HoldExpiryService:
    """Marks unpaid holds that ran out as EXPIRED and forgets old idempotency keys. Availability already ignores a
    lapsed hold, so this is housekeeping that makes the state visible, not what frees the slot."""

    BATCH = 200

    def __init__(self, bookings: BookingRepository, idempotency: IdempotencyStore, locks: LockManager,
                 clock: Callable[[], datetime]):
        self._bookings = bookings
        self._idempotency = idempotency
        self._locks = locks
        self._clock = clock

    def sweep(self) -> tuple[int, int]:
        """Returns (visits expired, idempotency keys purged). Safe to run on every instance at once."""
        now, expired = self._clock(), 0

        def expire_in(booking_id: str) -> int:
            fresh = self._bookings.find_by_id(booking_id)
            lapsed = [o for o in fresh.occurrences if o.hold_lapsed(now)]
            for occurrence in lapsed:
                occurrence.expire()
            if lapsed:
                self._bookings.save(fresh)
            return len(lapsed)

        while True:
            batch = self._bookings.find_with_expired_holds(now, self.BATCH)
            done = sum(self._locks.with_lock(b.maid_id, lambda b=b: expire_in(b.id)) for b in batch)
            expired += done
            if not batch or not done:
                break
        return expired, self._idempotency.purge_expired(now)


@dataclass(frozen=True)
class CancellationResult:
    booking: Booking
    cancelled_occurrence_ids: list
    total_refund: Decimal


class CancellationService:
    def __init__(self, bookings: BookingRepository, payments: PaymentRepository,
                 processors: PaymentProcessorRegistry, policy: CancellationPolicy, locks: LockManager,
                 clock: Callable[[], datetime]):
        self._bookings = bookings
        self._payments = payments
        self._processors = processors
        self._policy = policy
        self._locks = locks
        self._clock = clock

    # occurrence_id None cancels every cancellable occurrence of the booking (the whole series).
    def cancel(self, booking_id: str, occurrence_id: Optional[str] = None) -> CancellationResult:
        booking = self._load(booking_id)

        def run() -> CancellationResult:
            booking = self._load(booking_id)  # Re-read under the lock so state is current.
            now = self._clock()
            targets = self._targets(booking, occurrence_id, now)
            total = Decimal("0")
            for occurrence in targets:
                total += self._refund(occurrence, now)
                occurrence.cancel()
            self._bookings.save(booking)
            return CancellationResult(booking, [o.id for o in targets], total)

        return self._locks.with_lock(booking.maid_id, run)

    def _load(self, booking_id: str) -> Booking:
        booking = self._bookings.find_by_id(booking_id)
        if booking is None:
            raise NotFoundError(f"Booking not found: {booking_id}")
        return booking

    def _targets(self, booking, occurrence_id, now) -> list[BookingOccurrence]:
        if occurrence_id is None:
            targets = [o for o in booking.occurrences if self._is_cancellable(o, now)]
            if not targets:
                raise InvalidStateError(f"Booking {booking.id} has nothing left to cancel")
            return targets
        target = next((o for o in booking.occurrences if o.id == occurrence_id), None)
        if target is None:
            raise NotFoundError(f"Occurrence not found: {occurrence_id}")
        if not self._is_cancellable(target, now):
            raise InvalidStateError(f"Occurrence {occurrence_id} cannot be cancelled ({target.status.value})")
        return [target]

    # Cancellable while active and not yet finished.
    @staticmethod
    def _is_cancellable(occurrence: BookingOccurrence, now: datetime) -> bool:
        return occurrence.blocks(now) and occurrence.slot.end > now

    # The maid is leaving, so the customer is not at fault: every unfinished visit is cancelled with a full refund.
    def cancel_upcoming_for_maid(self, maid_id: str) -> tuple[int, Decimal]:
        def run() -> tuple[int, Decimal]:
            now, cancelled, total = self._clock(), 0, Decimal("0")
            for booking in self._bookings.find_by_maid_id(maid_id):
                touched = False
                for occurrence in booking.occurrences:
                    if self._is_cancellable(occurrence, now):
                        total += self._refund(occurrence, now, full=True)
                        occurrence.cancel()
                        cancelled, touched = cancelled + 1, True
                if touched:
                    self._bookings.save(booking)
            return cancelled, total

        return self._locks.with_lock(maid_id, run)

    def _refund(self, occurrence: BookingOccurrence, now: datetime, full: bool = False) -> Decimal:
        payment = self._payments.find_captured_by_occurrence_id(occurrence.id)
        if payment is None:
            return Decimal("0")
        fraction = Decimal("1") if full else self._policy.refund_fraction(occurrence, now)
        amount = (payment.amount * fraction).quantize(
            Decimal("0.01"), ROUND_HALF_UP)
        if amount > 0:
            self._processors.get(payment.method).refund(payment.gateway_reference, amount)
            payment.record_refund(amount)
            self._payments.save(payment)
        return amount
