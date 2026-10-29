from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from threading import Barrier

import pytest

from maidbooking.booking_strategies import BookingCommand
from maidbooking.domain import (BookingStatus, BookingType, DayOfWeek, OccurrenceStatus, PaymentMethodType,
                                RecurrenceRule, ServiceType)
from maidbooking.exceptions import (HoldExpiredError, IdempotencyInProgressError, IdempotencyKeyReusedError,
                                    InvalidStateError, PaymentFailedError, SlotUnavailableError)
from maidbooking.services import PayCommand, PaymentService

SLOT = datetime(2030, 1, 8, 10, 0)          # the fixture clock is Monday 2030-01-07 10:00
PAY = PayCommand(PaymentMethodType.WALLET, "wallet-1")
MINUTE = timedelta(minutes=1)


def reload(ctx, booking):
    return ctx.bookings.get(booking.id)


# ---------------------------------------------------------------- holds

def test_booking_gets_a_hold_deadline_ten_minutes_out(ctx, maid):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    assert booking.occurrences[0].hold_expires_at == ctx.now + 10 * MINUTE


def test_an_unpaid_hold_blocks_the_slot_until_it_lapses_then_frees_it(ctx, maid):
    ctx.book_scheduled(maid, SLOT, 60)
    ctx.now += 9 * MINUTE
    with pytest.raises(SlotUnavailableError):
        ctx.book_scheduled(maid, SLOT, 60)
    assert ctx.search.search(criteria_for(ctx)) == []

    ctx.now += 2 * MINUTE                     # 11 minutes: the hold lapsed, and nothing has swept it yet
    assert ctx.search.search(criteria_for(ctx)) == [maid]
    ctx.book_scheduled(maid, SLOT, 60)        # the slot can be booked again straight away


def criteria_for(ctx):
    from maidbooking.domain import TimeSlot
    from maidbooking.search import MaidSearchCriteria
    return MaidSearchCriteria(requested_slot=TimeSlot.of(SLOT, 60))


def test_start_time_counts_ignore_a_lapsed_hold(ctx, maid):
    ctx.book_scheduled(maid, SLOT, 60)

    def free_at_10():
        counts = ctx.availability.start_time_counts([maid], date(2030, 1, 8), 60, not_before=ctx.now)
        return dict(counts)[time(10, 0)]

    assert free_at_10() == 0
    ctx.now += 11 * MINUTE
    assert free_at_10() == 1


def test_sweeper_marks_lapsed_holds_expired_once_and_leaves_paid_visits_alone(ctx, maid):
    held = ctx.book_scheduled(maid, SLOT, 60)
    paid = ctx.book_scheduled(maid, SLOT + timedelta(hours=3), 60)
    ctx.payments.pay(paid.id, PAY)

    assert ctx.hold_expiry.sweep() == (0, 0)                      # nothing has lapsed yet
    ctx.now += 11 * MINUTE
    assert ctx.hold_expiry.sweep() == (1, 0)
    assert reload(ctx, held).status == BookingStatus.EXPIRED
    assert reload(ctx, held).occurrences[0].status == OccurrenceStatus.EXPIRED
    assert reload(ctx, paid).status == BookingStatus.CONFIRMED
    assert ctx.hold_expiry.sweep() == (0, 0)                      # idempotent


def test_paying_clears_the_deadline_so_a_confirmed_visit_never_expires(ctx, maid):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    ctx.payments.pay(booking.id, PAY)
    assert reload(ctx, booking).occurrences[0].hold_expires_at is None
    ctx.now += timedelta(hours=2)
    assert ctx.hold_expiry.sweep() == (0, 0)
    assert reload(ctx, booking).status == BookingStatus.CONFIRMED


@pytest.mark.parametrize("sweep_first", [False, True])
def test_paying_after_the_hold_ran_out_works_while_the_slot_is_still_free(ctx, maid, sweep_first):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    ctx.now += 11 * MINUTE
    if sweep_first:
        ctx.hold_expiry.sweep()

    ctx.payments.pay(booking.id, PAY)

    assert reload(ctx, booking).status == BookingStatus.CONFIRMED
    with pytest.raises(SlotUnavailableError):                     # and the maid is blocked again
        ctx.book_scheduled(maid, SLOT, 60)


def test_paying_after_the_hold_ran_out_is_refused_when_someone_else_took_the_slot(ctx, maid):
    first = ctx.book_scheduled(maid, SLOT, 60)
    ctx.now += 11 * MINUTE
    second = ctx.book_scheduled(maid, SLOT, 60)                   # allowed: the first hold lapsed
    ctx.payments.pay(second.id, PAY)

    with pytest.raises(HoldExpiredError):
        ctx.payments.pay(first.id, PAY)
    assert ctx.payment_repo.find_captured_by_occurrence_id(first.occurrences[0].id) is None   # nothing was charged


def test_late_payment_for_a_series_checks_every_visit_before_charging_any(ctx, maid):
    rule = RecurrenceRule(frozenset({DayOfWeek.TUESDAY}), date(2030, 1, 8), time(10, 0), 3)
    series = ctx.bookings.book(BookingCommand("c", maid.id, ServiceType.CLEANING, BookingType.RECURRING, 60, None, rule))
    ctx.now += 11 * MINUTE
    ctx.book_scheduled(maid, SLOT + timedelta(days=7), 60)        # someone takes the middle visit

    with pytest.raises(HoldExpiredError):
        ctx.payments.pay(series.id, PAY)

    assert all(ctx.payment_repo.find_captured_by_occurrence_id(o.id) is None for o in series.occurrences)


def test_a_visit_whose_time_has_passed_cannot_be_paid(ctx, maid):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    ctx.now = SLOT + timedelta(hours=2)
    with pytest.raises(HoldExpiredError):
        ctx.payments.pay(booking.id, PAY)


def test_an_expired_booking_cannot_be_cancelled_and_does_not_count_as_upcoming(ctx, maid):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    assert ctx.maids.count_upcoming_visits(maid.id) == 1
    ctx.now += 11 * MINUTE
    assert ctx.maids.count_upcoming_visits(maid.id) == 0
    ctx.hold_expiry.sweep()
    with pytest.raises(InvalidStateError):
        ctx.cancellations.cancel(booking.id)


# ---------------------------------------------------------------- idempotency

def captured(ctx, booking):
    return ctx.payment_repo.find_captured_by_occurrence_id(booking.occurrences[0].id)


def test_the_same_key_and_request_returns_the_first_result_without_charging_again(ctx, maid):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    first = ctx.payments.pay(booking.id, PAY, "key-1")
    again = ctx.payments.pay(booking.id, PAY, "key-1")
    assert [p.id for p in first] == [p.id for p in again]
    assert captured(ctx, booking).id == first[0].id


def test_the_same_key_with_a_different_request_is_rejected(ctx, maid):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    ctx.payments.pay(booking.id, PAY, "key-1")
    for other in (PayCommand(PaymentMethodType.WALLET, "wallet-2"), PayCommand(PaymentMethodType.UPI, "a@upi"),
                  PayCommand(PaymentMethodType.WALLET, "wallet-1", booking.occurrences[0].id)):
        with pytest.raises(IdempotencyKeyReusedError):
            ctx.payments.pay(booking.id, other, "key-1")


def test_a_failed_attempt_releases_its_key_so_a_corrected_retry_can_use_it(ctx, maid):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    with pytest.raises(PaymentFailedError):
        ctx.payments.pay(booking.id, PayCommand(PaymentMethodType.UPI, "fail@upi"), "key-1")
    paid = ctx.payments.pay(booking.id, PayCommand(PaymentMethodType.UPI, "asha@upi"), "key-1")
    assert paid and reload(ctx, booking).status == BookingStatus.CONFIRMED


def test_a_key_left_processing_by_a_crashed_attempt_is_not_charged_again(ctx, maid):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    fingerprint = PaymentService._fingerprint(PAY)
    ctx.idempotency.begin(f"{booking.id}:key-1", fingerprint, ctx.now + timedelta(hours=24))   # the crash left this behind

    with pytest.raises(IdempotencyInProgressError):
        ctx.payments.pay(booking.id, PAY, "key-1")
    assert captured(ctx, booking) is None
    assert reload(ctx, booking).status == BookingStatus.AWAITING_PAYMENT


def test_keys_expire_after_the_retention_period_and_are_purged(ctx, maid):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    ctx.payments.pay(booking.id, PAY, "key-1")
    assert ctx.idempotency.find(f"{booking.id}:key-1", ctx.now) is not None

    ctx.now = SLOT - timedelta(hours=1)                           # still inside 24 hours
    assert ctx.idempotency.find(f"{booking.id}:key-1", ctx.now) is not None
    ctx.now += timedelta(hours=25)
    assert ctx.idempotency.find(f"{booking.id}:key-1", ctx.now) is None
    assert ctx.hold_expiry.sweep() == (0, 1)


def test_a_record_written_before_fingerprints_existed_still_replays(ctx, maid):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    first = ctx.payments.pay(booking.id, PAY)
    key = f"{booking.id}:legacy"
    ctx.idempotency.begin(key, None, ctx.now + timedelta(hours=1))
    ctx.idempotency.complete(key, [p.id for p in first])
    again = ctx.payments.pay(booking.id, PayCommand(PaymentMethodType.CARD, "4111111111111111"), "legacy")
    assert [p.id for p in again] == [p.id for p in first]


def test_concurrent_requests_with_the_same_key_charge_once(ctx, maid):
    booking = ctx.book_scheduled(maid, SLOT, 60)
    threads = 8
    barrier = Barrier(threads)

    def attempt(_):
        barrier.wait()
        return [p.id for p in ctx.payments.pay(booking.id, PAY, "key-1")]

    with ThreadPoolExecutor(threads) as pool:
        results = list(pool.map(attempt, range(threads)))

    assert len({tuple(r) for r in results}) == 1                  # everyone got the same payment back
    assert captured(ctx, booking).id == results[0][0]
