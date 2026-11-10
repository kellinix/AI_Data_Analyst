from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import analyses
from app.services.file_processor import FileProcessor


@pytest.mark.parametrize("mode", ["raw", "clean"])
async def test_unsafe_workbook_is_rejected_before_file_or_account_changes(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(analyses.settings, "upload_dir", str(tmp_path))
    user = SimpleNamespace(id=uuid4(), storage_used_bytes=123)
    folder = tmp_path / str(user.id)
    folder.mkdir()
    original = SimpleNamespace(storage_path=str(folder / "original.xlsx"))
    processor = FileProcessor()

    def invalid_read(*args):
        raise ValueError("The files could not be matched safely. Their ID codes disagree.")

    async def invalid_clean(source, extension, parquet, csv, options):
        from pathlib import Path

        Path(parquet).write_bytes(b"partial")
        Path(csv).write_text("partial")
        invalid_read()

    monkeypatch.setattr(processor, "_read_file", invalid_read)
    monkeypatch.setattr(processor, "clean_file", invalid_clean)
    with pytest.raises(HTTPException) as error:
        await analyses._create_cleaned_uploaded_file(source_file=original, current_user=user,
            db=None, processor=processor, cleaning={"mode": mode})
    assert error.value.status_code == 422
    assert "matched safely" in error.value.detail
    assert user.storage_used_bytes == 123
    assert list(folder.iterdir()) == []


async def test_raw_workbook_rerun_keeps_old_report_when_identifiers_conflict(monkeypatch):
    original = SimpleNamespace(storage_path="original.xlsx")
    report = SimpleNamespace(file=original, metadata_={}, status="completed")

    def invalid_read(*args):
        raise ValueError("The files could not be matched safely.")

    monkeypatch.setattr(FileProcessor, "_read_file", invalid_read)
    with pytest.raises(HTTPException) as error:
        await analyses._regenerate_cleaned_file_for_rerun(analysis=report,
            current_user=SimpleNamespace(id=uuid4()), db=None)
    assert error.value.status_code == 422
    assert report.file is original and report.status == "completed"
