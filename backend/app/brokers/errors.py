class BrokerError(Exception):
    """Base class for all broker-adapter errors. Upstream code (Risk Engine, Order
    Orchestrator, System status) should only ever need to catch this hierarchy —
    never a provider-specific exception."""


class BrokerAuthError(BrokerError):
    """Credentials missing/invalid/expired."""


class BrokerRateLimitError(BrokerError):
    """Broker API rate limit hit; caller should back off."""


class BrokerConnectionError(BrokerError):
    """Network/timeout/5xx — broker unreachable."""


class BrokerOrderRejected(BrokerError):
    """Broker accepted the request but rejected the order itself (e.g. invalid
    size, market closed, insufficient margin)."""

    def __init__(self, message: str, reason_code: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code
