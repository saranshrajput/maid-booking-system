import os
import sys
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maidbooking.booking_strategies import (BookingCommand, BookingStrategyRegistry, InstantBookingStrategy,  # noqa: E402
                                            RecurringBookingStrategy, ScheduledBookingStrategy)
from maidbooking.cancellation_policy import TimeBasedCancellationPolicy  # noqa: E402
from maidbooking.domain import AvailabilityWindow, BookingType, DayOfWeek, Gender, ServiceType  # noqa: E402
from maidbooking.payment_processors import (CardPaymentProcessor, PaymentProcessorRegistry,  # noqa: E402
                                            UpiPaymentProcessor, WalletPaymentProcessor)
from maidbooking.pricing import HourlyPricingStrategy  # noqa: E402
from maidbooking.config import build_infrastructure  # noqa: E402
from maidbooking.search import MaidSearchService, standard_providers  # noqa: E402
from maidbooking.services import (AvailabilityService, BookingService, CancellationService,  # noqa: E402
                                  MaidService, OnboardMaidCommand, PaymentService)

NOW = datetime(2030, 1, 7, 10, 0)  # Monday
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")  # Postgres runs of the suite are skipped when unset.


def reset_database(url: str):
    from sqlalchemy import text
    from maidbooking.sql_persistence import create_db_engine
    engine = create_db_engine(url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE idempotency_keys, payments, booking_occurrences, bookings, maids"))
    engine.dispose()


class Ctx:
    """Real services over in-memory repositories with a fixed clock."""

    def __init__(self, database_url=None, reset=True):
        clock = lambda: NOW  # noqa: E731
        infra = build_infrastructure(database_url)
        if database_url and reset:
            reset_database(database_url)
        self.maid_repo, self.booking_repo, self.payment_repo = infra.maids, infra.bookings, infra.payments
        self.maids = MaidService(self.maid_repo)
        self.availability = AvailabilityService(self.booking_repo)
        locks = infra.locks
        processors = PaymentProcessorRegistry([CardPaymentProcessor(), UpiPaymentProcessor(),
                                               WalletPaymentProcessor()])
        strategies = BookingStrategyRegistry([InstantBookingStrategy(), ScheduledBookingStrategy(),
                                              RecurringBookingStrategy()])
        self.bookings = BookingService(self.maids, self.booking_repo, strategies, self.availability,
                                       HourlyPricingStrategy(), locks, clock)
        self.payments = PaymentService(self.booking_repo, self.payment_repo, infra.idempotency,
                                       processors, locks)
        self.cancellations = CancellationService(self.booking_repo, self.payment_repo, processors,
                                                 TimeBasedCancellationPolicy(), locks, clock)
        self.search = MaidSearchService(self.maid_repo, standard_providers(self.availability))

    # Works 08:00-20:00 every day, CLEANING only.
    def maid(self, name="Asha", locality="Koramangala", gender=Gender.FEMALE, rating=4.5, rate="200", *skills):
        windows = [AvailabilityWindow(d, time(8), time(20)) for d in DayOfWeek]
        return self.maids.onboard(OnboardMaidCommand(name, locality, gender, rating,
                                                     {ServiceType.CLEANING: Decimal(rate)}, frozenset(skills), windows))

    def book_scheduled(self, maid, start, minutes):
        return self.bookings.book(BookingCommand("cust-1", maid.id, ServiceType.CLEANING, BookingType.SCHEDULED,
                                                 minutes, start))


@pytest.fixture(params=["memory", "postgres"])
def ctx(request):
    if request.param == "postgres":
        if not TEST_DATABASE_URL:
            pytest.skip("TEST_DATABASE_URL not set")
        return Ctx(TEST_DATABASE_URL)
    return Ctx()


@pytest.fixture
def maid(ctx):
    return ctx.maid()
