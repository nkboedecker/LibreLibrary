"""Parity rules: the web interface can do nothing the API can't.

Every page route declares the API operation it fulfills, and calls the same
service function that operation calls.
"""

import ast
import importlib
import inspect
import pkgutil
import textwrap
from collections.abc import Callable
from typing import Any, cast

import pytest
from fastapi import APIRouter
from fastapi.routing import APIRoute

import librelibrary.api.v1
import librelibrary.services
import librelibrary.ui
from librelibrary.app import create_app
from librelibrary.settings import Settings

# Pages that read or change no records, so no API operation matches them.
NO_API_EQUIVALENT = {
    "home",
    "login_form",
    "logout",
    "new_work_form",
    "new_edition_form",
    "new_library_form",
    "new_copy_form",
    "new_shelf_form",
}
SERVICE_MODULES = {
    module.name for module in pkgutil.iter_modules(librelibrary.services.__path__)
}


def page_routes() -> list[APIRoute]:
    """Return the routes of every web page router."""
    routes: list[APIRoute] = []
    seen: list[APIRouter] = []
    for module_info in pkgutil.iter_modules(librelibrary.ui.__path__):
        module = importlib.import_module(f"librelibrary.ui.{module_info.name}")
        for value in vars(module).values():
            if isinstance(value, APIRouter) and value not in seen:
                seen.append(value)
                routes.extend(r for r in value.routes if isinstance(r, APIRoute))
    return routes


def declared_api(route: APIRoute) -> str | None:
    """Return the operationId a page route declared, or None if it declared none."""
    return cast(str | None, vars(route.endpoint)["__ui_api__"])


def api_endpoints() -> dict[str, Callable[..., Any]]:
    """Return each API operation's handler by operationId."""
    endpoints = {}
    for module_info in pkgutil.iter_modules(librelibrary.api.v1.__path__):
        module = importlib.import_module(f"librelibrary.api.v1.{module_info.name}")
        router = getattr(module, "router", None)
        if router is None:
            continue
        for route in router.routes:
            if isinstance(route, APIRoute) and route.operation_id:
                endpoints[route.operation_id] = route.endpoint
    return endpoints


def service_calls(function: Callable[..., Any]) -> list[str]:
    """List the service functions a handler calls, in source order."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    calls = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in SERVICE_MODULES
        ):
            calls.append((node.lineno, node.col_offset, node.func.attr))
    return [
        f"{module}.{name}"
        for _line, _col, name in sorted(calls)
        for module in [_module_of(name)]
    ]


def _module_of(function_name: str) -> str:
    for module_name in sorted(SERVICE_MODULES):
        module = importlib.import_module(f"librelibrary.services.{module_name}")
        if hasattr(module, function_name):
            return module_name
    raise AssertionError(function_name)


def test_there_are_page_routes() -> None:
    """The rest of this file means nothing if it finds no pages."""
    assert len(page_routes()) >= 5


def test_every_page_route_declares_its_api_operation() -> None:
    """A page without a declaration fails the build."""
    undeclared = [
        route.path
        for route in page_routes()
        if not hasattr(route.endpoint, "__ui_api__")
    ]
    assert undeclared == []


def test_declared_operations_exist_in_the_spec() -> None:
    """A page can't name an operation that isn't in the API."""
    operations = set(api_endpoints())
    for route in page_routes():
        declared = declared_api(route)
        name = route.endpoint.__name__
        if declared is None:
            assert name in NO_API_EQUIVALENT, name
        else:
            assert declared in operations, name


def test_pages_without_an_api_equivalent_are_listed_and_real() -> None:
    """The exemption list can't grow stale."""
    exempt = {
        route.endpoint.__name__
        for route in page_routes()
        if declared_api(route) is None
    }
    assert exempt == NO_API_EQUIVALENT


def test_pages_are_not_in_the_api_spec() -> None:
    """The spec describes the API alone."""
    app = create_app(Settings(database_url="sqlite://"))
    assert all(path.startswith("/api/") for path in app.openapi()["paths"])


@pytest.mark.parametrize(
    "route",
    [route for route in page_routes() if declared_api(route) is not None],
    ids=lambda route: route.endpoint.__name__,
)
def test_a_page_and_its_operation_call_the_same_service(route: APIRoute) -> None:
    """The page calls the service function that the API operation calls first."""
    operation = declared_api(route)
    assert operation
    api_calls = service_calls(api_endpoints()[operation])
    page_calls = service_calls(route.endpoint)

    assert api_calls
    assert api_calls[0] in page_calls
