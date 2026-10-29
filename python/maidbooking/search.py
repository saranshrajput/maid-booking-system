from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Iterable, Optional

from .domain import Gender, Maid, ServiceType, TimeSlot
from .repositories import MaidRepository


@dataclass(frozen=True)
class MaidSearchCriteria:
    """Every field is optional; None means 'don't filter on this'."""
    locality: Optional[str] = None
    service_type: Optional[ServiceType] = None
    requested_slot: Optional[TimeSlot] = None
    min_rating: Optional[float] = None
    max_hourly_rate: Optional[Decimal] = None
    gender: Optional[Gender] = None
    skills: Optional[Iterable[str]] = None


MaidFilter = Callable[[Maid], bool]
# Add a new search filter by adding one provider function to the list; nothing else changes.
MaidFilterProvider = Callable[[MaidSearchCriteria], Optional[MaidFilter]]


def locality_filter(c):
    if c.locality and c.locality.strip():
        return lambda m: m.serves_locality(c.locality)


def service_type_filter(c):
    if c.service_type:
        return lambda m: m.offers(c.service_type)


def rating_filter(c):
    if c.min_rating is not None:
        return lambda m: m.rating >= c.min_rating


# With a service type the cap applies to that service's rate, otherwise to any offered rate.
def price_filter(c):
    if c.max_hourly_rate is None:
        return None
    if c.service_type:
        return lambda m: m.offers(c.service_type) and m.rate_for(c.service_type) <= c.max_hourly_rate
    return lambda m: any(r <= c.max_hourly_rate for r in m.hourly_rates.values())


def gender_filter(c):
    if c.gender:
        return lambda m: m.gender == c.gender


def skills_filter(c):
    if c.skills:
        return lambda m: m.has_skills(c.skills)


def availability_filter(availability_service) -> MaidFilterProvider:
    def provider(c):
        if c.requested_slot:
            return lambda m: availability_service.is_available(m, c.requested_slot)
    return provider


def standard_providers(availability_service) -> list[MaidFilterProvider]:
    return [locality_filter, service_type_filter, rating_filter, price_filter, gender_filter,
            skills_filter, availability_filter(availability_service)]


class MaidSearchService:
    def __init__(self, maids: MaidRepository, providers: list[MaidFilterProvider]):
        self._maids = maids
        self._providers = providers

    def search(self, criteria: MaidSearchCriteria) -> list[Maid]:
        filters = [f for f in (p(criteria) for p in self._providers) if f]
        matches = [m for m in self._maids.find_all() if all(f(m) for f in filters)]
        return sorted(matches, key=lambda m: (-m.rating, m.name))
