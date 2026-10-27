import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from scripts import run_railway_staging


def test_root_owned_upload_volume_is_fixed_before_dropping_privileges(monkeypatch):
    calls = []
    fake_os = SimpleNamespace(
        geteuid=lambda: 0,
        environ={"UPLOAD_DIR": "/app/uploads"},
        makedirs=lambda *args, **kwargs: calls.append(("makedirs", args, kwargs)),
        chown=lambda *args: calls.append(("chown", args)),
        initgroups=lambda *args: calls.append(("initgroups", args)),
        setgid=lambda value: calls.append(("setgid", value)),
        setuid=lambda value: calls.append(("setuid", value)),
    )
    monkeypatch.setattr(run_railway_staging, "os", fake_os)
    monkeypatch.setitem(
        sys.modules,
        "pwd",
        SimpleNamespace(
            getpwnam=lambda name: SimpleNamespace(
                pw_name=name, pw_uid=1001, pw_gid=1001
            )
        ),
    )

    run_railway_staging.prepare_upload_volume()

    assert calls == [
        ("makedirs", ("/app/uploads",), {"exist_ok": True}),
        ("chown", ("/app/uploads", 1001, 1001)),
        ("initgroups", ("appuser", 1001)),
        ("setgid", 1001),
        ("setuid", 1001),
    ]


def test_non_root_runtime_leaves_volume_ownership_untouched(monkeypatch):
    monkeypatch.setattr(
        run_railway_staging,
        "os",
        SimpleNamespace(geteuid=lambda: 1001),
    )
    run_railway_staging.prepare_upload_volume()


def test_celery_beat_schedule_uses_writable_upload_volume(monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", "/app/uploads")

    beat = run_railway_staging.commands()[2]

    assert beat[-2:] == ["--schedule", str(Path("/app/uploads") / "celerybeat-schedule")]


@pytest.mark.parametrize(
    "configured, expected",
    [
        (
            "https://zephyr-web-staging.up.railway.app",
            ["https://zephyr-web-staging.up.railway.app"],
        ),
        (
            "https://a.example, https://b.example",
            ["https://a.example", "https://b.example"],
        ),
        (
            '["http://localhost:3000", "http://localhost:8081"]',
            ["http://localhost:3000", "http://localhost:8081"],
        ),
    ],
)
def test_cors_origins_accept_railway_url_and_existing_json(monkeypatch, configured, expected):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", configured)

    settings = Settings(
        _env_file=None,
        secret_key="test-secret",
        openai_api_key="test-openai-key",
        database_url="postgresql://test:test@localhost:5432/test",
    )

    assert settings.cors_origins == expected
