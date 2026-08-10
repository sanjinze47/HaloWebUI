from contextlib import contextmanager

import pytest

from open_webui.models.files import FileModel, Files
from open_webui.models import files as file_models


def _file(file_id: str, *, pending: bool) -> FileModel:
    return FileModel(
        id=file_id,
        user_id="user-1",
        filename=f"{file_id}.txt",
        path=f"uploads/{file_id}.txt",
        data={},
        meta={"deletion_pending": pending},
        created_at=1,
        updated_at=1,
    )


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _model):
        return _Query(self.rows)


def test_pending_deletions_are_hidden_from_normal_lists(monkeypatch):
    rows = [_file("visible", pending=False), _file("pending", pending=True)]

    @contextmanager
    def fake_get_db():
        yield _Db(rows)

    monkeypatch.setattr(file_models, "get_db", fake_get_db)

    assert [item.id for item in Files.get_files()] == ["visible"]
    assert [item.id for item in Files.get_files(include_pending=True)] == [
        "visible",
        "pending",
    ]


def test_failed_upload_record_delete_restores_pending_error(monkeypatch):
    pytest.importorskip("chromadb")
    from open_webui.routers import files as file_router

    file = _file("failed-upload", pending=False)
    metadata_updates = []
    monkeypatch.setattr(
        file_router.Files,
        "get_file_by_id",
        lambda *_args, **_kwargs: file,
    )
    monkeypatch.setattr(
        file_router.Files,
        "update_file_metadata_by_id",
        lambda _id, meta: metadata_updates.append(meta) or file,
    )
    monkeypatch.setattr(file_router, "cleanup_file_dependencies", lambda _file: None)
    monkeypatch.setattr(file_router.Files, "delete_file_by_id", lambda _id: False)

    file_router._cleanup_failed_uploaded_file(file.id, file.path)

    assert metadata_updates[-1]["deletion_pending"] is True
    assert "Failed to delete file record" in metadata_updates[-1][
        "deletion_last_error"
    ]


def test_failed_upload_does_not_clean_storage_before_tombstone(monkeypatch):
    pytest.importorskip("chromadb")
    from open_webui.routers import files as file_router

    file = _file("failed-upload", pending=False)
    cleanup_calls = []
    metadata_updates = []
    monkeypatch.setattr(
        file_router.Files,
        "get_file_by_id",
        lambda *_args, **_kwargs: file,
    )

    def update_metadata(_id, meta):
        metadata_updates.append(meta)
        return None

    monkeypatch.setattr(
        file_router.Files, "update_file_metadata_by_id", update_metadata
    )
    monkeypatch.setattr(
        file_router,
        "cleanup_file_dependencies",
        lambda _file: cleanup_calls.append(_file.id),
    )
    monkeypatch.setattr(
        file_router.Files,
        "delete_file_by_id",
        lambda _id: pytest.fail("record deletion must not run"),
    )

    file_router._cleanup_failed_uploaded_file(file.id, file.path)

    assert cleanup_calls == []
    assert metadata_updates[0]["deletion_pending"] is True
