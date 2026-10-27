import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .domain import PaymentMethodType
from .exceptions import InvalidRequestError


@dataclass(frozen=True)
class ChargeResult:
    success: bool
    reference: Optional[str] = None
    failure_reason: Optional[str] = None


class PaymentProcessor(ABC):
    """Our own gateway abstraction; a real PSP integration would implement this per method."""

    method: PaymentMethodType

    @abstractmethod
    def charge(self, amount: Decimal, instrument: str) -> ChargeResult: ...

    @abstractmethod
    def refund(self, gateway_reference: str, amount: Decimal) -> None: ...


class MockPaymentProcessor(PaymentProcessor):
    """Simulated gateway: succeeds for well-formed instruments, declines anything starting with 'fail'."""

    @abstractmethod
    def is_well_formed(self, instrument: str) -> bool: ...

    def charge(self, amount, instrument):
        if not instrument or not (instrument.startswith("fail") or self.is_well_formed(instrument)):
            return ChargeResult(False, failure_reason=f"Invalid {self.method.value} details")
        if instrument.startswith("fail"):
            return ChargeResult(False, failure_reason=f"{self.method.value} payment declined")
        return ChargeResult(True, reference=f"{self.method.value}-{uuid.uuid4()}")

    def refund(self, gateway_reference, amount):
        pass  # Mock gateway: refunds always succeed.


class CardPaymentProcessor(MockPaymentProcessor):
    method = PaymentMethodType.CARD

    def is_well_formed(self, instrument):
        return instrument.isdigit() and 12 <= len(instrument) <= 19


class UpiPaymentProcessor(MockPaymentProcessor):
    method = PaymentMethodType.UPI

    def is_well_formed(self, instrument):
        return "@" in instrument


class WalletPaymentProcessor(MockPaymentProcessor):
    method = PaymentMethodType.WALLET

    def is_well_formed(self, instrument):
        return bool(instrument.strip())


class PaymentProcessorRegistry:
    def __init__(self, processors: list[PaymentProcessor]):
        self._processors = {p.method: p for p in processors}

    def get(self, method: PaymentMethodType) -> PaymentProcessor:
        if method not in self._processors:
            raise InvalidRequestError(f"Unsupported payment method: {method}")
        return self._processors[method]
