"""Errors that services raise and the application turns into responses."""


class NotFound(Exception):  # noqa: N818
    """The record doesn't exist, or the caller may not know that it does."""


class Conflict(Exception):  # noqa: N818
    """The request conflicts with the current state."""


class Unauthenticated(Exception):  # noqa: N818
    """The request has no valid credentials."""


class RateLimited(Exception):  # noqa: N818
    """Too many attempts."""
