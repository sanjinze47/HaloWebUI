from __future__ import annotations

from open_webui.models.files import FileModel, Files
from open_webui.models.knowledge import Knowledges
from open_webui.retrieval.vector.connector import VECTOR_DB_CLIENT
from open_webui.storage.provider import Storage


def cleanup_file_dependencies(file: FileModel) -> None:
    """Remove a file from every KB and storage location before its DB row."""

    for knowledge in Knowledges.get_knowledge_bases():
        data = dict(knowledge.data or {})
        file_ids = list(data.get("file_ids", []))
        if file.id not in file_ids:
            continue

        # The File tombstone remains in place if either operation fails, so a
        # retry can continue with the remaining knowledge bases.
        VECTOR_DB_CLIENT.delete(
            collection_name=knowledge.id,
            filter={"file_id": file.id},
        )
        file_ids = [file_id for file_id in file_ids if file_id != file.id]
        data["file_ids"] = file_ids
        if not Knowledges.update_knowledge_data_by_id(knowledge.id, data):
            raise RuntimeError(
                f"Failed to unlink file {file.id} from knowledge {knowledge.id}."
            )

    standalone_collection = f"file-{file.id}"
    if VECTOR_DB_CLIENT.has_collection(collection_name=standalone_collection):
        VECTOR_DB_CLIENT.delete_collection(collection_name=standalone_collection)

    if file.path:
        Storage.delete_file(file.path)


def retry_pending_file_cleanups() -> None:
    """Best-effort retry for upload/delete tombstones left by earlier failures."""

    for file in Files.get_files(include_pending=True):
        if not (file.meta or {}).get("deletion_pending"):
            continue
        try:
            cleanup_file_dependencies(file)
            if not Files.delete_file_by_id(file.id):
                raise RuntimeError(f"Failed to delete file record {file.id}.")
        except Exception as exc:
            Files.update_file_metadata_by_id(
                file.id,
                {
                    "deletion_pending": True,
                    "deletion_last_error": str(exc),
                },
            )
