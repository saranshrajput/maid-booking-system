from datetime import date, datetime, time
from decimal import Decimal

import pytest

from maidbooking.booking_strategies import BookingCommand
from maidbooking.domain import (BookingStatus, BookingType, DayOfWeek, OccurrenceStatus, PaymentMethodType,
                                PaymentStatus, RecurrenceRule, ServiceType)
from maidbooking.exceptions import InvalidStateError
from maidbooking.services import PayCommand

PAY = PayCommand(PaymentMethodType.WALLET, "wallet-1")


def paid_scheduled(ctx, maid, start):
    booking = ctx.book_scheduled(maid, start, 60)
    ctx.payments.pay(booking.id, PAY)
    return booking


def paid_series(ctx, maid):
    rule = RecurrenceRule(frozenset({DayOfWeek.SUNDAY}), date(2030, 1, 7), time(9), 3)
    booking = ctx.bookings.book(BookingCommand("c", maid.id, ServiceType.CLEANING, BookingType.RECURRING, 60,
                                               None, rule))
    ctx.payments.pay(booking.id, PAY)
    return booking


def test_more_than_24_hours_before_start_refunds_in_full(ctx, maid):
    booking = paid_scheduled(ctx, maid, datetime(2030, 1, 9, 12, 0))
    result = ctx.cancellations.cancel(booking.id)
    assert result.total_refund == Decimal("200.00")
    assert booking.status == BookingStatus.CANCELLED
    payment = ctx.payment_repo.find_captured_by_occurrence_id(booking.occurrences[0].id)
    assert payment.status == PaymentStatus.REFUNDED


def test_between_2_and_24_hours_refunds_half(ctx, maid):
    booking = paid_scheduled(ctx, maid, datetime(2030, 1, 8, 9, 0))
    assert ctx.cancellations.cancel(booking.id).total_refund == Decimal("100.00")


def test_less_than_2_hours_refunds_nothing(ctx, maid):
    booking = paid_scheduled(ctx, maid, datetime(2030, 1, 7, 11, 0))
    assert ctx.cancellations.cancel(booking.id).total_refund == Decimal("0")


def test_unpaid_booking_cancels_without_refund(ctx, maid):
    booking = ctx.book_scheduled(maid, datetime(2030, 1, 9, 12, 0), 60)
    assert ctx.cancellations.cancel(booking.id).total_refund == Decimal("0")


def test_cancellation_frees_the_slot_for_rebooking(ctx, maid):
    start = datetime(2030, 1, 9, 12, 0)
    booking = ctx.book_scheduled(maid, start, 60)
    ctx.cancellations.cancel(booking.id)
    ctx.book_scheduled(maid, start, 60)


def test_cancelling_twice_is_an_invalid_transition(ctx, maid):
    booking = ctx.book_scheduled(maid, datetime(2030, 1, 9, 12, 0), 60)
    ctx.cancellations.cancel(booking.id)
    with pytest.raises(InvalidStateError):
        ctx.cancellations.cancel(booking.id)


def test_recurring_single_occurrence_cancel_leaves_the_rest_active(ctx, maid):
    booking = paid_series(ctx, maid)
    result = ctx.cancellations.cancel(booking.id, booking.occurrences[1].id)
    assert len(result.cancelled_occurrence_ids) == 1
    assert booking.occurrences[1].status == OccurrenceStatus.CANCELLED
    assert booking.occurrences[0].status == OccurrenceStatus.CONFIRMED
    assert booking.status == BookingStatus.CONFIRMED


def test_recurring_whole_series_cancel_refunds_every_paid_occurrence(ctx, maid):
    booking = paid_series(ctx, maid)
    result = ctx.cancellations.cancel(booking.id)
    assert len(result.cancelled_occurrence_ids) == 3
    assert result.total_refund == Decimal("600.00")
    assert booking.status == BookingStatus.CANCELLED
    assert ctx.availability.is_available(maid, booking.occurrences[0].slot)
