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


def test_pagination_returns_consistent_pages_and_total(ctx):
    for i in range(7):
        ctx.maid(f"Maid {i}", "Koramangala", Gender.FEMALE, 4.0 + i / 10, "200", "pets")
    ctx.maid("Elsewhere", "Indiranagar", Gender.FEMALE, 4.9, "200")

    for criteria_ in (MaidSearchCriteria(locality="Koramangala"),            # paginated by the repository
                      MaidSearchCriteria(locality="Koramangala", skills={"pets"})):  # filtered in Python, then sliced
        full = ctx.search.search(criteria_)
        pages = [ctx.search.search_page(criteria_, limit=3, offset=o) for o in (0, 3, 6)]
        assert [m.name for m in full] == [f"Maid {i}" for i in range(6, -1, -1)]  # best rated first
        assert all(p.total == 7 for p in pages)
        assert [len(p.items) for p in pages] == [3, 3, 1]
        assert [m for p in pages for m in p.items] == full
        assert ctx.search.search_page(criteria_, limit=3, offset=9).items == []


def test_localities_and_service_summary(ctx):
    ctx.maid("Asha", "Koramangala", Gender.FEMALE, 4.8, "250")
    ctx.maid("Ravi", "koramangala", Gender.MALE, 4.2, "180")
    ctx.maid("Meena", "Indiranagar", Gender.FEMALE, 4.6, "300")

    assert {l.lower() for l in ctx.maid_repo.localities()} == {"koramangala", "indiranagar"}
    everywhere = ctx.maid_repo.service_summary(None)
    assert everywhere[ServiceType.CLEANING] == (3, Decimal("180"))
    here = ctx.maid_repo.service_summary("KORAMANGALA")
    assert here[ServiceType.CLEANING] == (2, Decimal("180"))
    assert ctx.maid_repo.service_summary("Nowhere") == {}


def test_slot_search_and_start_time_counts_use_one_bookings_query(ctx):
    if ctx.engine is None:
        pytest.skip("statement counting needs the SQL backend")
    from sqlalchemy import event
    from datetime import date

    for i in range(30):
        ctx.maid(f"Maid {i}", "Koramangala", Gender.FEMALE, 4.0, "200")
    statements = []
    event.listen(ctx.engine, "before_cursor_execute", lambda *args: statements.append(args[2]))

    slot = TimeSlot.of(datetime(2030, 1, 8, 10, 0), 60)
    found = ctx.search.search(MaidSearchCriteria(locality="Koramangala", requested_slot=slot))
    assert len(found) == 30
    assert len(statements) <= 3, statements  # one for maids, one for bookings (not one per maid)

    statements.clear()
    maids = ctx.search.search(MaidSearchCriteria(locality="Koramangala"))
    ctx.availability.start_time_counts(maids, date(2030, 1, 8), 60, not_before=datetime(2030, 1, 7, 10, 0))
    assert len(statements) <= 3, statements
