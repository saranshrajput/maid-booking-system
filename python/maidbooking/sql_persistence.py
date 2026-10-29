from __future__ import annotations

import threading
import zlib
from datetime import datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Numeric, String, create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload, sessionmaker

from .domain import (AvailabilityWindow, Booking, BookingOccurrence, BookingType, DayOfWeek, Gender, Maid,
                     OccurrenceStatus, Payment, PaymentMethodType, PaymentStatus, ServiceType, TimeSlot)
from .repositories import BookingRepository, IdempotencyStore, MaidRepository, PaymentRepository
from .services import LockManager, MaidLockManager


class Base(DeclarativeBase):
    pass


class MaidRow(Base):
    __tablename__ = "maids"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    locality: Mapped[str] = mapped_column(String(200), index=True)
    gender: Mapped[str] = mapped_column(String(20))
    rating: Mapped[float] = mapped_column(Float)
    hourly_rates: Mapped[dict] = mapped_column(JSON)
    skills: Mapped[list] = mapped_column(JSON)
    availability: Mapped[list] = mapped_column(JSON)


class OccurrenceRow(Base):
    __tablename__ = "booking_occurrences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20))


class BookingRow(Base):
    __tablename__ = "bookings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(100), index=True)
    maid_id: Mapped[str] = mapped_column(String(36), index=True)
    service_type: Mapped[str] = mapped_column(String(30))
    booking_type: Mapped[str] = mapped_column(String(20))
    occurrences: Mapped[list[OccurrenceRow]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by=OccurrenceRow.start_at)


class PaymentRow(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(36), index=True)
    occurrence_id: Mapped[str] = mapped_column(String(36), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    gateway_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    refunded_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))


class IdempotencyRow(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    payment_ids: Mapped[list] = mapped_column(JSON)


def normalize_url(url: str) -> str:
    """Render hands out postgres:// URLs; SQLAlchemy needs the driver spelled out."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def create_db_engine(url: str) -> Engine:
    return create_engine(normalize_url(url), pool_size=10, max_overflow=10, pool_pre_ping=True)


class SqlMaidRepository(MaidRepository):
    def __init__(self, engine: Engine):
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def save(self, maid: Maid) -> Maid:
        with self._sessions.begin() as s:
            s.merge(MaidRow(
                id=maid.id, name=maid.name, locality=maid.locality, gender=maid.gender.value, rating=maid.rating,
                hourly_rates={k.value: str(v) for k, v in maid.hourly_rates.items()}, skills=sorted(maid.skills),
                availability=[{"day": int(w.day), "start": w.start.isoformat(), "end": w.end.isoformat()}
                              for w in maid.availability]))
        return maid

    def find_by_id(self, id: str) -> Optional[Maid]:
        with self._sessions() as s:
            row = s.get(MaidRow, id)
            return self._to_domain(row) if row else None

    def find_all(self) -> list[Maid]:
        with self._sessions() as s:
            return [self._to_domain(r) for r in s.scalars(select(MaidRow))]

    @staticmethod
    def _to_domain(r: MaidRow) -> Maid:
        return Maid(r.id, r.name, r.locality, Gender(r.gender), r.rating,
                    {ServiceType(k): Decimal(v) for k, v in r.hourly_rates.items()}, frozenset(r.skills),
                    [AvailabilityWindow(DayOfWeek(w["day"]), time.fromisoformat(w["start"]),
                                        time.fromisoformat(w["end"])) for w in r.availability])


class SqlBookingRepository(BookingRepository):
    def __init__(self, engine: Engine):
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def save(self, booking: Booking) -> Booking:
        with self._sessions.begin() as s:
            s.merge(BookingRow(
                id=booking.id, customer_id=booking.customer_id, maid_id=booking.maid_id,
                service_type=booking.service_type.value, booking_type=booking.booking_type.value,
                occurrences=[OccurrenceRow(id=o.id, booking_id=booking.id, start_at=o.slot.start, end_at=o.slot.end,
                                           price=o.price, status=o.status.value) for o in booking.occurrences]))
        return booking

    def find_by_id(self, id: str) -> Optional[Booking]:
        with self._sessions() as s:
            row = s.get(BookingRow, id)
            return self._to_domain(row) if row else None

    def find_by_maid_id(self, maid_id: str) -> list[Booking]:
        with self._sessions() as s:
            rows = s.scalars(select(BookingRow).where(BookingRow.maid_id == maid_id))
            return [self._to_domain(r) for r in rows]

    def find_by_customer_id(self, customer_id: str) -> list[Booking]:
        with self._sessions() as s:
            rows = s.scalars(select(BookingRow).where(BookingRow.customer_id == customer_id))
            return [self._to_domain(r) for r in rows]

    @staticmethod
    def _to_domain(r: BookingRow) -> Booking:
        occurrences = []
        for o in r.occurrences:
            occurrence = BookingOccurrence(o.id, TimeSlot(o.start_at, o.end_at), Decimal(o.price))
            occurrence.status = OccurrenceStatus(o.status)
            occurrences.append(occurrence)
        return Booking(r.id, r.customer_id, r.maid_id, ServiceType(r.service_type), BookingType(r.booking_type),
                       occurrences)


class SqlPaymentRepository(PaymentRepository):
    def __init__(self, engine: Engine):
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def save(self, payment: Payment) -> Payment:
        with self._sessions.begin() as s:
            s.merge(PaymentRow(
                id=payment.id, booking_id=payment.booking_id, occurrence_id=payment.occurrence_id,
                amount=payment.amount, method=payment.method.value, status=payment.status.value,
                gateway_reference=payment.gateway_reference, failure_reason=payment.failure_reason,
                refunded_amount=payment.refunded_amount))
        return payment

    def find_captured_by_occurrence_id(self, occurrence_id: str) -> Optional[Payment]:
        with self._sessions() as s:
            row = s.scalars(select(PaymentRow).where(PaymentRow.occurrence_id == occurrence_id,
                                                     PaymentRow.status != PaymentStatus.FAILED.value)).first()
            return self._to_domain(row) if row else None

    def find_by_ids(self, ids: list[str]) -> list[Payment]:
        with self._sessions() as s:
            rows = {r.id: r for r in s.scalars(select(PaymentRow).where(PaymentRow.id.in_(ids)))}
            return [self._to_domain(rows[i]) for i in ids if i in rows]

    @staticmethod
    def _to_domain(r: PaymentRow) -> Payment:
        return Payment(r.id, r.booking_id, r.occurrence_id, Decimal(r.amount), PaymentMethodType(r.method),
                       PaymentStatus(r.status), r.gateway_reference, r.failure_reason, Decimal(r.refunded_amount))


class SqlIdempotencyStore(IdempotencyStore):
    def __init__(self, engine: Engine, payments: SqlPaymentRepository):
        self._sessions = sessionmaker(engine, expire_on_commit=False)
        self._payments = payments

    def find(self, key: str) -> Optional[list[Payment]]:
        with self._sessions() as s:
            row = s.get(IdempotencyRow, key)
        return self._payments.find_by_ids(row.payment_ids) if row else None

    def save(self, key: str, result: list[Payment]) -> None:
        with self._sessions.begin() as s:
            s.merge(IdempotencyRow(key=key, payment_ids=[p.id for p in result]))


class PostgresAdvisoryLockManager(LockManager):
    """Per-maid lock that holds across app instances: an in-process lock first, then a Postgres advisory lock."""

    MAX_CONCURRENT_HOLDERS = 8  # Each holder keeps one pooled connection checked out while it works.

    def __init__(self, engine: Engine):
        self._engine = engine
        self._local = MaidLockManager()
        self._holders = threading.BoundedSemaphore(self.MAX_CONCURRENT_HOLDERS)

    def with_lock(self, maid_id: str, action):
        return self._local.with_lock(maid_id, lambda: self._with_db_lock(maid_id, action))

    def _with_db_lock(self, maid_id: str, action):
        key = zlib.crc32(maid_id.encode())
        with self._holders, self._engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})
            try:
                return action()
            finally:
                try:
                    conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                except Exception:
                    conn.invalidate()  # A dropped connection releases its session locks on the server.
                    raise


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
