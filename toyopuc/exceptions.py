
class ToyopucError(Exception):
    """Base error for TOYOPUC communication."""


class ToyopucProtocolError(ToyopucError):
    """Raised when the response frame is invalid or unexpected."""


class ToyopucTimeoutError(ToyopucError):
    """Raised on socket timeouts."""
