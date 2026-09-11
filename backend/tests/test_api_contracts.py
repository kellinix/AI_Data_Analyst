from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from app.main import app
from app.schemas.user import UserCreate, UserResponse


def test_openapi_schema_generates():
    """Regression: a rate-limited endpoint in a module with `from __future__
    import annotations` left its `db: DB` dependency as an unresolved forward
    reference, so /api/openapi.json (and /api/docs) returned 500."""
    schema = app.openapi()

    assert "/api/v1/public/shared/{share_token}" in schema["paths"]


def test_no_route_takes_a_database_session_as_a_query_parameter():
    """The same failure turned the session dependency into a bogus query
    parameter, so the shared-link endpoint could never get a database session."""
    offenders = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and any(param.name == "db" for param in route.dependant.query_params)
    ]

    assert offenders == []


def test_user_response_echoes_reserved_domain_emails():
    """Regression: re-validating a stored email as EmailStr turned addresses
    Supabase accepts (e.g. @example.test) into a 500 on /users/me."""
    now = datetime.now(UTC)
    user = UserResponse.model_validate(
        {
            "email": "someone@example.test",
            "id": uuid.uuid4(),
            "plan": "free",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
    )

    assert user.email == "someone@example.test"


def test_sign_up_input_still_validates_email():
    with pytest.raises(ValidationError):
        UserCreate(email="not-an-email", supabase_id="abc")
