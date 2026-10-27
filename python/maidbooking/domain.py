from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum, IntEnum

from .exceptions import InvalidRequestError, InvalidStateError


class DayOfWeek(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class Gender(str, Enum):
    FEMALE = "FEMALE"
    MALE = "MALE"
    OTHER = "OTHER"


class ServiceType(str, Enum):
    CLEANING = "CLEANING"
    COOKING = "COOKING"
    DISHWASHING = "DISHWASHING"
    LAUNDRY = "LAUNDRY"
    BABYSITTING = "BABYSITTING"


class BookingType(str, Enum):
    INSTANT = "INSTANT"
    SCHEDULED = "SCHEDULED"
    RECURRING = "RECURRING"


class OccurrenceStatus(str, Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class BookingStatus(str, Enum):
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class PaymentMethodType(str, Enum):
    CARD = "CARD"
    UPI = "UPI"
    WALLET = "WALLET"


class PaymentStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


@dataclass(frozen=True)
class TimeSlot:
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.end <= self.start:
            raise InvalidRequestError("Time slot must have an end after its start")

    @staticmethod
    def of(start: datetime, duration_minutes: int) -> TimeSlot:
        if duration_minutes <= 0:
            raise InvalidRequestError("Duration must be positive")
        return TimeSlot(start, start + timedelta(minutes=duration_minutes))

    # Half-open interval overlap, so back-to-back slots do not conflict.
    def overlaps(self, other: TimeSlot) -> bool:
        return self.start < other.end and other.start < self.end

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass(frozen=True)
class AvailabilityWindow:
    """A recurring weekly working window, e.g. MONDAY 09:00-17:00."""
    day: DayOfWeek
    start: time
    end: time

    def __post_init__(self):
        if self.end <= self.start:
            raise InvalidRequestError("Availability window needs an end time after its start")

    def covers(self, slot: TimeSlot) -> bool:
        if slot.start.date() != slot.end.date():
            return False
        return (slot.start.weekday() == self.day
                and slot.start.time() >= self.start
                and slot.end.time() <= self.end)


@dataclass(frozen=True)
class RecurrenceRule:
    """Repeats on the given weekdays at start_time from start_date until `occurrences` slots exist."""
    days_of_week: frozenset
    start_date: date
    start_time: time
    occurrences: int

    MAX_OCCURRENCES = 52

    def __post_init__(self):
        if not self.days_of_week:
            raise InvalidRequestError("Recurrence needs at least one day of week")
        if not 1 <= self.occurrences <= self.MAX_OCCURRENCES:
            raise InvalidRequestError(f"Recurrence occurrences must be between 1 and {self.MAX_OCCURRENCES}")
        object.__setattr__(self, "days_of_week", frozenset(self.days_of_week))


@dataclass(frozen=True)
class Maid:
    id: str
    name: str
    locality: str
    gender: Gender
    rating: float
    hourly_rates: dict
    skills: frozenset
    availability: tuple

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise InvalidRequestError("Maid name is required")
        if not self.locality or not self.locality.strip():
            raise InvalidRequestError("Maid locality is required")
        if not 0 <= self.rating <= 5:
            raise InvalidRequestError("Rating must be between 0 and 5")
        if not self.hourly_rates:
            raise InvalidRequestError("Maid must offer at least one service with a rate")
        if any(Decimal(r) <= 0 for r in self.hourly_rates.values()):
            raise InvalidRequestError("Hourly rates must be positive")
        if not self.availability:
            raise InvalidRequestError("Maid must have at least one availability window")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "locality", self.locality.strip())
        object.__setattr__(self, "hourly_rates", {k: Decimal(v) for k, v in self.hourly_rates.items()})
        object.__setattr__(self, "skills", frozenset(s.strip().lower() for s in self.skills))
        object.__setattr__(self, "availability", tuple(self.availability))

    def offers(self, service: ServiceType) -> bool:
        return service in self.hourly_rates

    def serves_locality(self, locality: str) -> bool:
        return self.locality.lower() == locality.strip().lower()

    def has_skills(self, required) -> bool:
        return {s.strip().lower() for s in required} <= self.skills

    def works_during(self, slot: TimeSlot) -> bool:
        return any(w.covers(slot) for w in self.availability)

    def rate_for(self, service: ServiceType) -> Decimal:
        if service not in self.hourly_rates:
            raise InvalidRequestError(f"{self.name} does not offer {service.value}")
        return self.hourly_rates[service]


class BookingOccurrence:
    """One bookable slot; instant/scheduled bookings have one, recurring bookings have many."""

    def __init__(self, id: str, slot: TimeSlot, price: Decimal):
        self.id = id
        self.slot = slot
        self.price = price
        self.status = OccurrenceStatus.PENDING_PAYMENT

    def confirm(self):
        if self.status != OccurrenceStatus.PENDING_PAYMENT:
            raise InvalidStateError(f"Occurrence {self.id} cannot be confirmed from {self.status.value}")
        self.status = OccurrenceStatus.CONFIRMED

    def cancel(self):
        if self.status == OccurrenceStatus.CANCELLED:
            raise InvalidStateError(f"Occurrence {self.id} is already cancelled")
        self.status = OccurrenceStatus.CANCELLED

    # Active occurrences hold the maid's slot.
    @property
    def is_active(self) -> bool:
        return self.status != OccurrenceStatus.CANCELLED


@dataclass
class Booking:
    id: str
    customer_id: str
    maid_id: str
    service_type: ServiceType
    booking_type: BookingType
    occurrences: list

    # Derived from occurrences so it can never drift out of sync.
    @property
    def status(self) -> BookingStatus:
        if not any(o.is_active for o in self.occurrences):
            return BookingStatus.CANCELLED
        if any(o.status == OccurrenceStatus.PENDING_PAYMENT for o in self.occurrences):
            return BookingStatus.AWAITING_PAYMENT
        return BookingStatus.CONFIRMED


@dataclass
class Payment:
    id: str
    booking_id: str
    occurrence_id: str
    amount: Decimal
    method: PaymentMethodType
    status: PaymentStatus
    gateway_reference: str | None = None
    failure_reason: str | None = None
    refunded_amount: Decimal = Decimal("0")
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def record_refund(self, refund: Decimal):
        with self._lock:
            self.refunded_amount += refund
            self.status = (PaymentStatus.REFUNDED if self.refunded_amount >= self.amount
                           else PaymentStatus.PARTIALLY_REFUNDED)

    @property
    def is_captured(self) -> bool:
        return self.status != PaymentStatus.FAILED
