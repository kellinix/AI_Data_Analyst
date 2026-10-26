"""Run Zephyr's API, queue worker and scheduler on one Railway volume.

Staging only: these processes share /app/uploads. Set a single service replica
and attach a persistent volume there. Scale out only after shared object storage
has replaced local file paths throughout the analysis pipeline.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def prepare_upload_volume() -> None:
    """Make Railway's root-owned volume writable, then drop root privileges."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return

    import pwd

    user = pwd.getpwnam("appuser")
    upload_dir = os.environ.get("UPLOAD_DIR", "/app/uploads")
    os.makedirs(upload_dir, exist_ok=True)
    os.chown(upload_dir, user.pw_uid, user.pw_gid)
    os.initgroups(user.pw_name, user.pw_gid)
    os.setgid(user.pw_gid)
    os.setuid(user.pw_uid)


def commands() -> list[list[str]]:
    port = int(os.environ.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be a TCP port")
    return [
        ["gunicorn", "app.main:app", "--worker-class", "uvicorn.workers.UvicornWorker",
         "--workers", "1", "--bind", f"0.0.0.0:{port}", "--timeout", "120",
         "--access-logfile", "-", "--error-logfile", "-"],
        ["celery", "-A", "app.workers.celery_app", "worker", "--loglevel=warning",
         "--concurrency=1", "--queues=analysis,default,celery"],
        ["celery", "-A", "app.workers.celery_app", "beat", "--loglevel=warning"],
    ]


def main() -> int:
    prepare_upload_volume()
    children = [subprocess.Popen(command) for command in commands()]
    stopping = False

    def stop(_signal: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping:
            for child in children:
                status = child.poll()
                if status is not None:
                    print(f"Staging process {child.args[0]} exited ({status})", file=sys.stderr)
                    return status or 1
            time.sleep(1)
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
