from __future__ import annotations

import threading
import zlib
from datetime import datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import (JSON, DateTime, Float, ForeignKey, Index, Numeric, String, create_engine, delete, distinct, func,
                        select, text)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload, sessionmaker

from .domain import (AvailabilityWindow, Booking, BookingOccurrence, BookingType, DayOfWeek, Gender, Maid,
                     OccurrenceStatus, Payment, PaymentMethodType, PaymentStatus, ServiceType, TimeSlot)
from .repositories import BookingRepository, IdempotencyStore, MaidQuery, MaidRepository, PaymentRepository
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


class MaidServiceRow(Base):
    """One row per (maid, service) so searches can filter and aggregate by service and rate with an index."""
    __tablename__ = "maid_services"
    maid_id: Mapped[str] = mapped_column(ForeignKey("maids.id"), primary_key=True)
    service_type: Mapped[str] = mapped_column(String(30), primary_key=True)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    __table_args__ = (Index("ix_maid_services_type_rate", "service_type", "hourly_rate"),)


class OccurrenceRow(Base):
    __tablename__ = "booking_occurrences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
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


# Case-insensitive area lookups use this index (queries compare lower(locality)).
Index("ix_maids_locality_lower", func.lower(MaidRow.locality))
Index("ix_maids_rating", MaidRow.rating)


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


def _service_rows(maid_id: str, rates: dict) -> list[MaidServiceRow]:
    return [MaidServiceRow(maid_id=maid_id, service_type=str(getattr(k, "value", k)), hourly_rate=Decimal(str(v)))
            for k, v in rates.items()]


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
            s.flush()
            s.execute(delete(MaidServiceRow).where(MaidServiceRow.maid_id == maid.id))
            s.add_all(_service_rows(maid.id, maid.hourly_rates))
        return maid

    def find_by_id(self, id: str) -> Optional[Maid]:
        with self._sessions() as s:
            row = s.get(MaidRow, id)
            return self._to_domain(row) if row else None

    @staticmethod
    def _filtered(q: MaidQuery):
        stmt = select(MaidRow)
        if q.locality:
            stmt = stmt.where(func.lower(MaidRow.locality) == q.locality.strip().lower())
        if q.gender:
            stmt = stmt.where(MaidRow.gender == q.gender.value)
        if q.min_rating is not None:
            stmt = stmt.where(MaidRow.rating >= q.min_rating)
        if q.service_type or q.max_hourly_rate is not None:
            offered = select(MaidServiceRow.maid_id)
            if q.service_type:
                offered = offered.where(MaidServiceRow.service_type == q.service_type.value)
            if q.max_hourly_rate is not None:
                offered = offered.where(MaidServiceRow.hourly_rate <= q.max_hourly_rate)
            stmt = stmt.where(MaidRow.id.in_(offered))
        return stmt

    def search(self, query: MaidQuery, limit: Optional[int] = None, offset: int = 0) -> list[Maid]:
        stmt = self._filtered(query).order_by(MaidRow.rating.desc(), MaidRow.name)
        if limit:
            stmt = stmt.limit(limit)
        if offset:
            stmt = stmt.offset(offset)
        with self._sessions() as s:
            return [self._to_domain(r) for r in s.scalars(stmt)]

    def count(self, query: MaidQuery) -> int:
        with self._sessions() as s:
            return s.scalar(select(func.count()).select_from(self._filtered(query).subquery())) or 0

    def localities(self) -> list[str]:
        with self._sessions() as s:
            return list(s.scalars(select(distinct(MaidRow.locality)).order_by(MaidRow.locality)))

    def service_summary(self, locality: Optional[str]) -> dict:
        stmt = select(MaidServiceRow.service_type, func.count(), func.min(MaidServiceRow.hourly_rate)).group_by(
            MaidServiceRow.service_type)
        if locality and locality.strip():
            stmt = stmt.join(MaidRow, MaidRow.id == MaidServiceRow.maid_id).where(
                func.lower(MaidRow.locality) == locality.strip().lower())
        with self._sessions() as s:
            return {ServiceType(t): (n, Decimal(rate)) for t, n, rate in s.execute(stmt)}

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

    def find_busy_slots(self, maid_ids: list[str], window: TimeSlot) -> dict:
        if not maid_ids:
            return {}
        stmt = (select(BookingRow.maid_id, OccurrenceRow.start_at, OccurrenceRow.end_at)
                .join(OccurrenceRow, OccurrenceRow.booking_id == BookingRow.id)
                .where(BookingRow.maid_id.in_(maid_ids), OccurrenceRow.status != OccurrenceStatus.CANCELLED.value,
                       OccurrenceRow.start_at < window.end, OccurrenceRow.end_at > window.start))
        busy: dict = {}
        with self._sessions() as s:
            for maid_id, start, end in s.execute(stmt):
                busy.setdefault(maid_id, []).append(TimeSlot(start, end))
        return busy

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
    # create_all skips tables that already exist, so add any newer indexes to them explicitly.
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(engine, checkfirst=True)
    backfill_service_rows(engine)


def backfill_service_rows(engine: Engine) -> None:
    """Maids saved before the maid_services table existed get their rows built from their stored rates."""
    with sessionmaker(engine).begin() as s:
        for row in s.scalars(select(MaidRow).where(~MaidRow.id.in_(select(MaidServiceRow.maid_id)))):
            s.add_all(_service_rows(row.id, row.hourly_rates))
