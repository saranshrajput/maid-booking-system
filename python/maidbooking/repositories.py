from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Optional

from .domain import Booking, Maid, Payment


class MaidRepository(ABC):
    @abstractmethod
    def save(self, maid: Maid) -> Maid: ...

    @abstractmethod
    def find_by_id(self, id: str) -> Optional[Maid]: ...

    @abstractmethod
    def find_all(self) -> list[Maid]: ...


class BookingRepository(ABC):
    @abstractmethod
    def save(self, booking: Booking) -> Booking: ...

    @abstractmethod
    def find_by_id(self, id: str) -> Optional[Booking]: ...

    @abstractmethod
    def find_by_maid_id(self, maid_id: str) -> list[Booking]: ...


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

    def find_all(self):
        with self._lock:
            return list(self._store.values())


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
