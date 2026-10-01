"""Business exceptions.

Services raise these; a single HTTP handler (see ``core/http.py``) translates them
into responses. Nothing in here knows about HTTP.
"""


class DomainError(Exception):
    """Base class for every expected, business-level failure."""


class AuthenticationError(DomainError):
    """The request carries no valid credentials."""


class NotFoundError(DomainError):
    """The requested resource does not exist."""


class ConflictError(DomainError):
    """The operation conflicts with the current state of a resource."""


class ExternalServiceError(DomainError):
    """A dependency (tool, remote API, filesystem) failed or is unavailable."""


class ConfigurationError(Exception):
    """The application is misconfigured. Raised at startup so it fails fast."""
