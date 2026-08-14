class IliasMcpError(Exception):
    """Base class for all errors raised by this project."""


class LoginError(IliasMcpError):
    """Raised when a provider cannot establish an authenticated ILIAS session."""


class MissingCredentialsError(IliasMcpError):
    """Raised when required credentials are not present in the environment/.env."""


class ProviderNotFoundError(IliasMcpError):
    """Raised when the configured provider name is not registered."""


class NotLoggedInError(IliasMcpError):
    """Raised when an ILIAS operation is attempted without an authenticated session."""


class ParseError(IliasMcpError):
    """Raised when an ILIAS page does not have the HTML structure we expect.

    Kept as its own type because ILIAS page markup drifts between versions/
    installations, and callers may want to react differently (e.g. dump HTML
    for debugging) than to a generic error.
    """
