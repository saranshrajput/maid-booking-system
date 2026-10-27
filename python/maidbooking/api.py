import os
from datetime import date, datetime, time
from decimal import Decimal
from typing import Callable, Optional

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .booking_strategies import (BookingCommand, BookingStrategyRegistry, InstantBookingStrategy,
                                 RecurringBookingStrategy, ScheduledBookingStrategy)
from .cancellation_policy import TimeBasedCancellationPolicy
from .domain import (AvailabilityWindow, Booking, BookingType, DayOfWeek, Gender, Maid, PaymentMethodType,
                     RecurrenceRule, ServiceType, TimeSlot)
from .exceptions import (InvalidRequestError, InvalidStateError, NotFoundError, PaymentFailedError,
                         SlotUnavailableError)
from .payment_processors import (CardPaymentProcessor, PaymentProcessorRegistry, UpiPaymentProcessor,
                                 WalletPaymentProcessor)
from .config import build_infrastructure, local_clock
from .pricing import HourlyPricingStrategy
from .search import MaidSearchCriteria, MaidSearchService, standard_providers
from .services import (AvailabilityService, BookingService, CancellationService, MaidService,
                       OnboardMaidCommand, PayCommand, PaymentService)

DEFAULT_SEARCH_DURATION_MINUTES = 60
ERROR_STATUS = {NotFoundError: (404, "NOT_FOUND"), InvalidRequestError: (400, "INVALID_REQUEST"),
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
                             "status": o.status} for o in b.occurrences]}


def create_app(clock: Optional[Callable[[], datetime]] = None, database_url: Optional[str] = None) -> FastAPI:
    clock = clock or local_clock()
    infra = build_infrastructure(database_url)
    maid_repo, booking_repo, payment_repo, locks = infra.maids, infra.bookings, infra.payments, infra.locks
    processors = PaymentProcessorRegistry([CardPaymentProcessor(), UpiPaymentProcessor(), WalletPaymentProcessor()])
    availability = AvailabilityService(booking_repo)
    maid_service = MaidService(maid_repo)
    search_service = MaidSearchService(maid_repo, standard_providers(availability))
    booking_service = BookingService(
        maid_service, booking_repo,
        BookingStrategyRegistry([InstantBookingStrategy(), ScheduledBookingStrategy(), RecurringBookingStrategy()]),
        availability, HourlyPricingStrategy(), locks, clock)
    payment_service = PaymentService(booking_repo, payment_repo, infra.idempotency, processors, locks)
    cancellation_service = CancellationService(booking_repo, payment_repo, processors,
                                               TimeBasedCancellationPolicy(), locks, clock)

    app = FastAPI(title="Maid Booking System")

    @app.exception_handler(InvalidRequestError)
    @app.exception_handler(NotFoundError)
    @app.exception_handler(SlotUnavailableError)
    @app.exception_handler(InvalidStateError)
    @app.exception_handler(PaymentFailedError)
    async def domain_error(_: Request, e: Exception):
        status, code = ERROR_STATUS[type(e)]
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

    @app.get("/api/maids/search")
    def search(locality: Optional[str] = None, serviceType: Optional[ServiceType] = None,
               date: Optional[date] = None, startTime: Optional[time] = None,
               durationMinutes: Optional[int] = None, minRating: Optional[float] = None,
               maxHourlyRate: Optional[Decimal] = None, gender: Optional[Gender] = None,
               skills: Optional[list[str]] = Query(None)):
        slot = _requested_slot(date, startTime, durationMinutes)
        criteria = MaidSearchCriteria(locality, serviceType, slot, minRating, maxHourlyRate, gender, skills)
        return [maid_json(m) for m in search_service.search(criteria)]

    @app.get("/api/maids/{maid_id}")
    def get_maid(maid_id: str):
        return maid_json(maid_service.get(maid_id))

    @app.post("/api/bookings", status_code=201)
    def book(r: CreateBookingRequest):
        rule = r.recurrence and RecurrenceRule(frozenset(r.recurrence.daysOfWeek), r.recurrence.startDate,
                                               r.recurrence.startTime, r.recurrence.occurrences)
        return booking_json(booking_service.book(BookingCommand(
            r.customerId, r.maidId, r.serviceType, r.bookingType, r.durationMinutes, r.startDateTime, rule)))

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
