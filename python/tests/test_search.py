from datetime import datetime
from decimal import Decimal

import pytest

from maidbooking.domain import Gender, ServiceType, TimeSlot
from maidbooking.exceptions import InvalidRequestError
from maidbooking.search import MaidSearchCriteria


@pytest.fixture
def maids(ctx):
    asha = ctx.maid("Asha", "Koramangala", Gender.FEMALE, 4.8, "250", "deep-cleaning")
    bina = ctx.maid("Bina", "Koramangala", Gender.FEMALE, 4.0, "150")
    chitra = ctx.maid("Chitra", "Indiranagar", Gender.MALE, 4.5, "200", "deep-cleaning")
    return asha, bina, chitra


def criteria(**kw):
    return MaidSearchCriteria(service_type=ServiceType.CLEANING, **kw)


def test_no_criteria_returns_everyone_sorted_by_rating(ctx, maids):
    assert [m.name for m in ctx.search.search(MaidSearchCriteria())] == ["Asha", "Chitra", "Bina"]


def test_filters_combine(ctx, maids):
    asha, bina, chitra = maids
    assert ctx.search.search(criteria(locality="koramangala", min_rating=4.5)) == [asha]
    assert ctx.search.search(criteria(locality="Koramangala", max_hourly_rate=Decimal("200"))) == [bina]
    assert ctx.search.search(criteria(gender=Gender.MALE)) == [chitra]
    assert ctx.search.search(criteria(skills={"Deep-Cleaning"})) == [asha, chitra]


def test_only_available_maids_are_returned_for_the_requested_slot(ctx, maids):
    asha, bina, _ = maids
    start = datetime(2030, 1, 8, 10, 0)
    ctx.book_scheduled(asha, start, 60)
    slot = TimeSlot.of(datetime(2030, 1, 8, 10, 30), 60)
    assert ctx.search.search(criteria(locality="Koramangala", requested_slot=slot)) == [bina]


def test_maids_outside_working_hours_are_excluded(ctx, maids):
    assert ctx.search.search(criteria(requested_slot=TimeSlot.of(datetime(2030, 1, 8, 22, 0), 60))) == []


def test_onboarding_validates_profile(ctx):
    with pytest.raises(InvalidRequestError):
        ctx.maid("", "Koramangala")
    with pytest.raises(InvalidRequestError):
        ctx.maid("X", "Koramangala", rating=7.0)
    with pytest.raises(InvalidRequestError):
        ctx.maid("X", "Koramangala", rate="-5")
