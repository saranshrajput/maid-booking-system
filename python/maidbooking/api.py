import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from datetime import date, datetime, time
from decimal import Decimal
from typing import Callable, Optional

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .booking_strategies import (BookingCommand, BookingStrategyRegistry, InstantBookingStrategy,
                                 RecurringBookingStrategy, ScheduledBookingStrategy)
from .cancellation_policy import TimeBasedCancellationPolicy
from .domain import (AvailabilityWindow, Booking, BookingType, DayOfWeek, Gender, Maid, PaymentMethodType,
                     RecurrenceRule, ServiceType, TimeSlot)
from .exceptions import (HoldExpiredError, IdempotencyInProgressError, IdempotencyKeyReusedError, InvalidRequestError,
                         InvalidStateError, MaidHasUpcomingBookingsError, NotFoundError, PaymentFailedError,
                         SlotUnavailableError)
from .payment_processors import (CardPaymentProcessor, PaymentProcessorRegistry, UpiPaymentProcessor,
                                 WalletPaymentProcessor)
from .config import build_infrastructure, local_clock
from .pricing import HourlyPricingStrategy
from .search import MaidSearchCriteria, MaidSearchService
from .services import (AvailabilityService, BookingService, CancellationService, HoldExpiryService, HoldPolicy,
                       MaidService, OnboardMaidCommand, PayCommand, PaymentService)

DEFAULT_SEARCH_DURATION_MINUTES = 60
DEFAULT_PAGE_SIZE = 50
log = logging.getLogger(__name__)
MAX_PAGE_SIZE = 100
STATIC_DIR = Path(__file__).parent / "static"
ERROR_STATUS = {HoldExpiredError: (409, "HOLD_EXPIRED"), IdempotencyInProgressError: (409, "IDEMPOTENCY_IN_PROGRESS"),
                IdempotencyKeyReusedError: (422, "IDEMPOTENCY_KEY_REUSED"),
                MaidHasUpcomingBookingsError: (409, "MAID_HAS_UPCOMING_BOOKINGS"), NotFoundError: (404, "NOT_FOUND"), InvalidRequestError: (400, "INVALID_REQUEST"),
                SlotUnavailableError: (409, "SLOT_UNAVAILABLE"), InvalidStateError: (409, "INVALID_STATE"),
                PaymentFailedError: (402, "PAYMENT_FAILED")}


class WindowDto(BaseModel):
    day: DayOfWeek
    start: time
    end: time


class AddMaidRequest(BaseModel):
    name: str = Field(min_length=1)
    locality: str = Field(min_length=1)
    gender: Gender
    rating: float = Field(ge=0, le=5)
    hourlyRates: dict[ServiceType, Decimal] = Field(min_length=1)
    skills: list[str] = []
    availability: list[WindowDto] = Field(min_length=1)


class RecurrenceDto(BaseModel):
    daysOfWeek: list[DayOfWeek] = Field(min_length=1)
    startDate: date
    startTime: time
    occurrences: int = Field(gt=0)


class CreateBookingRequest(BaseModel):
    customerId: str = Field(min_length=1)
    maidId: str = Field(min_length=1)
    serviceType: ServiceType
    bookingType: BookingType
    durationMinutes: int = Field(gt=0)
    startDateTime: Optional[datetime] = None
    recurrence: Optional[RecurrenceDto] = None


class PayRequest(BaseModel):
    method: PaymentMethodType
    instrument: str = Field(min_length=1)
    occurrenceId: Optional[str] = None


def maid_json(m: Maid) -> dict:
    return {"id": m.id, "name": m.name, "locality": m.locality, "gender": m.gender, "rating": m.rating,
            "hourlyRates": {k.value: float(v) for k, v in m.hourly_rates.items()}, "skills": sorted(m.skills),
            "availability": [{"day": w.day.name, "start": w.start.isoformat(), "end": w.end.isoformat()}
                             for w in m.availability]}


def booking_json(b: Booking) -> dict:
    return {"id": b.id, "customerId": b.customer_id, "maidId": b.maid_id, "serviceType": b.service_type,
            "bookingType": b.booking_type, "status": b.status,
            "occurrences": [{"id": o.id, "start": o.slot.start, "end": o.slot.end, "price": float(o.price),
                             "status": o.status, "holdExpiresAt": o.hold_expires_at} for o in b.occurrences]}


def create_app(clock: Optional[Callable[[], datetime]] = None, database_url: Optional[str] = None,
               holds: Optional[HoldPolicy] = None, sweep_seconds: Optional[float] = None) -> FastAPI:
    """HOLD_MINUTES (default 10) is how long an unpaid booking holds the slot, IDEMPOTENCY_HOURS (default 24) how long
    a payment key is remembered, HOLD_SWEEP_SECONDS (default 30, 0 = off) how often expired holds are swept."""
    clock = clock or local_clock()
    holds = holds or HoldPolicy(timedelta(minutes=float(os.getenv("HOLD_MINUTES", "10"))),
                                timedelta(hours=float(os.getenv("IDEMPOTENCY_HOURS", "24"))))
    sweep_seconds = float(os.getenv("HOLD_SWEEP_SECONDS", "30")) if sweep_seconds is None else sweep_seconds
    infra = build_infrastructure(database_url)
    maid_repo, booking_repo, payment_repo, locks = infra.maids, infra.bookings, infra.payments, infra.locks
    processors = PaymentProcessorRegistry([CardPaymentProcessor(), UpiPaymentProcessor(), WalletPaymentProcessor()])
    availability = AvailabilityService(booking_repo, clock)
    maid_service = MaidService(maid_repo, booking_repo, clock)
    search_service = MaidSearchService(maid_repo, availability)
    booking_service = BookingService(
        maid_service, booking_repo,
        BookingStrategyRegistry([InstantBookingStrategy(), ScheduledBookingStrategy(), RecurringBookingStrategy()]),
        availability, HourlyPricingStrategy(), locks, clock, holds)
    payment_service = PaymentService(booking_repo, payment_repo, infra.idempotency, processors, locks, maid_service,
                                     availability, clock, holds)
    hold_expiry = HoldExpiryService(booking_repo, infra.idempotency, locks, clock)
    cancellation_service = CancellationService(booking_repo, payment_repo, processors,
                                               TimeBasedCancellationPolicy(), locks, clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop = threading.Event()

        def sweep_loop():
            while True:
                try:
                    hold_expiry.sweep()
                except Exception:
                    log.exception("hold expiry sweep failed")
                if stop.wait(sweep_seconds):
                    return

        worker = threading.Thread(target=sweep_loop, name="hold-expiry", daemon=True)
        if sweep_seconds > 0:
            worker.start()
        yield
        stop.set()

    app = FastAPI(title="Maid Booking System", lifespan=lifespan)
    app.state.hold_expiry = hold_expiry  # tests and ops can run a sweep by hand

    @app.exception_handler(InvalidRequestError)
    @app.exception_handler(NotFoundError)
    @app.exception_handler(SlotUnavailableError)
    @app.exception_handler(InvalidStateError)
    @app.exception_handler(PaymentFailedError)
    async def domain_error(_: Request, e: Exception):
        status, code = next(v for cls, v in ERROR_STATUS.items() if isinstance(e, cls))  # subclasses listed first
        return JSONResponse(status_code=status, content={"code": code, "message": str(e)})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, e: RequestValidationError):
        message = "; ".join(f"{'.'.join(map(str, err['loc'][1:]))} {err['msg']}" for err in e.errors())
        return JSONResponse(status_code=400, content={"code": "INVALID_REQUEST", "message": message})

    @app.get("/health")
    def health(response: Response):
        if infra.engine is not None:
            try:
                with infra.engine.connect() as conn:
                    conn.exec_driver_sql("SELECT 1")
            except Exception:
                response.status_code = 503
                return {"status": "unavailable", "storage": infra.storage}
        return {"status": "ok", "storage": infra.storage}

    @app.post("/api/maids", status_code=201)
    def add_maid(r: AddMaidRequest):
        windows = [AvailabilityWindow(w.day, w.start, w.end) for w in r.availability]
        return maid_json(maid_service.onboard(OnboardMaidCommand(
            r.name, r.locality, r.gender, r.rating, r.hourlyRates, frozenset(r.skills), windows)))

    @app.get("/api/meta")
    def meta():
        return {"now": clock().isoformat(timespec="seconds"), "timezone": os.getenv("APP_TIMEZONE", "Asia/Kolkata")}

    @app.get("/api/availability/slots")
    def availability_slots(day: date = Query(alias="date"), durationMinutes: int = Query(60, gt=0, le=720),
                           locality: Optional[str] = None, serviceType: Optional[ServiceType] = None,
                           gender: Optional[Gender] = None):
        """Free-maid count for each start time on one day, so a UI can grey out times nobody can take."""
        maids = search_service.search(MaidSearchCriteria(locality, serviceType, None, None, None, gender, None))
        counts = availability.start_time_counts(maids, day, durationMinutes, not_before=clock())
        return [{"time": t.strftime("%H:%M"), "available": n} for t, n in counts]

    @app.get("/api/localities")
    def localities():
        return maid_repo.localities()

    @app.get("/api/services/summary")
    def services_summary(locality: Optional[str] = None):
        """Maid count and lowest hourly rate per service, computed in the database (one aggregate query)."""
        return {service.value: {"maids": count, "minHourlyRate": float(rate)}
                for service, (count, rate) in maid_repo.service_summary(locality).items()}

    @app.get("/api/maids/search")
    def search(response: Response, locality: Optional[str] = None, serviceType: Optional[ServiceType] = None,
               date: Optional[date] = None, startTime: Optional[time] = None,
               durationMinutes: Optional[int] = None, minRating: Optional[float] = None,
               maxHourlyRate: Optional[Decimal] = None, gender: Optional[Gender] = None,
               skills: Optional[list[str]] = Query(None), limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
               offset: int = Query(0, ge=0)):
        slot = _requested_slot(date, startTime, durationMinutes)
        criteria = MaidSearchCriteria(locality, serviceType, slot, minRating, maxHourlyRate, gender, skills)
        page = search_service.search_page(criteria, limit, offset)
        response.headers["X-Total-Count"] = str(page.total)
        return [maid_json(m) for m in page.items]

    @app.get("/api/maids/{maid_id}")
    def get_maid(maid_id: str):
        return maid_json(maid_service.get(maid_id))

    @app.delete("/api/maids/{maid_id}")
    def remove_maid(maid_id: str, cancelUpcoming: bool = False):
        """Hide a maid from search and booking. Refused while she has upcoming visits unless cancelUpcoming=true,
        which cancels them with full refunds."""
        maid = maid_service.get(maid_id)
        upcoming = maid_service.count_upcoming_visits(maid_id)
        if upcoming and not cancelUpcoming:
            raise MaidHasUpcomingBookingsError(
                f"{maid.name} has {upcoming} upcoming {'visit' if upcoming == 1 else 'visits'}. "
                "Cancel them first, or remove her with cancelUpcoming=true to cancel them with full refunds.")
        maid_service.deactivate(maid_id)  # first, so nobody can book her while the visits are cancelled
        cancelled, refund = cancellation_service.cancel_upcoming_for_maid(maid_id) if upcoming else (0, Decimal("0"))
        return {"id": maid_id, "removed": True, "cancelledVisits": cancelled, "totalRefund": float(refund)}

    @app.post("/api/bookings", status_code=201)
    def book(r: CreateBookingRequest):
        rule = r.recurrence and RecurrenceRule(frozenset(r.recurrence.daysOfWeek), r.recurrence.startDate,
                                               r.recurrence.startTime, r.recurrence.occurrences)
        return booking_json(booking_service.book(BookingCommand(
            r.customerId, r.maidId, r.serviceType, r.bookingType, r.durationMinutes, r.startDateTime, rule)))

    @app.get("/api/bookings")
    def list_bookings(customerId: str = Query(min_length=1)):
        return [booking_json(b) for b in booking_service.list_for_customer(customerId)]

    @app.get("/api/bookings/{booking_id}")
    def get_booking(booking_id: str):
        return booking_json(booking_service.get(booking_id))

    @app.post("/api/bookings/{booking_id}/payments", status_code=201)
    def pay(booking_id: str, r: PayRequest, idempotency_key: Optional[str] = Header(None)):
        payments = payment_service.pay(booking_id, PayCommand(r.method, r.instrument, r.occurrenceId),
                                       idempotency_key)
        return [{"id": p.id, "occurrenceId": p.occurrence_id, "amount": float(p.amount), "method": p.method,
                 "status": p.status, "refundedAmount": float(p.refunded_amount)} for p in payments]

    @app.post("/api/bookings/{booking_id}/cancel")
    def cancel(booking_id: str, occurrenceId: Optional[str] = None):
        result = cancellation_service.cancel(booking_id, occurrenceId)
        return {"booking": booking_json(result.booking), "cancelledOccurrenceIds": result.cancelled_occurrence_ids,
                "totalRefund": float(result.total_refund)}

    # Static UI last, so every API route above wins over it.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    return app


def _requested_slot(day: Optional[date], start: Optional[time], minutes: Optional[int]) -> Optional[TimeSlot]:
    if day is None and start is None:
        if minutes is not None:
            raise InvalidRequestError("durationMinutes needs date and startTime")
        return None
    if day is None or start is None:
        raise InvalidRequestError("date and startTime must be provided together")
    return TimeSlot.of(datetime.combine(day, start), minutes or DEFAULT_SEARCH_DURATION_MINUTES)


app = create_app(database_url=os.getenv("DATABASE_URL"))
