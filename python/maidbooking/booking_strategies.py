from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .domain import BookingType, RecurrenceRule, ServiceType, TimeSlot
from .exceptions import InvalidRequestError


@dataclass(frozen=True)
class BookingCommand:
    customer_id: str
    maid_id: str
    service_type: ServiceType
    booking_type: BookingType
    duration_minutes: int
    start_datetime: Optional[datetime] = None
    recurrence: Optional[RecurrenceRule] = None


class BookingStrategy(ABC):
    """One implementation per booking type; a new type is a new class, no existing code changes."""

    type: BookingType

    @abstractmethod
    def resolve_slots(self, command: BookingCommand, now: datetime) -> list[TimeSlot]: ...


class InstantBookingStrategy(BookingStrategy):
    type = BookingType.INSTANT

    def resolve_slots(self, command, now):
        return [TimeSlot.of(now.replace(second=0, microsecond=0), command.duration_minutes)]


class ScheduledBookingStrategy(BookingStrategy):
    type = BookingType.SCHEDULED

    def resolve_slots(self, command, now):
        start = command.start_datetime
        if start is None or start <= now:
            raise InvalidRequestError("Scheduled booking needs a start date-time in the future")
        return [TimeSlot.of(start, command.duration_minutes)]


class RecurringBookingStrategy(BookingStrategy):
    type = BookingType.RECURRING

    def resolve_slots(self, command, now):
        rule = command.recurrence
        if rule is None:
            raise InvalidRequestError("Recurring booking needs a recurrence rule")
        slots, day = [], rule.start_date
        while len(slots) < rule.occurrences:
            start = datetime.combine(day, rule.start_time)
            if day.weekday() in rule.days_of_week and start > now:
                slots.append(TimeSlot.of(start, command.duration_minutes))
            day += timedelta(days=1)
        return slots


class BookingStrategyRegistry:
    def __init__(self, strategies: list[BookingStrategy]):
        self._strategies = {s.type: s for s in strategies}

    def get(self, booking_type: BookingType) -> BookingStrategy:
        if booking_type not in self._strategies:
            raise InvalidRequestError(f"Unsupported booking type: {booking_type}")
        return self._strategies[booking_type]
