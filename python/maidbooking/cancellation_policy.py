from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal

from .domain import BookingOccurrence


class CancellationPolicy(ABC):
    # Fraction of the paid amount to refund, between 0 and 1.
    @abstractmethod
    def refund_fraction(self, occurrence: BookingOccurrence, now: datetime) -> Decimal: ...


class TimeBasedCancellationPolicy(CancellationPolicy):
    """24h+ before start: full refund; 2h+: half; later: none."""

    def refund_fraction(self, occurrence, now):
        until_start = occurrence.slot.start - now
        if until_start >= timedelta(hours=24):
            return Decimal("1")
        if until_start >= timedelta(hours=2):
            return Decimal("0.5")
        return Decimal("0")
