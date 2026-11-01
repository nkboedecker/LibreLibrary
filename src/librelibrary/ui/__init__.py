"""The server-rendered web interface.

Every route here is a thin caller of the service layer, like the REST routes.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

HTTP_METHODS = {"GET": "get", "POST": "post"}


def ui_route(
    router: APIRouter, method: str, path: str, *, api: str | None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a page route and declare the REST operation it fulfills.

    `api` is the `operationId` of the API operation that does the same job, so a
    test can confirm that the interface can't do what the API can't. A page that
    reads or changes no records, such as the sign-in form, passes `api=None`, and
    the parity tests list it by name.
    """

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        function.__ui_api__ = api  # type: ignore[attr-defined]
        register = getattr(router, HTTP_METHODS[method])
        register(path, include_in_schema=False)(function)
        return function

    return decorate
