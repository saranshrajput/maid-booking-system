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
    def find_busy_slots(self, maid_ids: list[str], window: TimeSlot) -> dict[str, list[TimeSlot]]:
        """Active (not cancelled) occurrence slots overlapping `window`, for many maids in one call."""

    @abstractmethod
    def find_by_customer_id(self, customer_id: str) -> list[Booking]: ...


class PaymentRepository(ABC):
    @abstractmethod
    def save(self, payment: Payment) -> Payment: ...

    @abstractmethod
    def find_captured_by_occurrence_id(self, occurrence_id: str) -> Optional[Payment]: ...

    @abstractmethod
    def find_by_ids(self, ids: list[str]) -> list[Payment]: ...


class IdempotencyStore(ABC):
    @abstractmethod
    def find(self, key: str) -> Optional[list[Payment]]: ...

    @abstractmethod
    def save(self, key: str, result: list[Payment]) -> None: ...


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

    def find_busy_slots(self, maid_ids, window):
        wanted = set(maid_ids)
        with self._lock:
            bookings = [b for b in self._store.values() if b.maid_id in wanted]
        busy: dict = {}
        for b in bookings:
            for o in b.occurrences:
                if o.is_active and o.slot.overlaps(window):
                    busy.setdefault(b.maid_id, []).append(o.slot)
        return busy


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
        self._store: dict[str, list[Payment]] = {}

    def find(self, key):
        return self._store.get(key)

    def save(self, key, result):
        self._store[key] = list(result)
