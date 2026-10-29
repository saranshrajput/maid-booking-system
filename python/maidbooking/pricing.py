from abc import ABC, abstractmethod
from decimal import ROUND_HALF_UP, Decimal

from .domain import Maid, ServiceType, TimeSlot


class PricingStrategy(ABC):
    @abstractmethod
    def price(self, maid: Maid, service: ServiceType, slot: TimeSlot) -> Decimal: ...


class HourlyPricingStrategy(PricingStrategy):
    def price(self, maid, service, slot):
        return (maid.rate_for(service) * slot.minutes / 60).quantize(Decimal("0.01"), ROUND_HALF_UP)
