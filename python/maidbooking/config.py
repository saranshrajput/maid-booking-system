import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .repositories import (InMemoryBookingRepository, InMemoryIdempotencyStore, InMemoryMaidRepository,
                           InMemoryPaymentRepository)
from .services import MaidLockManager


@dataclass
class Infrastructure:
    maids: object
    bookings: object
    payments: object
    idempotency: object
    locks: object
    engine: object = None  # Set only for the Postgres backend.

    @property
    def storage(self) -> str:
        return "postgres" if self.engine is not None else "memory"


def build_infrastructure(database_url: Optional[str]) -> Infrastructure:
    """Postgres when a DATABASE_URL is given (Render sets it), otherwise in-memory."""
    if not database_url:
        return Infrastructure(InMemoryMaidRepository(), InMemoryBookingRepository(), InMemoryPaymentRepository(),
                              InMemoryIdempotencyStore(), MaidLockManager())
    from .sql_persistence import (PostgresAdvisoryLockManager, SqlBookingRepository, SqlIdempotencyStore,
                                  SqlMaidRepository, SqlPaymentRepository, create_db_engine, create_schema)
    engine = create_db_engine(database_url)
    create_schema(engine)
    payments = SqlPaymentRepository(engine)
    return Infrastructure(SqlMaidRepository(engine), SqlBookingRepository(engine), payments,
                          SqlIdempotencyStore(engine), PostgresAdvisoryLockManager(engine), engine)


def local_clock(timezone: Optional[str] = None) -> Callable[[], datetime]:
    """Naive 'now' in the business timezone, so the server's own zone (UTC on Render) does not matter."""
    zone = ZoneInfo(timezone or os.getenv("APP_TIMEZONE", "Asia/Kolkata"))
    return lambda: datetime.now(zone).replace(tzinfo=None)
