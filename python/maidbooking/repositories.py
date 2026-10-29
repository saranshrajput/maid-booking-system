from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .domain import Booking, Gender, Maid, Payment, ServiceType, TimeSlot


@dataclass(frozen=True)
class MaidQuery:
    """The search attributes a repository can filter on itself, so a database can use indexes and paginate."""
    locality: Optional[str] = None
    service_type: Optional[ServiceType] = None
    gender: Optional[Gender] = None
    min_rating: Optional[float] = None
    max_hourly_rate: Optional[Decimal] = None

    # With a service type the cap applies to that service's rate, otherwise to any offered rate.
    def matches(self, m: Maid) -> bool:
        if not m.active:
            return False
        if self.locality and not m.serves_locality(self.locality):
            return False
        if self.gender and m.gender != self.gender:
            return False
        if self.min_rating is not None and m.rating < self.min_rating:
            return False
        if self.service_type and not m.offers(self.service_type):
            return False
        if self.max_hourly_rate is not None:
            rates = [m.hourly_rates[self.service_type]] if self.service_type else m.hourly_rates.values()
            return any(r <= self.max_hourly_rate for r in rates)
        return True


class MaidRepository(ABC):
    @abstractmethod
    def save(self, maid: Maid) -> Maid: ...

    @abstractmethod
    def find_by_id(self, id: str) -> Optional[Maid]: ...

    @abstractmethod
    def search(self, query: MaidQuery, limit: Optional[int] = None, offset: int = 0) -> list[Maid]:
        """Maids matching the query, best rated first then by name."""

    @abstractmethod
    def count(self, query: MaidQuery) -> int: ...

    @abstractmethod
    def localities(self) -> list[str]: ...

    @abstractmethod
    def service_summary(self, locality: Optional[str]) -> dict[ServiceType, tuple[int, Decimal]]:
        """Per service: how many maids offer it and the lowest hourly rate, optionally within one area."""


class BookingRepository(ABC):
    @abstractmethod
    def save(self, booking: Booking) -> Booking: ...

    @abstractmethod
    def find_by_id(self, id: str) -> Optional[Booking]: ...

    @abstractmethod
    def find_by_maid_id(self, maid_id: str) -> list[Booking]: ...

    @abstractmethod
    def find_busy_slots(self, maid_ids: list[str], window: TimeSlot, now: datetime) -> dict[str, list[TimeSlot]]:
        """Slots that keep each maid busy at `now` and overlap `window`, for many maids in one call: confirmed
        occurrences and unpaid ones whose hold has not lapsed (cancelled and expired ones never block)."""

    @abstractmethod
    def find_with_expired_holds(self, now: datetime, limit: int) -> list[Booking]:
        """Bookings with at least one unpaid occurrence whose hold has lapsed, for the expiry sweeper."""

    @abstractmethod
    def find_by_customer_id(self, customer_id: str) -> list[Booking]: ...


class PaymentRepository(ABC):
    @abstractmethod
    def save(self, payment: Payment) -> Payment: ...

    @abstractmethod
    def find_captured_by_occurrence_id(self, occurrence_id: str) -> Optional[Payment]: ...

    @abstractmethod
    def find_by_ids(self, ids: list[str]) -> list[Payment]: ...


@dataclass(frozen=True)
class IdempotencyRecord:
    key: str
    fingerprint: Optional[str]      # hash of the request; None for records written by older releases
    state: str                      # PROCESSING while the first attempt runs, COMPLETED afterwards
    payment_ids: tuple
    expires_at: datetime


class IdempotencyStore(ABC):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"

    @abstractmethod
    def find(self, key: str, now: datetime) -> Optional[IdempotencyRecord]:
        """The live record for the key, or None when there is none or it has expired."""

    @abstractmethod
    def begin(self, key: str, fingerprint: str, expires_at: datetime) -> None:
        """Mark the key as being processed (replacing an expired record, if any)."""

    @abstractmethod
    def complete(self, key: str, payment_ids: list[str]) -> None: ...

    @abstractmethod
    def release(self, key: str) -> None:
        """Forget the key, so a failed attempt can be retried."""

    @abstractmethod
    def purge_expired(self, now: datetime) -> int: ...


class InMemoryMaidRepository(MaidRepository):
    def __init__(self):
        self._store: dict[str, Maid] = {}
        self._lock = threading.Lock()

    def save(self, maid):
        with self._lock:
            self._store[maid.id] = maid
        return maid

    def find_by_id(self, id):
        return self._store.get(id)

    def search(self, query, limit=None, offset=0):
        with self._lock:
            matches = [m for m in self._store.values() if query.matches(m)]
        matches.sort(key=lambda m: (-m.rating, m.name))
        return matches[offset:offset + limit] if limit else matches[offset:]

    def count(self, query):
        with self._lock:
            return sum(1 for m in self._store.values() if query.matches(m))

    def localities(self):
        with self._lock:
            return sorted({m.locality for m in self._store.values() if m.active})

    def service_summary(self, locality):
        summary: dict = {}
        with self._lock:
            maids = list(self._store.values())
        for m in maids:
            if not m.active or (locality and not m.serves_locality(locality)):
                continue
            for service, rate in m.hourly_rates.items():
                count, lowest = summary.get(service, (0, rate))
                summary[service] = (count + 1, min(lowest, rate))
        return summary


class InMemoryBookingRepository(BookingRepository):
    def __init__(self):
        self._store: dict[str, Booking] = {}
        self._lock = threading.Lock()

    def save(self, booking):
        with self._lock:
            self._store[booking.id] = booking
        return booking

    def find_by_id(self, id):
        return self._store.get(id)

    def find_by_maid_id(self, maid_id):
        with self._lock:
            return [b for b in self._store.values() if b.maid_id == maid_id]

    def find_by_customer_id(self, customer_id):
        with self._lock:
            return [b for b in self._store.values() if b.customer_id == customer_id]

    def find_busy_slots(self, maid_ids, window, now):
        wanted = set(maid_ids)
        with self._lock:
            bookings = [b for b in self._store.values() if b.maid_id in wanted]
        busy: dict = {}
        for b in bookings:
            for o in b.occurrences:
                if o.blocks(now) and o.slot.overlaps(window):
                    busy.setdefault(b.maid_id, []).append(o.slot)
        return busy

    def find_with_expired_holds(self, now, limit):
        with self._lock:
            found = [b for b in self._store.values() if any(o.hold_lapsed(now) for o in b.occurrences)]
        return found[:limit]


class InMemoryPaymentRepository(PaymentRepository):
    def __init__(self):
        self._store: dict[str, Payment] = {}
        self._lock = threading.Lock()

    def save(self, payment):
        with self._lock:
            self._store[payment.id] = payment
        return payment

    def find_captured_by_occurrence_id(self, occurrence_id):
        with self._lock:
            return next((p for p in self._store.values()
                         if p.occurrence_id == occurrence_id and p.is_captured), None)

    def find_by_ids(self, ids):
        with self._lock:
            return [self._store[i] for i in ids if i in self._store]


class InMemoryIdempotencyStore(IdempotencyStore):
    def __init__(self):
        self._store: dict[str, IdempotencyRecord] = {}
        self._lock = threading.Lock()

    def find(self, key, now):
        with self._lock:
            record = self._store.get(key)
        return record if record and record.expires_at > now else None

    def begin(self, key, fingerprint, expires_at):
        with self._lock:
            self._store[key] = IdempotencyRecord(key, fingerprint, self.PROCESSING, (), expires_at)

    def complete(self, key, payment_ids):
        with self._lock:
            record = self._store[key]
            self._store[key] = IdempotencyRecord(key, record.fingerprint, self.COMPLETED, tuple(payment_ids), record.expires_at)

    def release(self, key):
        with self._lock:
            self._store.pop(key, None)

    def purge_expired(self, now):
        with self._lock:
            stale = [k for k, r in self._store.items() if r.expires_at <= now]
            for k in stale:
                del self._store[k]
        return len(stale)
