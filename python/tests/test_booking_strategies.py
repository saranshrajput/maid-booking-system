from datetime import date, datetime, time

import pytest

from maidbooking.booking_strategies import (BookingCommand, InstantBookingStrategy, RecurringBookingStrategy,
                                            ScheduledBookingStrategy)
from maidbooking.domain import BookingType, DayOfWeek, RecurrenceRule, ServiceType, TimeSlot
from maidbooking.exceptions import InvalidRequestError

NOW = datetime(2030, 1, 7, 10, 0, 30)  # Monday


def command(type_, start=None, rule=None):
    return BookingCommand("c", "m", ServiceType.CLEANING, type_, 60, start, rule)


def test_instant_starts_now_truncated_to_the_minute():
    slots = InstantBookingStrategy().resolve_slots(command(BookingType.INSTANT), NOW)
    assert slots == [TimeSlot.of(datetime(2030, 1, 7, 10, 0), 60)]


def test_scheduled_rejects_past_or_missing_start():
    strategy = ScheduledBookingStrategy()
    with pytest.raises(InvalidRequestError):
        strategy.resolve_slots(command(BookingType.SCHEDULED, datetime(2030, 1, 7, 9, 0)), NOW)
    with pytest.raises(InvalidRequestError):
        strategy.resolve_slots(command(BookingType.SCHEDULED), NOW)


def test_recurring_generates_requested_occurrences_on_matching_days():
    rule = RecurrenceRule(frozenset({DayOfWeek.SUNDAY}), date(2030, 1, 7), time(9), 3)
    slots = RecurringBookingStrategy().resolve_slots(command(BookingType.RECURRING, rule=rule), NOW)
    assert [s.start for s in slots] == [datetime(2030, 1, 13, 9), datetime(2030, 1, 20, 9), datetime(2030, 1, 27, 9)]


def test_recurring_skips_todays_slot_that_already_passed():
    rule = RecurrenceRule(frozenset({DayOfWeek.MONDAY}), date(2030, 1, 7), time(9), 2)
    slots = RecurringBookingStrategy().resolve_slots(command(BookingType.RECURRING, rule=rule), NOW)
    assert slots[0].start == datetime(2030, 1, 14, 9)


def test_recurrence_rule_rejects_bad_input():
    with pytest.raises(InvalidRequestError):
        RecurrenceRule(frozenset(), date(2030, 1, 7), time(12), 3)
    with pytest.raises(InvalidRequestError):
        RecurrenceRule(frozenset({DayOfWeek.MONDAY}), date(2030, 1, 7), time(12), 0)
