import hashlib
import mimetypes
import unicodedata
import uuid
from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from app.api.deps import DB, CurrentUser, ensure_storage_quota
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import get_logger
from app.models.analysis import UploadedFile
from app.schemas.analysis import UploadedFileResponse
from app.services.file_processor import FileProcessor

router = APIRouter()
logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".parquet", ".tsv"}


def _validate_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{suffix}' is not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    return suffix


@router.post("", response_model=UploadedFileResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.upload_rate_limit_per_minute}/minute")
async def upload_file(
    request: Request,
    current_user: CurrentUser,
    db: DB,
    file: UploadFile = File(...),
    original_filename: Annotated[str | None, Form(max_length=512)] = None,
):
    """Upload a data file for analysis."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Native upload libraries may put a cache UUID in the multipart filename.
    # Read the cached form to distinguish an explicitly empty name from omission.
    supplied_name = original_filename
    if supplied_name is None:
        supplied_name = (await request.form()).get("original_filename")
    filename = file.filename
    if supplied_name is not None:
        if (
            not isinstance(supplied_name, str)
            or not supplied_name.strip()
            or len(supplied_name) > 512
            or "/" in supplied_name
            or "\\" in supplied_name
            or any(unicodedata.category(character) == "Cc" for character in supplied_name)
        ):
            raise HTTPException(status_code=400, detail="Use an original file name without folders or control characters.")
        filename = supplied_name

    ext = _validate_extension(filename)

    # Check file size before reading
    if file.size and file.size > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {settings.max_upload_size_bytes // (1024*1024)} MB",
        )

    # Read file content
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large",
        )

    ensure_storage_quota(current_user, len(content))

    # Compute checksum
    checksum = hashlib.sha256(content).hexdigest()

    # Save to disk
    upload_dir = Path(settings.upload_dir) / str(current_user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = upload_dir / unique_name

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Profile the file
    processor = FileProcessor()
    try:
        profile = await processor.profile(str(file_path), ext)
    except Exception as exc:
        logger.warning("File profiling failed", exc=str(exc))
        profile = {"row_count": None, "column_count": None, "columns": None}

    # Store in DB
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    uploaded_file = UploadedFile(
        user_id=current_user.id,
        filename=unique_name,
        original_filename=filename,
        file_size=len(content),
        mime_type=mime_type,
        storage_path=str(file_path),
        row_count=profile.get("row_count"),
        column_count=profile.get("column_count"),
        columns=profile.get("columns"),
        checksum=checksum,
    )
    db.add(uploaded_file)
    await db.flush()
    await db.refresh(uploaded_file)

    # Update user storage usage
    current_user.storage_used_bytes = (current_user.storage_used_bytes or 0) + len(content)

    logger.info(
        "File uploaded",
        file_id=str(uploaded_file.id),
        user_id=str(current_user.id),
        size=len(content),
    )
    return uploaded_file
