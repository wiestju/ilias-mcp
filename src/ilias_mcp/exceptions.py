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


class DownloadError(IliasMcpError):
    """Raised when a file download returns something other than the file
    (observed live: an HTML page instead of binary content) even after a
    forced re-login retry — most often a transient session/server hiccup
    rather than a real file-not-found."""
