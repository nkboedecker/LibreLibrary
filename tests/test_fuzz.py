"""Fuzz every operation in the spec: no input may cause a server error."""

from typing import Any

import schemathesis
from fastapi import FastAPI
from hypothesis import HealthCheck, settings
from pytest import fixture
from schemathesis.generation.case import Case
from schemathesis.schemas import BaseSchema

from .conftest import MakeAccount

api_schema = schemathesis.pytest.from_fixture("loaded_schema")
WITHOUT_BEARER = {"health_get", "auth_login"}
ALL_SCOPES = ("library:read", "library:write", "admin")


def operation_id(case: Case[Any]) -> object:
    """Return the operation that a case calls."""
    return case.operation.definition.raw.get("operationId")


@fixture
def loaded_schema(app: FastAPI) -> BaseSchema:
    """Load the spec that the application generates."""
    schema = schemathesis.openapi.from_dict(app.openapi())
    schema.app = app
    return schema


@api_schema.parametrize()
@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.filter_too_much,
        HealthCheck.too_slow,
    ],
)
def test_no_input_causes_a_server_error(
    case: Case[Any], make_account: MakeAccount
) -> None:
    """Whatever arrives, the answer is never a 5xx.

    Each case gets its own admin, because a fuzzed request can revoke a token. A
    shared caller would turn every later case into a 401, which proves nothing.
    Schemathesis also strips the header from some cases on purpose, to test
    anonymous access, so a 401 is a failure only when a token was sent.
    """
    caller = make_account("admin", scopes=ALL_SCOPES)
    response = case.call(headers=caller.headers)
    assert response.status_code < 500, response.text
    sent_token = "Authorization" in response.request.headers
    if sent_token and operation_id(case) not in WITHOUT_BEARER:
        assert response.status_code != 401, "the caller's token was refused"
