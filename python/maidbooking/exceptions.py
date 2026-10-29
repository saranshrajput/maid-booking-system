class MaidBookingError(Exception):
    pass


class NotFoundError(MaidBookingError):
    pass


class InvalidRequestError(MaidBookingError):
    pass


class SlotUnavailableError(MaidBookingError):
    pass


class InvalidStateError(MaidBookingError):
    pass


class PaymentFailedError(MaidBookingError):
    pass
