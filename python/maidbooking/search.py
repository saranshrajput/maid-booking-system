from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Iterable, Optional

from .domain import Gender, Maid, ServiceType, TimeSlot
from .repositories import MaidQuery, MaidRepository
from .services import AvailabilityService


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


@dataclass(frozen=True)
class SearchPage:
    items: list
    total: int


MaidFilter = Callable[[Maid], bool]
# Filters the repository cannot push into a query. Add one by adding a provider function to the list.
MaidFilterProvider = Callable[[MaidSearchCriteria], Optional[MaidFilter]]


def skills_filter(c):
    if c.skills:
        return lambda m: m.has_skills(c.skills)


def standard_providers() -> list[MaidFilterProvider]:
    return [skills_filter]


class MaidSearchService:
    """Locality, service, rating, rate and gender are filtered (and paginated) by the repository, so a database can
    use its indexes. A requested slot is checked for all candidates with one bookings query. Anything else goes
    through the filter providers in Python."""

    def __init__(self, maids: MaidRepository, availability: AvailabilityService,
                 providers: Optional[list[MaidFilterProvider]] = None):
        self._maids = maids
        self._availability = availability
        self._providers = standard_providers() if providers is None else providers

    def search(self, criteria: MaidSearchCriteria, limit: Optional[int] = None, offset: int = 0) -> list[Maid]:
        return self.search_page(criteria, limit, offset).items

    def search_page(self, criteria: MaidSearchCriteria, limit: Optional[int] = None, offset: int = 0) -> SearchPage:
        query = MaidQuery((criteria.locality or "").strip() or None, criteria.service_type, criteria.gender,
                          criteria.min_rating, criteria.max_hourly_rate)
        residual = [f for f in (p(criteria) for p in self._providers) if f]
        if criteria.requested_slot is None and not residual:
            return SearchPage(self._maids.search(query, limit, offset), self._maids.count(query))  # paginated in SQL
        maids = self._maids.search(query)
        if criteria.requested_slot is not None:
            maids = self._availability.free_maids(maids, criteria.requested_slot)
        maids = [m for m in maids if all(f(m) for f in residual)]
        return SearchPage(maids[offset:offset + limit] if limit else maids[offset:], len(maids))
