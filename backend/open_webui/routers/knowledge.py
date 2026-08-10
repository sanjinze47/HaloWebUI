from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
import logging
import time

from open_webui.models.knowledge import (
    Knowledges,
    KnowledgeForm,
    KnowledgeResponse,
    KnowledgeUserResponse,
)
from open_webui.models.files import Files, FileModel
from open_webui.retrieval.vector.connector import VECTOR_DB_CLIENT
from open_webui.routers.retrieval import (
    process_file,
    ProcessFileForm,
    process_files_batch,
    BatchProcessFilesForm,
    restore_vector_snapshot,
)
from open_webui.storage.provider import Storage

from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_verified_user
from open_webui.utils.access_control import (
    can_read_resource,
    can_write_resource,
    ensure_requested_access_control_allowed,
    ensure_resource_acl_change_allowed,
    has_permission,
)
from open_webui.utils.file_upload_diagnostics import (
    build_file_upload_error_detail,
    classify_file_upload_error,
)


from open_webui.env import SRC_LOG_LEVELS
from open_webui.models.models import Models, ModelForm
from open_webui.retrieval.document_processing import FILE_PROCESSING_MODE_RETRIEVAL


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()


class KnowledgeFilesResponse(KnowledgeResponse):
    files: list[FileModel]


class KnowledgeSearchResponse(BaseModel):
    items: list[KnowledgeUserResponse]
    total: int


class KnowledgeFileSearchResponse(BaseModel):
    items: list[dict]
    total: int


############################
# getKnowledgeBases
############################


@router.get("/", response_model=list[KnowledgeUserResponse])
async def get_knowledge(
    user=Depends(get_verified_user),
    page: Optional[int] = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    knowledge_bases = []

    if user.role == "admin":
        knowledge_bases = Knowledges.get_knowledge_bases()
    else:
        knowledge_bases = Knowledges.get_knowledge_bases_by_user_id(user.id, "read")

    # In-memory pagination (access control filtering happens in Python)
    if page is not None and page >= 1:
        skip = (page - 1) * limit
        knowledge_bases = knowledge_bases[skip : skip + limit]

    # Batch-load all file metadata in one query to avoid N+1
    all_file_ids = set()
    for kb in knowledge_bases:
        if kb.data:
            all_file_ids.update(kb.data.get("file_ids", []))

    all_files = (
        Files.get_file_metadatas_by_ids(list(all_file_ids)) if all_file_ids else []
    )
    file_map = {f.id: f for f in all_files}

    knowledge_with_files = []
    for knowledge_base in knowledge_bases:
        files = []
        if knowledge_base.data:
            kb_file_ids = knowledge_base.data.get("file_ids", [])
            files = [file_map[fid] for fid in kb_file_ids if fid in file_map]

            # Clean up missing file references
            if len(files) != len(kb_file_ids):
                valid_ids = [f.id for f in files]
                data = knowledge_base.data or {}
                data["file_ids"] = valid_ids
                Knowledges.update_knowledge_data_by_id(id=knowledge_base.id, data=data)

        knowledge_with_files.append(
            KnowledgeUserResponse(
                **knowledge_base.model_dump(),
                files=files,
            )
        )

    return knowledge_with_files


@router.get("/list", response_model=list[KnowledgeUserResponse])
async def get_knowledge_list(user=Depends(get_verified_user)):
    knowledge_bases = []

    if user.role == "admin":
        knowledge_bases = Knowledges.get_knowledge_bases()
    else:
        knowledge_bases = Knowledges.get_knowledge_bases_by_user_id(user.id, "write")

    # Batch-load all file metadata in one query to avoid N+1
    all_file_ids = set()
    for kb in knowledge_bases:
        if kb.data:
            all_file_ids.update(kb.data.get("file_ids", []))

    all_files = (
        Files.get_file_metadatas_by_ids(list(all_file_ids)) if all_file_ids else []
    )
    file_map = {f.id: f for f in all_files}

    knowledge_with_files = []
    for knowledge_base in knowledge_bases:
        files = []
        if knowledge_base.data:
            kb_file_ids = knowledge_base.data.get("file_ids", [])
            files = [file_map[fid] for fid in kb_file_ids if fid in file_map]

            # Clean up missing file references
            if len(files) != len(kb_file_ids):
                valid_ids = [f.id for f in files]
                data = knowledge_base.data or {}
                data["file_ids"] = valid_ids
                Knowledges.update_knowledge_data_by_id(id=knowledge_base.id, data=data)

        knowledge_with_files.append(
            KnowledgeUserResponse(
                **knowledge_base.model_dump(),
                files=files,
            )
        )
    return knowledge_with_files


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge_bases(
    query: Optional[str] = None,
    view_option: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    user=Depends(get_verified_user),
):
    knowledge_bases = (
        Knowledges.get_knowledge_bases()
        if user.role == "admin"
        else Knowledges.get_knowledge_bases_by_user_id(user.id, "read")
    )

    filtered = knowledge_bases
    if view_option == "created":
        filtered = [item for item in filtered if item.user_id == user.id]
    elif view_option == "shared":
        filtered = [item for item in filtered if item.user_id != user.id]

    if query:
        query_lower = query.strip().lower()
        filtered = [
            item
            for item in filtered
            if query_lower in (item.name or "").lower()
            or query_lower in (item.description or "").lower()
            or query_lower in ((item.user.name if item.user else "") or "").lower()
            or query_lower in ((item.user.email if item.user else "") or "").lower()
        ]

    total = len(filtered)
    offset = (page - 1) * limit
    return KnowledgeSearchResponse(items=filtered[offset : offset + limit], total=total)


@router.get("/search/files", response_model=KnowledgeFileSearchResponse)
async def search_knowledge_files(
    query: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    user=Depends(get_verified_user),
):
    knowledge_bases = (
        Knowledges.get_knowledge_bases()
        if user.role == "admin"
        else Knowledges.get_knowledge_bases_by_user_id(user.id, "read")
    )

    file_to_collection: dict[str, dict] = {}
    all_file_ids: list[str] = []
    for knowledge_base in knowledge_bases:
        file_ids = (knowledge_base.data or {}).get("file_ids", [])
        for file_id in file_ids:
            all_file_ids.append(file_id)
            file_to_collection[file_id] = {
                "id": knowledge_base.id,
                "name": knowledge_base.name,
                "description": knowledge_base.description,
            }

    files = (
        Files.get_file_metadatas_by_ids(list(dict.fromkeys(all_file_ids)))
        if all_file_ids
        else []
    )
    items = []
    for file in files:
        meta = file.meta or {}
        filename = (
            meta.get("name") or meta.get("filename") or meta.get("title") or file.id
        )
        items.append(
            {
                "id": file.id,
                "meta": meta,
                "filename": filename,
                "name": filename,
                "type": "file",
                "collection": file_to_collection.get(file.id),
                "created_at": file.created_at,
                "updated_at": file.updated_at,
            }
        )

    if query:
        query_lower = query.strip().lower()
        items = [
            item
            for item in items
            if query_lower in (item.get("filename") or "").lower()
            or query_lower in ((item.get("collection") or {}).get("name") or "").lower()
            or query_lower
            in ((item.get("collection") or {}).get("description") or "").lower()
        ]

    total = len(items)
    offset = (page - 1) * limit
    return KnowledgeFileSearchResponse(
        items=items[offset : offset + limit], total=total
    )


############################
# CreateNewKnowledge
############################


@router.post("/create", response_model=Optional[KnowledgeResponse])
async def create_new_knowledge(
    request: Request, form_data: KnowledgeForm, user=Depends(get_verified_user)
):
    if user.role != "admin" and not has_permission(
        user.id, "workspace.knowledge", request.app.state.config.USER_PERMISSIONS
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    ensure_requested_access_control_allowed(
        request,
        user,
        form_data.access_control,
        public_permission_key="sharing.public_knowledge",
    )

    knowledge = Knowledges.insert_new_knowledge(user.id, form_data)

    if knowledge:
        return knowledge
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.FILE_EXISTS,
        )


############################
# ReindexKnowledgeFiles
############################


@router.post("/reindex", response_model=bool)
async def reindex_knowledge_files(request: Request, user=Depends(get_verified_user)):
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    knowledge_bases = Knowledges.get_knowledge_bases()

    log.info(f"Starting reindexing for {len(knowledge_bases)} knowledge bases")

    for knowledge_base in knowledge_bases:
        try:
            files = Files.get_files_by_ids(knowledge_base.data.get("file_ids", []))
            vector_snapshot = None
            if VECTOR_DB_CLIENT.has_collection(collection_name=knowledge_base.id):
                vector_snapshot = VECTOR_DB_CLIENT.get(
                    collection_name=knowledge_base.id
                )

            failed_files = []
            for file in files:
                try:
                    process_file(
                        request,
                        ProcessFileForm(
                            file_id=file.id,
                            collection_name=knowledge_base.id,
                            overwrite=True,
                        ),
                        user=user,
                    )
                except Exception as e:
                    log.error(
                        f"Error processing file {file.filename} (ID: {file.id}): {str(e)}"
                    )
                    failed_files.append({"file_id": file.id, "error": str(e)})
                    continue

        except Exception as e:
            log.error(f"Error processing knowledge base {knowledge_base.id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing knowledge base",
            )

        if failed_files:
            log.warning(
                f"Failed to process {len(failed_files)} files in knowledge base {knowledge_base.id}"
            )
            for failed in failed_files:
                log.warning(f"File ID: {failed['file_id']}, Error: {failed['error']}")
            try:
                restore_vector_snapshot(
                    request,
                    knowledge_base.id,
                    vector_snapshot,
                    user=user,
                )
            except Exception as rollback_error:
                log.exception(
                    "Failed to restore knowledge snapshot for %s",
                    knowledge_base.id,
                )
                failed_files.append(
                    {"file_id": None, "error": f"rollback failed: {rollback_error}"}
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "knowledge_reindex_failed",
                    "failed_files": failed_files,
                },
            )

    log.info("Reindexing completed successfully")
    return True


############################
# GetKnowledgeById
############################


@router.get("/{id}", response_model=Optional[KnowledgeFilesResponse])
async def get_knowledge_by_id(id: str, user=Depends(get_verified_user)):
    knowledge = Knowledges.get_knowledge_by_id(id=id)

    if knowledge:

        if can_read_resource(user, knowledge):

            file_ids = knowledge.data.get("file_ids", []) if knowledge.data else []
            files = Files.get_files_by_ids(file_ids)

            return KnowledgeFilesResponse(
                **knowledge.model_dump(),
                files=files,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# UpdateKnowledgeById
############################


@router.post("/{id}/update", response_model=Optional[KnowledgeFilesResponse])
async def update_knowledge_by_id(
    request: Request,
    id: str,
    form_data: KnowledgeForm,
    user=Depends(get_verified_user),
):
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    if "access_control" not in getattr(form_data, "model_fields_set", set()):
        form_data.access_control = knowledge.access_control

    ensure_resource_acl_change_allowed(
        request,
        user,
        knowledge,
        form_data.access_control,
        public_permission_key="sharing.public_knowledge",
    )

    knowledge = Knowledges.update_knowledge_by_id(id=id, form_data=form_data)
    if knowledge:
        file_ids = knowledge.data.get("file_ids", []) if knowledge.data else []
        files = Files.get_files_by_ids(file_ids)

        return KnowledgeFilesResponse(
            **knowledge.model_dump(),
            files=files,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.ID_TAKEN,
        )


############################
# AddFileToKnowledge
############################


class KnowledgeFileIdForm(BaseModel):
    file_id: str
    overwrite: bool = False


@router.post("/{id}/file/add", response_model=Optional[KnowledgeFilesResponse])
def add_file_to_knowledge_by_id(
    request: Request,
    id: str,
    form_data: KnowledgeFileIdForm,
    user=Depends(get_verified_user),
):
    knowledge = Knowledges.get_knowledge_by_id(id=id)

    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    file = Files.get_file_by_id(form_data.file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Add content to the vector database
    try:
        process_result = process_file(
            request,
            ProcessFileForm(
                file_id=form_data.file_id,
                collection_name=id,
                overwrite=form_data.overwrite,
                processing_mode=FILE_PROCESSING_MODE_RETRIEVAL,
            ),
            user=user,
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        log.debug(e)
        diagnostic = classify_file_upload_error(
            e,
            filename=file.filename,
            content_type=file.meta.get("content_type") if file.meta else None,
            user=user,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=build_file_upload_error_detail(diagnostic),
        )

    if knowledge:
        data = knowledge.data or {}
        file_ids = data.get("file_ids", [])

        if form_data.file_id not in file_ids:
            file_ids.append(form_data.file_id)
            data["file_ids"] = file_ids

            knowledge = Knowledges.update_knowledge_data_by_id(id=id, data=data)

            if knowledge:
                files = Files.get_files_by_ids(file_ids)

                return KnowledgeFilesResponse(
                    **knowledge.model_dump(),
                    files=files,
                    warnings=(
                        {
                            "message": "知识库文件已强制转为检索模式。",
                            "processing_notice": process_result.get("notice"),
                        }
                        if process_result
                        and process_result.get("processing_mode")
                        != (file.meta or {}).get("processing_mode")
                        else None
                    ),
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("knowledge"),
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("file_id"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.post("/{id}/file/update", response_model=Optional[KnowledgeFilesResponse])
def update_file_from_knowledge_by_id(
    request: Request,
    id: str,
    form_data: KnowledgeFileIdForm,
    user=Depends(get_verified_user),
):
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    file = Files.get_file_by_id(form_data.file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Add content to the vector database
    try:
        process_file(
            request,
            ProcessFileForm(
                file_id=form_data.file_id,
                collection_name=id,
                overwrite=True,
                processing_mode=FILE_PROCESSING_MODE_RETRIEVAL,
            ),
            user=user,
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        diagnostic = classify_file_upload_error(
            e,
            filename=file.filename,
            content_type=file.meta.get("content_type") if file.meta else None,
            user=user,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=build_file_upload_error_detail(diagnostic),
        )

    if knowledge:
        data = knowledge.data or {}
        file_ids = data.get("file_ids", [])

        files = Files.get_files_by_ids(file_ids)

        return KnowledgeFilesResponse(
            **knowledge.model_dump(),
            files=files,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# RemoveFileFromKnowledge
############################


@router.post("/{id}/file/remove", response_model=Optional[KnowledgeFilesResponse])
def remove_file_from_knowledge_by_id(
    id: str,
    form_data: KnowledgeFileIdForm,
    user=Depends(get_verified_user),
):
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    file = Files.get_file_by_id(form_data.file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    data = dict(knowledge.data or {})
    file_ids = list(data.get("file_ids", []))
    if form_data.file_id not in file_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("file_id"),
        )

    # This endpoint only unlinks the file from this knowledge base. The
    # standalone file record, blob and file collection remain reusable.
    try:
        VECTOR_DB_CLIENT.delete(
            collection_name=knowledge.id, filter={"file_id": form_data.file_id}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "knowledge_file_unlink_pending",
                "message": "Knowledge vector cleanup failed and can be retried.",
            },
        ) from e

    if knowledge:
        file_ids.remove(form_data.file_id)
        data["file_ids"] = file_ids

        knowledge = Knowledges.update_knowledge_data_by_id(id=id, data=data)

        if knowledge:
            files = Files.get_files_by_ids(file_ids)

            return KnowledgeFilesResponse(
                **knowledge.model_dump(),
                files=files,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("knowledge"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# DeleteKnowledgeById
############################


def _cleanup_state(knowledge, operation: str, error: Optional[str] = None) -> dict:
    meta = dict(knowledge.meta or {})
    previous = dict(meta.get("vector_cleanup") or {})
    now = int(time.time())
    cleanup = {
        "operation": operation,
        "status": "pending",
        "attempts": int(previous.get("attempts") or 0) + 1,
        "requested_at": int(previous.get("requested_at") or now),
        "last_attempt_at": now,
        "last_error": error,
    }
    meta["vector_cleanup"] = cleanup
    return meta


def _delete_knowledge_vectors_or_mark_pending(knowledge, operation: str):
    meta = _cleanup_state(knowledge, operation)
    if not Knowledges.update_knowledge_meta_by_id(knowledge.id, meta):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "knowledge_cleanup_state_failed",
                "message": "Unable to persist knowledge cleanup state.",
            },
        )
    try:
        if VECTOR_DB_CLIENT.has_collection(collection_name=knowledge.id):
            VECTOR_DB_CLIENT.delete_collection(collection_name=knowledge.id)
    except Exception as exc:
        current = Knowledges.get_knowledge_by_id(knowledge.id) or knowledge
        meta = _cleanup_state(current, operation, str(exc))
        Knowledges.update_knowledge_meta_by_id(knowledge.id, meta)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "knowledge_cleanup_pending",
                "message": "Knowledge vector cleanup failed and can be retried.",
            },
        ) from exc

    # Keep the durable marker until the caller commits the matching metadata
    # operation. A process exit after vector deletion must remain recoverable.
    return Knowledges.get_knowledge_by_id(knowledge.id) or knowledge


def _remove_knowledge_model_references(knowledge_id: str) -> None:
    for model in Models.get_all_models():
        if not model.meta or not hasattr(model.meta, "knowledge"):
            continue
        knowledge_list = model.meta.knowledge or []
        updated_knowledge = [
            item for item in knowledge_list if item.get("id") != knowledge_id
        ]
        if len(updated_knowledge) == len(knowledge_list):
            continue
        model.meta.knowledge = updated_knowledge
        updated = Models.update_model_by_id(
            model.id,
            ModelForm(
                id=model.id,
                name=model.name,
                base_model_id=model.base_model_id,
                meta=model.meta,
                params=model.params,
                access_control=model.access_control,
                is_active=model.is_active,
            ),
        )
        if not updated:
            raise RuntimeError(
                f"Unable to remove knowledge {knowledge_id} from model {model.id}."
            )


def retry_pending_knowledge_cleanups() -> None:
    """Best-effort startup retry for durable vector cleanup records."""
    for knowledge in Knowledges.get_knowledge_bases():
        cleanup = dict((knowledge.meta or {}).get("vector_cleanup") or {})
        if cleanup.get("status") != "pending":
            continue
        operation = cleanup.get("operation")
        if operation not in {"delete", "reset"}:
            continue
        try:
            if VECTOR_DB_CLIENT.has_collection(collection_name=knowledge.id):
                VECTOR_DB_CLIENT.delete_collection(collection_name=knowledge.id)
            if operation == "delete":
                _remove_knowledge_model_references(knowledge.id)
                if not Knowledges.delete_knowledge_by_id(knowledge.id):
                    raise RuntimeError("Unable to delete knowledge metadata.")
                continue
            if not Knowledges.update_knowledge_data_by_id(
                id=knowledge.id, data={"file_ids": []}
            ):
                raise RuntimeError("Unable to reset knowledge metadata.")
            meta = dict(knowledge.meta or {})
            meta.pop("vector_cleanup", None)
            if not Knowledges.update_knowledge_meta_by_id(knowledge.id, meta):
                raise RuntimeError("Unable to clear knowledge cleanup state.")
        except Exception as exc:
            log.warning("Knowledge cleanup retry failed for %s: %s", knowledge.id, exc)
            Knowledges.update_knowledge_meta_by_id(
                knowledge.id, _cleanup_state(knowledge, operation, str(exc))
            )


@router.delete("/{id}/delete", response_model=bool)
async def delete_knowledge_by_id(id: str, user=Depends(get_verified_user)):
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    log.info(f"Deleting knowledge base: {id} (name: {knowledge.name})")

    knowledge = _delete_knowledge_vectors_or_mark_pending(knowledge, "delete")
    try:
        _remove_knowledge_model_references(id)
    except Exception as exc:
        Knowledges.update_knowledge_meta_by_id(
            knowledge.id,
            _cleanup_state(knowledge, "delete", str(exc)),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "knowledge_cleanup_pending"},
        ) from exc
    result = Knowledges.delete_knowledge_by_id(id=id)
    if not result:
        Knowledges.update_knowledge_meta_by_id(
            knowledge.id,
            _cleanup_state(knowledge, "delete", "Unable to delete knowledge metadata."),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "knowledge_cleanup_pending"},
        )
    return result


############################
# ResetKnowledgeById
############################


@router.post("/{id}/reset", response_model=Optional[KnowledgeResponse])
async def reset_knowledge_by_id(id: str, user=Depends(get_verified_user)):
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    knowledge = _delete_knowledge_vectors_or_mark_pending(knowledge, "reset")

    knowledge = Knowledges.update_knowledge_data_by_id(id=id, data={"file_ids": []})
    if not knowledge:
        current = Knowledges.get_knowledge_by_id(id)
        if current:
            Knowledges.update_knowledge_meta_by_id(
                id,
                _cleanup_state(
                    current,
                    "reset",
                    "Unable to reset knowledge metadata.",
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "knowledge_cleanup_pending"},
        )

    meta = dict(knowledge.meta or {})
    meta.pop("vector_cleanup", None)
    knowledge = Knowledges.update_knowledge_meta_by_id(id, meta)
    if not knowledge:
        current = Knowledges.get_knowledge_by_id(id)
        if current:
            Knowledges.update_knowledge_meta_by_id(
                id,
                _cleanup_state(
                    current,
                    "reset",
                    "Unable to clear knowledge cleanup state.",
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "knowledge_cleanup_pending"},
        )

    return knowledge


############################
# AddFilesToKnowledge
############################


@router.post("/{id}/files/batch/add", response_model=Optional[KnowledgeFilesResponse])
def add_files_to_knowledge_batch(
    request: Request,
    id: str,
    form_data: list[KnowledgeFileIdForm],
    user=Depends(get_verified_user),
):
    """
    Add multiple files to a knowledge base
    """
    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_write_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    # Get files content
    log.info(f"files/batch/add - {len(form_data)} files")
    files: List[FileModel] = []
    for form in form_data:
        file = Files.get_file_by_id(form.file_id)
        if not file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {form.file_id} not found",
            )
        files.append(file)

    # Process files
    try:
        result = process_files_batch(
            request=request,
            form_data=BatchProcessFilesForm(files=files, collection_name=id),
            user=user,
        )
    except Exception as e:
        log.error(
            f"add_files_to_knowledge_batch: Exception occurred: {e}", exc_info=True
        )
        diagnostic = classify_file_upload_error(e, user=user)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=build_file_upload_error_detail(diagnostic),
        )

    # Add successful files to knowledge base
    data = knowledge.data or {}
    existing_file_ids = data.get("file_ids", [])

    # Only add files that were successfully processed
    successful_file_ids = [r.file_id for r in result.results if r.status == "completed"]
    for file_id in successful_file_ids:
        if file_id not in existing_file_ids:
            existing_file_ids.append(file_id)

    data["file_ids"] = existing_file_ids
    knowledge = Knowledges.update_knowledge_data_by_id(id=id, data=data)

    # If there were any errors, include them in the response
    if result.errors:
        error_details = [f"{err.file_id}: {err.error}" for err in result.errors]
        return KnowledgeFilesResponse(
            **knowledge.model_dump(),
            files=Files.get_files_by_ids(existing_file_ids),
            warnings={
                "message": "Some files failed to process",
                "errors": error_details,
            },
        )

    return KnowledgeFilesResponse(
        **knowledge.model_dump(),
        files=Files.get_files_by_ids(existing_file_ids),
        warnings={"message": "知识库文件已强制转为检索模式。"},
    )


############################
# exportKnowledgeZip
############################


@router.get("/{id}/export")
async def export_knowledge_by_id(id: str, user=Depends(get_verified_user)):
    """Export a knowledge base and its files as a zip archive."""
    import io
    import json
    import zipfile
    from fastapi.responses import StreamingResponse as FastStreamingResponse

    knowledge = Knowledges.get_knowledge_by_id(id=id)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not can_read_resource(user, knowledge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    buf = io.BytesIO()
    file_ids = (knowledge.data or {}).get("file_ids", [])

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Write knowledge metadata
        meta = {
            "id": knowledge.id,
            "name": knowledge.name,
            "description": knowledge.description,
            "data": knowledge.data,
            "created_at": knowledge.created_at,
            "updated_at": knowledge.updated_at,
        }
        zf.writestr(
            "knowledge.json",
            json.dumps(meta, ensure_ascii=False, indent=2, default=str),
        )

        # Write each file
        for file_id in file_ids:
            file = Files.get_file_by_id(file_id)
            if not file:
                continue
            try:
                file_path = Storage.get_file(file.path)
                if file_path and hasattr(file_path, "read"):
                    zf.writestr(f"files/{file.filename}", file_path.read())
                elif isinstance(file_path, str):
                    with open(file_path, "rb") as f:
                        zf.writestr(f"files/{file.filename}", f.read())
            except Exception as e:
                log.warning(f"Failed to export file {file_id}: {e}")
                # Include file metadata even if content fails
                file_meta = {
                    "id": file.id,
                    "filename": file.filename,
                    "meta": file.meta,
                    "error": str(e),
                }
                zf.writestr(
                    f"files/{file.filename}.meta.json",
                    json.dumps(file_meta, ensure_ascii=False, indent=2, default=str),
                )

    buf.seek(0)
    safe_name = knowledge.name.replace(" ", "_").replace("/", "_")[:50]
    return FastStreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )
