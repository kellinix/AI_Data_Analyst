import sys
from types import SimpleNamespace

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
