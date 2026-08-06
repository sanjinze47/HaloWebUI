import logging
import os
import re
import uuid
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
    Query,
)
from fastapi.responses import FileResponse, StreamingResponse
from open_webui.constants import ERROR_MESSAGES
from open_webui.config import (
    FILE_MAX_TOTAL_SIZE,
    RAG_ALLOWED_FILE_MIME_TYPES,
)
from open_webui.env import SRC_LOG_LEVELS
from open_webui.models.files import (
    FileForm,
    FileModel,
    FileModelResponse,
    Files,
)
from open_webui.models.knowledge import Knowledges

from open_webui.routers.knowledge import get_knowledge, get_knowledge_list
from open_webui.routers.retrieval import ProcessFileForm, process_file
from open_webui.routers.audio import transcribe
from open_webui.retrieval.document_processing import (
    get_file_effective_processing_mode,
    resolve_file_processing_mode_from_config,
)
from open_webui.retrieval.vector.connector import VECTOR_DB_CLIENT
from open_webui.storage.provider import Storage
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_access
from open_webui.utils.file_upload_diagnostics import (
    build_file_upload_error_detail,
    classify_file_upload_error,
    is_archive_file,
)
from pydantic import BaseModel

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


router = APIRouter()


_SIZE_SUFFIXES = {
    "kb": 1024,
    "kib": 1024,
    "mb": 1024 * 1024,
    "mib": 1024 * 1024,
    "gb": 1024 * 1024 * 1024,
    "gib": 1024 * 1024 * 1024,
}


def _unwrap_config_value(value):
    return getattr(value, "value", value)


def _coerce_size_limit_bytes(value, *, default_unit: str = "mb") -> Optional[int]:
    value = _unwrap_config_value(value)
    if value is None or value is False or value == "":
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        number = float(value)
        unit = default_unit
    else:
        match = re.fullmatch(
            r"\s*(\d+(?:\.\d+)?)\s*([kmgt]?i?b)?\s*", str(value), re.I
        )
        if not match:
            return None
        number = float(match.group(1))
        unit = (match.group(2) or default_unit).lower()

    if number <= 0:
        return None
    multiplier = _SIZE_SUFFIXES.get(unit, 1024 * 1024)
    return max(1, int(number * multiplier))


def _read_upload_size(file: UploadFile) -> int:
    stream = file.file
    current_position = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if current_position and size == 0:
        stream.seek(current_position)
    return max(0, int(size))


def _normalize_mime_type(content_type: Optional[str]) -> str:
    return str(content_type or "").split(";", 1)[0].strip().lower()


def _normalize_allowed_values(value, *, strip_dot: bool = False) -> list[str]:
    value = _unwrap_config_value(value)
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        return []

    normalized = []
    for item in values:
        item = str(item or "").strip().lower()
        if strip_dot:
            item = item.lstrip(".")
        if item:
            normalized.append(item)
    return normalized


def _get_allowed_mime_types(request: Request) -> list[str]:
    configured = getattr(request.app.state.config, "ALLOWED_FILE_MIME_TYPES", None)
    if configured is None:
        configured = RAG_ALLOWED_FILE_MIME_TYPES
    return _normalize_allowed_values(configured)



def _mime_type_is_allowed(content_type: str, allowed_types: list[str]) -> bool:
    if not allowed_types:
        return True
    return any(
        allowed == content_type
        or (allowed.endswith("/*") and content_type.startswith(allowed[:-1]))
        for allowed in allowed_types
    )


def _build_upload_validation_diagnostic(
    code: str,
    *,
    filename: str,
    message: str,
    hint: str,
    size: Optional[int] = None,
    limit: Optional[int] = None,
    content_type: Optional[str] = None,
) -> dict:
    diagnostic = {
        "code": code,
        "title": "File upload validation failed.",
        "message": message,
        "hint": hint,
        "blocking": True,
        "filename": filename,
    }
    if size is not None:
        diagnostic["size"] = size
    if limit is not None:
        diagnostic["limit"] = limit
    if content_type:
        diagnostic["content_type"] = content_type
    return diagnostic


def _validate_uploaded_file(
    request: Request,
    file: UploadFile,
    *,
    filename: str,
    process: bool,
) -> int:
    size = _read_upload_size(file)
    content_type = _normalize_mime_type(file.content_type)
    if size <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "The uploaded file is empty.",
                "diagnostic": _build_upload_validation_diagnostic(
                    "empty_file",
                    filename=filename,
                    message="The uploaded file is empty.",
                    hint="Choose a non-empty file and try again.",
                    size=size,
                    content_type=content_type,
                ),
            },
        )

    config = request.app.state.config
    single_limit = _coerce_size_limit_bytes(
        getattr(config, "FILE_MAX_SIZE", None)
    )
    if single_limit is None:
        single_limit = _coerce_size_limit_bytes(
            os.environ.get("RAG_FILE_MAX_SIZE")
        )
    if single_limit is not None and size > single_limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "message": "The uploaded file exceeds the configured size limit.",
                "diagnostic": _build_upload_validation_diagnostic(
                    "file_too_large",
                    filename=filename,
                    message="The uploaded file exceeds the configured size limit.",
                    hint="Choose a smaller file or increase the upload size limit.",
                    size=size,
                    limit=single_limit,
                    content_type=content_type,
                ),
            },
        )

    allowed_mime_types = _get_allowed_mime_types(request)
    if not _mime_type_is_allowed(content_type, allowed_mime_types):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"MIME type {content_type or 'unknown'} is not allowed.",
                "diagnostic": _build_upload_validation_diagnostic(
                    "mime_type_not_allowed",
                    filename=filename,
                    message=f"MIME type {content_type or 'unknown'} is not allowed.",
                    hint="Choose a file with an allowed MIME type and try again.",
                    size=size,
                    content_type=content_type,
                ),
            },
        )

    extension = os.path.splitext(filename)[1].lstrip(".").lower()
    allowed_extensions = _normalize_allowed_values(
        getattr(config, "ALLOWED_FILE_EXTENSIONS", None), strip_dot=True
    )
    if allowed_extensions and extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"File type {extension or 'unknown'} is not allowed.",
                "diagnostic": _build_upload_validation_diagnostic(
                    "file_extension_not_allowed",
                    filename=filename,
                    message=f"File type {extension or 'unknown'} is not allowed.",
                    hint="Choose a file with an allowed extension and try again.",
                    size=size,
                    content_type=content_type,
                ),
            },
        )

    return size


def _cleanup_failed_uploaded_file(file_id: str, file_path: str | None) -> None:
    if file_id:
        try:
            file_collection = f"file-{file_id}"
            if VECTOR_DB_CLIENT.has_collection(collection_name=file_collection):
                VECTOR_DB_CLIENT.delete_collection(collection_name=file_collection)
        except Exception as exc:
            log.debug("Failed to delete temporary file collection %s: %s", file_id, exc)

        try:
            _clear_file_remote_cache(Files.get_file_by_id(file_id))
        except Exception as exc:
            log.debug("Failed to clear remote file cache %s: %s", file_id, exc)

        try:
            Files.delete_file_by_id(file_id)
        except Exception as exc:
            log.debug("Failed to delete file record %s: %s", file_id, exc)

    if file_path:
        try:
            Storage.delete_file(file_path)
        except Exception as exc:
            log.debug("Failed to delete uploaded file %s: %s", file_path, exc)


def _clear_file_remote_cache(file_obj: Optional[FileModel]) -> None:
    if not file_obj:
        return
    meta = dict(file_obj.meta or {})
    openai_meta = dict(meta.get("openai") or {})
    files_map = openai_meta.get("files")
    if not isinstance(files_map, dict) or not files_map:
        return
    openai_meta["files"] = {}
    meta["openai"] = openai_meta
    try:
        Files.update_file_metadata_by_id(file_obj.id, meta)
    except Exception as exc:
        log.debug("Failed to clear remote file cache for %s: %s", file_obj.id, exc)


############################
# Check if the current user has access to a file through any knowledge bases the user may be in.
############################


def has_access_to_file(
    file_id: Optional[str], access_type: str, user=Depends(get_verified_user)
) -> bool:
    file = Files.get_file_by_id(file_id)
    log.debug(f"Checking if user has {access_type} access to file")

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    has_access = False
    knowledge_base_id = file.meta.get("collection_name") if file.meta else None

    if knowledge_base_id:
        knowledge_bases = Knowledges.get_knowledge_bases_by_user_id(
            user.id, access_type
        )
        for knowledge_base in knowledge_bases:
            if knowledge_base.id == knowledge_base_id:
                has_access = True
                break

    return has_access


def _user_can_access_file(
    file: Optional[FileModel], user, access_type: str = "read"
) -> bool:
    if not file:
        return False

    if file.user_id == user.id or user.role == "admin":
        return True

    explicit_access = file.access_control
    if explicit_access is not None and has_access(
        user.id, access_type, explicit_access
    ):
        return True

    return has_access_to_file(file.id, access_type, user)


############################
# Upload File
############################


@router.post("/", response_model=FileModelResponse)
def upload_file(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_verified_user),
    file_metadata: dict = {},
    process: bool = Query(True),
    processing_mode: Optional[str] = Query(None),
):
    log.info(f"file.content_type: {file.content_type}")
    file_path = None
    id = None
    try:
        unsanitized_filename = file.filename
        filename = os.path.basename(unsanitized_filename)

        if is_archive_file(filename, file.content_type):
            diagnostic = classify_file_upload_error(
                None,
                filename=filename,
                content_type=file.content_type,
                user=user,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=build_file_upload_error_detail(diagnostic),
            )

        upload_size = _validate_uploaded_file(
            request,
            file,
            filename=filename,
            process=process,
        )

        # replace filename with uuid
        id = str(uuid.uuid4())
        name = filename
        filename = f"{id}_{filename}"
        file_size, file_path = Storage.upload_file(file.file, filename)
        if not file_size:
            file_size = upload_size
        requested_processing_mode = resolve_file_processing_mode_from_config(
            request.app.state.config, processing_mode
        )

        file_item = Files.insert_new_file(
            user.id,
            FileForm(
                **{
                    "id": id,
                    "filename": name,
                    "path": file_path,
                    "meta": {
                        "name": name,
                        "content_type": file.content_type,
                        "size": file_size,
                        "data": file_metadata,
                        "processing_mode": requested_processing_mode,
                        "resolved_processing_mode": requested_processing_mode,
                    },
                }
            ),
        )
        # Auto mode is resolved after the final chat model/connection is known.
        # Keep the original upload untouched until then; knowledge-base uploads
        # continue to use their explicit retrieval mode.
        if process and requested_processing_mode != "auto":
            try:
                warning_message = None
                if file.content_type in [
                    "audio/mpeg",
                    "audio/wav",
                    "audio/ogg",
                    "audio/x-m4a",
                ]:
                    file_path = Storage.get_file(file_path)
                    result = transcribe(request, file_path)

                    process_file(
                        request,
                        ProcessFileForm(
                            file_id=id,
                            content=result.get("text", ""),
                            processing_mode=requested_processing_mode,
                        ),
                        user=user,
                    )
                elif not str(file.content_type or "").startswith("image/"):
                    process_result = process_file(
                        request,
                        ProcessFileForm(
                            file_id=id,
                            processing_mode=requested_processing_mode,
                        ),
                        user=user,
                    )
                    warning_message = process_result.get("notice") if process_result else None

                file_item = Files.get_file_by_id(id=id)
                if warning_message:
                    file_item = FileModelResponse(
                        **{
                            **file_item.model_dump(),
                            "error": warning_message,
                        }
                    )
            except Exception as e:
                log.exception(e)
                log.error(f"Error processing file: {file_item.id}")
                diagnostic = classify_file_upload_error(
                    e,
                    filename=name,
                    content_type=file.content_type,
                    user=user,
                )
                if diagnostic.get("blocking", True):
                    _cleanup_failed_uploaded_file(id, file_path)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=build_file_upload_error_detail(diagnostic),
                    )

                file_item = FileModelResponse(
                    **{
                        **file_item.model_dump(),
                        "error": diagnostic["message"],
                        "diagnostic": diagnostic,
                    }
                )

        if file_item:
            if isinstance(file_item, FileModelResponse):
                return file_item
            effective_mode = get_file_effective_processing_mode(
                file_item,
                default_mode=requested_processing_mode,
            )
            if effective_mode != requested_processing_mode:
                file_item = FileModelResponse(
                    **{
                        **file_item.model_dump(),
                        "error": (
                            f"文件当前已按 {effective_mode} 模式保存，"
                            f"与请求的 {requested_processing_mode} 不一致。"
                        ),
                    }
                )
            return file_item
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error uploading file"),
            )

    except HTTPException:
        raise
    except Exception as e:
        log.exception(e)
        if id:
            _cleanup_failed_uploaded_file(id, file_path)
        diagnostic = classify_file_upload_error(
            e,
            filename=getattr(file, "filename", None),
            content_type=getattr(file, "content_type", None),
            user=user,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=build_file_upload_error_detail(diagnostic),
        )


############################
# List Files
############################


@router.get("/", response_model=list[FileModelResponse])
async def list_files(user=Depends(get_verified_user), content: bool = Query(True)):
    if user.role == "admin":
        files = Files.get_files()
    else:
        files = Files.get_files_by_user_id(user.id)

    if not content:
        for file in files:
            del file.data["content"]

    return files


############################
# Search Files
############################


@router.get("/search", response_model=list[FileModelResponse])
async def search_files(
    filename: str = Query(
        ...,
        description="Filename pattern to search for. Supports wildcards such as '*.txt'",
    ),
    content: bool = Query(True),
    user=Depends(get_verified_user),
):
    """
    Search for files by filename with support for wildcard patterns.
    """
    # Get files according to user role
    if user.role == "admin":
        files = Files.get_files()
    else:
        files = Files.get_files_by_user_id(user.id)

    # Get matching files
    matching_files = [
        file for file in files if fnmatch(file.filename.lower(), filename.lower())
    ]

    if not matching_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No files found matching the pattern.",
        )

    if not content:
        for file in matching_files:
            del file.data["content"]

    return matching_files


############################
# Delete All Files
############################


@router.delete("/all")
async def delete_all_files(user=Depends(get_admin_user)):
    for file_obj in Files.get_files():
        _clear_file_remote_cache(file_obj)
    result = Files.delete_all_files()
    if result:
        try:
            Storage.delete_all_files()
        except Exception as e:
            log.exception(e)
            log.error("Error deleting files")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error deleting files"),
            )
        return {"message": "All files deleted successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error deleting files"),
        )


############################
# Get File By Id
############################


@router.get("/{id}", response_model=Optional[FileModel])
async def get_file_by_id(id: str, user=Depends(get_verified_user)):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if _user_can_access_file(file, user, "read"):
        return file
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Get File Data Content By Id
############################


@router.get("/{id}/data/content")
async def get_file_data_content_by_id(id: str, user=Depends(get_verified_user)):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if _user_can_access_file(file, user, "read"):
        return {"content": file.data.get("content", "")}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Update File Data Content By Id
############################


class ContentForm(BaseModel):
    content: str


@router.post("/{id}/data/content/update")
async def update_file_data_content_by_id(
    request: Request, id: str, form_data: ContentForm, user=Depends(get_verified_user)
):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if _user_can_access_file(file, user, "write"):
        try:
            process_file(
                request,
                ProcessFileForm(file_id=id, content=form_data.content),
                user=user,
            )
            file = Files.get_file_by_id(id=id)
        except Exception as e:
            log.exception(e)
            log.error(f"Error processing file: {file.id}")

        return {"content": file.data.get("content", "")}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Get File Content By Id
############################


@router.get("/{id}/content")
async def get_file_content_by_id(
    id: str, user=Depends(get_verified_user), attachment: bool = Query(False)
):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if _user_can_access_file(file, user, "read"):
        try:
            file_path = Storage.get_file(file.path)
            file_path = Path(file_path)

            # Check if the file already exists in the cache
            if file_path.is_file():
                # Handle Unicode filenames
                filename = file.meta.get("name", file.filename)
                encoded_filename = quote(filename)  # RFC5987 encoding

                content_type = file.meta.get("content_type")
                filename = file.meta.get("name", file.filename)
                encoded_filename = quote(filename)
                headers = {}

                if attachment:
                    headers["Content-Disposition"] = (
                        f"attachment; filename*=UTF-8''{encoded_filename}"
                    )
                else:
                    if content_type == "application/pdf" or filename.lower().endswith(
                        ".pdf"
                    ):
                        headers["Content-Disposition"] = (
                            f"inline; filename*=UTF-8''{encoded_filename}"
                        )
                        content_type = "application/pdf"
                    elif content_type != "text/plain":
                        headers["Content-Disposition"] = (
                            f"attachment; filename*=UTF-8''{encoded_filename}"
                        )

                return FileResponse(file_path, headers=headers, media_type=content_type)

            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ERROR_MESSAGES.NOT_FOUND,
                )
        except Exception as e:
            log.exception(e)
            log.error("Error getting file content")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error getting file content"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.get("/{id}/content/html")
async def get_html_file_content_by_id(id: str, user=Depends(get_verified_user)):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if _user_can_access_file(file, user, "read"):
        try:
            file_path = Storage.get_file(file.path)
            file_path = Path(file_path)

            # Check if the file already exists in the cache
            if file_path.is_file():
                log.info(f"file_path: {file_path}")
                return FileResponse(file_path)
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ERROR_MESSAGES.NOT_FOUND,
                )
        except Exception as e:
            log.exception(e)
            log.error("Error getting file content")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error getting file content"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.get("/{id}/content/{file_name}")
async def get_file_content_by_id(id: str, user=Depends(get_verified_user)):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if _user_can_access_file(file, user, "read"):
        file_path = file.path

        # Handle Unicode filenames
        filename = file.meta.get("name", file.filename)
        encoded_filename = quote(filename)  # RFC5987 encoding
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }

        if file_path:
            file_path = Storage.get_file(file_path)
            file_path = Path(file_path)

            # Check if the file already exists in the cache
            if file_path.is_file():
                return FileResponse(file_path, headers=headers)
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ERROR_MESSAGES.NOT_FOUND,
                )
        else:
            # File path doesn’t exist, return the content as .txt if possible
            file_content = file.content.get("content", "")
            file_name = file.filename

            # Create a generator that encodes the file content
            def generator():
                yield file_content.encode("utf-8")

            return StreamingResponse(
                generator(),
                media_type="text/plain",
                headers=headers,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# Delete File By Id
############################


@router.delete("/{id}")
async def delete_file_by_id(id: str, user=Depends(get_verified_user)):
    file = Files.get_file_by_id(id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if _user_can_access_file(file, user, "write"):
        # We should add Chroma cleanup here

        _clear_file_remote_cache(file)
        result = Files.delete_file_by_id(id)
        if result:
            try:
                Storage.delete_file(file.path)
            except Exception as e:
                log.exception(e)
                log.error("Error deleting files")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("Error deleting files"),
                )
            return {"message": "File deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error deleting file"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
