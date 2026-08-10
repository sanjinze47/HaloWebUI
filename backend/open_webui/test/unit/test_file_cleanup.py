from types import SimpleNamespace

from open_webui.models.files import FileModel
from open_webui.utils import file_cleanup


def _file(file_id: str) -> FileModel:
    return FileModel(
        id=file_id,
        user_id="user-1",
        filename=f"{file_id}.txt",
        path=f"uploads/{file_id}.txt",
        data={},
        meta={"deletion_pending": True},
        created_at=1,
        updated_at=1,
    )


def test_file_dependency_cleanup_unlinks_every_knowledge_reference(monkeypatch):
    file = _file("shared-file")
    knowledge_items = [
        SimpleNamespace(id="kb-1", data={"file_ids": [file.id, "other"]}),
        SimpleNamespace(id="kb-2", data={"file_ids": [file.id]}),
        SimpleNamespace(id="kb-3", data={"file_ids": ["other"]}),
    ]
    vector_deletes = []
    knowledge_updates = []
    storage_deletes = []
    monkeypatch.setattr(
        file_cleanup.Knowledges,
        "get_knowledge_bases",
        lambda: knowledge_items,
    )
    monkeypatch.setattr(
        file_cleanup.Knowledges,
        "update_knowledge_data_by_id",
        lambda knowledge_id, data: knowledge_updates.append((knowledge_id, data))
        or knowledge_items[0],
    )
    monkeypatch.setattr(
        file_cleanup.VECTOR_DB_CLIENT,
        "delete",
        lambda **kwargs: vector_deletes.append(kwargs),
    )
    monkeypatch.setattr(
        file_cleanup.VECTOR_DB_CLIENT, "has_collection", lambda **_kwargs: True
    )
    monkeypatch.setattr(
        file_cleanup.VECTOR_DB_CLIENT,
        "delete_collection",
        lambda **kwargs: vector_deletes.append(kwargs),
    )
    monkeypatch.setattr(
        file_cleanup.Storage,
        "delete_file",
        lambda path: storage_deletes.append(path),
    )

    file_cleanup.cleanup_file_dependencies(file)

    assert knowledge_updates == [
        ("kb-1", {"file_ids": ["other"]}),
        ("kb-2", {"file_ids": []}),
    ]
    assert [item["collection_name"] for item in vector_deletes] == [
        "kb-1",
        "kb-2",
        f"file-{file.id}",
    ]
    assert storage_deletes == [file.path]
