from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from decimal import Decimal
from threading import Barrier

import pytest

from maidbooking.booking_strategies import BookingCommand
from maidbooking.domain import BookingStatus, BookingType, DayOfWeek, RecurrenceRule, ServiceType
from maidbooking.exceptions import InvalidRequestError, SlotUnavailableError

TOMORROW_10 = datetime(2030, 1, 8, 10, 0)


def recurring_command(maid, occurrences=4):
    rule = RecurrenceRule(frozenset({DayOfWeek.SUNDAY}), date(2030, 1, 7), time(9), occurrences)
    return BookingCommand("c", maid.id, ServiceType.CLEANING, BookingType.RECURRING, 60, None, rule)


def test_scheduled_booking_is_priced_by_duration_and_awaits_payment(ctx, maid):
    booking = ctx.book_scheduled(maid, TOMORROW_10, 90)
    assert booking.status == BookingStatus.AWAITING_PAYMENT
    assert booking.occurrences[0].price == Decimal("300.00")


def test_instant_booking_starts_now(ctx, maid):
    booking = ctx.bookings.book(BookingCommand("c", maid.id, ServiceType.CLEANING, BookingType.INSTANT, 60))
    assert booking.occurrences[0].slot.start == datetime(2030, 1, 7, 10, 0)


def test_overlap_is_rejected_but_back_to_back_is_allowed(ctx, maid):
    ctx.book_scheduled(maid, TOMORROW_10, 60)
    with pytest.raises(SlotUnavailableError):
        ctx.book_scheduled(maid, datetime(2030, 1, 8, 10, 30), 60)
    ctx.book_scheduled(maid, datetime(2030, 1, 8, 11, 0), 60)


def test_slot_outside_working_hours_is_rejected(ctx, maid):
    with pytest.raises(SlotUnavailableError):
        ctx.book_scheduled(maid, datetime(2030, 1, 8, 6, 0), 60)
    with pytest.raises(SlotUnavailableError):
        ctx.book_scheduled(maid, datetime(2030, 1, 8, 19, 0), 120)


def test_recurring_booking_creates_all_occurrences_and_blocks_each(ctx, maid):
    booking = ctx.bookings.book(recurring_command(maid))
    assert len(booking.occurrences) == 4
    with pytest.raises(SlotUnavailableError):
        ctx.book_scheduled(maid, datetime(2030, 1, 20, 9, 30), 60)


def test_recurring_booking_is_all_or_nothing_when_one_occurrence_conflicts(ctx, maid):
    ctx.book_scheduled(maid, datetime(2030, 1, 20, 9, 0), 60)
    with pytest.raises(SlotUnavailableError):
        ctx.bookings.book(recurring_command(maid))
    assert len(ctx.booking_repo.find_by_maid_id(maid.id)) == 1


def test_rejects_service_the_maid_does_not_offer(ctx, maid):
    with pytest.raises(InvalidRequestError):
        ctx.bookings.book(BookingCommand("c", maid.id, ServiceType.COOKING, BookingType.SCHEDULED, 60, TOMORROW_10))


@pytest.mark.parametrize("minutes", [0, 13 * 60])
def test_rejects_invalid_duration(ctx, maid, minutes):
    with pytest.raises(InvalidRequestError):
        ctx.book_scheduled(maid, TOMORROW_10, minutes)


def test_concurrent_requests_for_same_slot_yield_exactly_one_booking(ctx, maid):
    threads = 16
    barrier = Barrier(threads)

    def attempt():
        barrier.wait()
        try:
            ctx.book_scheduled(maid, TOMORROW_10, 60)
            return True
        except SlotUnavailableError:
            return False

    with ThreadPoolExecutor(threads) as pool:
        results = list(pool.map(lambda _: attempt(), range(threads)))

    assert results.count(True) == 1
    assert len(ctx.booking_repo.find_by_maid_id(maid.id)) == 1


def test_two_app_instances_sharing_a_database_cannot_double_book():
    import os
    from tests.conftest import Ctx
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    instance_a, instance_b = Ctx(url), Ctx(url, reset=False)  # Separate in-process locks, one database.
    maid = instance_a.maid()
    threads = 16
    barrier = Barrier(threads)

    def attempt(i):
        barrier.wait()
        try:
            (instance_a if i % 2 else instance_b).book_scheduled(maid, TOMORROW_10, 60)
            return True
        except SlotUnavailableError:
            return False

    with ThreadPoolExecutor(threads) as pool:
        results = list(pool.map(attempt, range(threads)))

    assert results.count(True) == 1
    assert len(instance_a.booking_repo.find_by_maid_id(maid.id)) == 1


def test_busy_slots_report_only_active_overlapping_slots(ctx, maid):
    from maidbooking.domain import TimeSlot
    booking = ctx.book_scheduled(maid, TOMORROW_10, 60)
    other = ctx.maid("Other", "Koramangala")
    day = TimeSlot(datetime(2030, 1, 8, 0, 0), datetime(2030, 1, 9, 0, 0))

    busy = ctx.booking_repo.find_busy_slots([maid.id, other.id], day)
    assert busy == {maid.id: [booking.occurrences[0].slot]}
    assert ctx.booking_repo.find_busy_slots([maid.id], TimeSlot(datetime(2030, 1, 8, 11, 0), datetime(2030, 1, 8, 12, 0))) == {}
    assert ctx.booking_repo.find_busy_slots([], day) == {}

    ctx.cancellations.cancel(booking.id)
    assert ctx.booking_repo.find_busy_slots([maid.id], day) == {}
