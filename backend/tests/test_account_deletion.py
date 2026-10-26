"""Account removal, retry handling, and protection against stale JWT provisioning."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api import deps
from app.api.v1.endpoints import users
from app.services import account_service


@pytest.fixture
def remote(monkeypatch):
    requests = []
    result = {"status": 200, "body": {}}

    async def respond(request):
        requests.append(request)
        return httpx.Response(result["status"], json=result["body"])

    original = httpx.AsyncClient
    monkeypatch.setattr(
        account_service.httpx, "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
    )
    monkeypatch.setattr(account_service.settings, "supabase_url", "https://test.supabase.co")
    monkeypatch.setattr(account_service.settings, "supabase_anon_key", "test-anon")
    monkeypatch.setattr(account_service.settings, "supabase_service_role_key", "test-service")
    return requests, result


@pytest.mark.parametrize("status", [200, 204, 404])
async def test_remote_delete_is_hard_and_retryable(remote, status):
    requests, result = remote
    result["status"] = status
    subject = str(uuid.uuid4())
    await account_service.delete_auth_user(subject)
    assert requests[0].url.path == f"/auth/v1/admin/users/{subject}"
    assert requests[0].headers["authorization"] == "Bearer test-service"
    assert b'"should_soft_delete":false' in requests[0].content


async def test_remote_failure_does_not_expose_credentials(remote):
    _, result = remote
    result["status"] = 500
    with pytest.raises(HTTPException) as error:
        await account_service.delete_auth_user(str(uuid.uuid4()))
    assert error.value.status_code == 503
    assert "test-service" not in error.value.detail


@pytest.mark.parametrize("status,body", [(401, {}), (404, {}), (200, {"id": "other"})])
async def test_stale_or_wrong_auth_user_cannot_provision(remote, status, body):
    _, result = remote
    result.update(status=status, body=body)
    with pytest.raises(HTTPException) as error:
        await account_service.confirm_auth_user("old-token", "deleted-user")
    assert error.value.status_code == 401


async def test_live_auth_user_can_provision(remote):
    requests, result = remote
    result["body"] = {"id": "live-user"}
    await account_service.confirm_auth_user("live-token", "live-user")
    assert requests[0].headers["authorization"] == "Bearer live-token"


async def test_deleted_token_never_creates_local_user(monkeypatch):
    monkeypatch.setattr(deps, "verify_supabase_token", AsyncMock(return_value={"sub": "deleted"}))
    confirm = AsyncMock(side_effect=HTTPException(401, "Invalid or deleted account"))
    monkeypatch.setattr(account_service, "confirm_auth_user", confirm)
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=None))
    with pytest.raises(HTTPException) as error:
        await deps.get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials="stale"), db)
    assert error.value.status_code == 401
    db.flush.assert_not_awaited()


def test_cleanup_removes_only_owned_directory(tmp_path, monkeypatch):
    owner, stranger = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(account_service.settings, "upload_dir", str(tmp_path))
    for subject in (owner, stranger):
        folder = tmp_path / str(subject)
        folder.mkdir()
        (folder / "upload.csv").write_text("private")
    account_service.delete_account_uploads(owner)
    account_service.delete_account_uploads(owner)  # repeat cleanup is harmless
    assert not (tmp_path / str(owner)).exists()
    assert (tmp_path / str(stranger) / "upload.csv").read_text() == "private"


@pytest.fixture
def deletion(monkeypatch):
    auth_delete = AsyncMock()
    cleanup = Mock()
    monkeypatch.setattr(users, "delete_auth_user", auth_delete)
    monkeypatch.setattr(users, "delete_account_uploads", cleanup)
    owner = SimpleNamespace(id=uuid.uuid4(), supabase_id=str(uuid.uuid4()))
    db = AsyncMock()
    db.execute.side_effect = [
        Mock(first=Mock(return_value=None)),
        Mock(scalar_one_or_none=Mock(return_value=None)),
        Mock(),
    ]
    return owner, db, auth_delete, cleanup


async def test_delete_commits_after_remote_and_file_cleanup(deletion):
    owner, db, remote_delete, cleanup = deletion
    response = await users.delete_me(owner, db)
    assert response.status_code == 204
    remote_delete.assert_awaited_once_with(owner.supabase_id)
    cleanup.assert_called_once_with(owner.id)
    db.commit.assert_awaited_once()
    delete_statement = db.execute.await_args_list[2].args[0]
    assert delete_statement.compile().params == {"id_1": owner.id}


async def test_running_analysis_blocks_deletion(deletion):
    owner, db, remote_delete, cleanup = deletion
    db.execute.side_effect = [Mock(first=Mock(return_value=(uuid.uuid4(),)))]
    with pytest.raises(HTTPException) as error:
        await users.delete_me(owner, db)
    assert error.value.status_code == 409
    remote_delete.assert_not_awaited()
    cleanup.assert_not_called()
    db.commit.assert_not_awaited()


async def test_paid_subscription_blocks_deletion(deletion):
    owner, db, remote_delete, _ = deletion
    db.execute.side_effect = [
        Mock(first=Mock(return_value=None)),
        Mock(scalar_one_or_none=Mock(return_value=SimpleNamespace(
            stripe_subscription_id="sub-test", status="active",
        ))),
    ]
    with pytest.raises(HTTPException) as error:
        await users.delete_me(owner, db)
    assert error.value.status_code == 409
    remote_delete.assert_not_awaited()


async def test_remote_failure_preserves_local_data(deletion):
    owner, db, remote_delete, cleanup = deletion
    remote_delete.side_effect = HTTPException(503, "retry")
    with pytest.raises(HTTPException):
        await users.delete_me(owner, db)
    db.commit.assert_not_awaited()
    cleanup.assert_not_called()


async def test_cleanup_failure_leaves_local_transaction_uncommitted(deletion):
    owner, db, _, cleanup = deletion
    cleanup.side_effect = PermissionError("locked")
    with pytest.raises(HTTPException) as error:
        await users.delete_me(owner, db)
    assert error.value.status_code == 503
    db.commit.assert_not_awaited()
