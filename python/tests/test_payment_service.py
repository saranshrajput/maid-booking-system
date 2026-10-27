from datetime import date, datetime, time

import pytest

from maidbooking.booking_strategies import BookingCommand
from maidbooking.domain import (BookingStatus, BookingType, DayOfWeek, OccurrenceStatus, PaymentMethodType,
                                RecurrenceRule, ServiceType)
from maidbooking.exceptions import InvalidRequestError, InvalidStateError, PaymentFailedError
from maidbooking.services import PayCommand

CARD = "4111111111111111"
START = datetime(2030, 1, 8, 10, 0)


def recurring(ctx, maid, occurrences):
    rule = RecurrenceRule(frozenset({DayOfWeek.SUNDAY}), date(2030, 1, 7), time(9), occurrences)
    return ctx.bookings.book(BookingCommand("c", maid.id, ServiceType.CLEANING, BookingType.RECURRING, 60, None, rule))


def test_successful_payment_confirms_booking(ctx, maid):
    booking = ctx.book_scheduled(maid, START, 60)
    payments = ctx.payments.pay(booking.id, PayCommand(PaymentMethodType.CARD, CARD))
    assert len(payments) == 1
    assert booking.status == BookingStatus.CONFIRMED


def test_failed_payment_leaves_booking_awaiting_payment(ctx, maid):
    booking = ctx.book_scheduled(maid, START, 60)
    with pytest.raises(PaymentFailedError):
        ctx.payments.pay(booking.id, PayCommand(PaymentMethodType.UPI, "fail@upi"))
    assert booking.status == BookingStatus.AWAITING_PAYMENT


def test_malformed_instrument_is_declined(ctx, maid):
    booking = ctx.book_scheduled(maid, START, 60)
    with pytest.raises(PaymentFailedError):
        ctx.payments.pay(booking.id, PayCommand(PaymentMethodType.UPI, "no-handle"))


def test_recurring_booking_can_be_paid_per_occurrence(ctx, maid):
    booking = recurring(ctx, maid, 3)
    ctx.payments.pay(booking.id, PayCommand(PaymentMethodType.WALLET, "wallet-1", booking.occurrences[0].id))
    assert booking.occurrences[0].status == OccurrenceStatus.CONFIRMED
    assert booking.occurrences[1].status == OccurrenceStatus.PENDING_PAYMENT
    assert booking.status == BookingStatus.AWAITING_PAYMENT

    rest = ctx.payments.pay(booking.id, PayCommand(PaymentMethodType.WALLET, "wallet-1"))
    assert len(rest) == 2
    assert booking.status == BookingStatus.CONFIRMED


def test_paying_an_already_paid_occurrence_is_an_invalid_transition(ctx, maid):
    booking = ctx.book_scheduled(maid, START, 60)
    ctx.payments.pay(booking.id, PayCommand(PaymentMethodType.CARD, CARD))
    with pytest.raises(InvalidStateError):
        ctx.payments.pay(booking.id, PayCommand(PaymentMethodType.CARD, CARD))


def test_same_idempotency_key_returns_original_result_without_charging_twice(ctx, maid):
    booking = ctx.book_scheduled(maid, START, 60)
    cmd = PayCommand(PaymentMethodType.CARD, CARD)
    first = ctx.payments.pay(booking.id, cmd, "key-1")
    retry = ctx.payments.pay(booking.id, cmd, "key-1")
    assert first[0].id == retry[0].id


def test_missing_method_is_rejected(ctx, maid):
    booking = ctx.book_scheduled(maid, START, 60)
    with pytest.raises(InvalidRequestError):
        ctx.payments.pay(booking.id, PayCommand(None, CARD))
