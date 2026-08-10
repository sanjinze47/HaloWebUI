from types import SimpleNamespace

import pytest


pytest.importorskip("chromadb")

from open_webui.routers import knowledge as knowledge_router  # noqa: E402


def _knowledge(*, operation: str | None = None):
    meta = {}
    if operation:
        meta["vector_cleanup"] = {
            "operation": operation,
            "status": "pending",
            "attempts": 1,
        }
    return SimpleNamespace(
        id="kb-1",
        user_id="user-1",
        data={"file_ids": ["file-1"]},
        meta=meta,
    )


def test_vector_cleanup_marker_remains_until_metadata_operation(monkeypatch):
    current = _knowledge()
    deleted = []

    def update_meta(_id, meta):
        current.meta = meta
        return current

    monkeypatch.setattr(
        knowledge_router.Knowledges, "update_knowledge_meta_by_id", update_meta
    )
    monkeypatch.setattr(
        knowledge_router.Knowledges,
        "get_knowledge_by_id",
        lambda _id: current,
    )
    monkeypatch.setattr(
        knowledge_router.VECTOR_DB_CLIENT,
        "has_collection",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        knowledge_router.VECTOR_DB_CLIENT,
        "delete_collection",
        lambda **kwargs: deleted.append(kwargs["collection_name"]),
    )

    result = knowledge_router._delete_knowledge_vectors_or_mark_pending(
        current, "reset"
    )

    assert deleted == [current.id]
    assert result.meta["vector_cleanup"]["status"] == "pending"
    assert result.meta["vector_cleanup"]["operation"] == "reset"


def test_startup_retry_completes_pending_reset(monkeypatch):
    current = _knowledge(operation="reset")
    monkeypatch.setattr(
        knowledge_router.Knowledges,
        "get_knowledge_bases",
        lambda: [current],
    )
    monkeypatch.setattr(
        knowledge_router.VECTOR_DB_CLIENT,
        "has_collection",
        lambda **_kwargs: False,
    )

    def update_data(id, data):
        current.data = data
        return current

    def update_meta(_id, meta):
        current.meta = meta
        return current

    monkeypatch.setattr(
        knowledge_router.Knowledges, "update_knowledge_data_by_id", update_data
    )
    monkeypatch.setattr(
        knowledge_router.Knowledges, "update_knowledge_meta_by_id", update_meta
    )

    knowledge_router.retry_pending_knowledge_cleanups()

    assert current.data == {"file_ids": []}
    assert "vector_cleanup" not in current.meta


def test_startup_retry_keeps_pending_marker_when_reset_metadata_fails(monkeypatch):
    current = _knowledge(operation="reset")
    monkeypatch.setattr(
        knowledge_router.Knowledges,
        "get_knowledge_bases",
        lambda: [current],
    )
    monkeypatch.setattr(
        knowledge_router.VECTOR_DB_CLIENT,
        "has_collection",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        knowledge_router.Knowledges,
        "update_knowledge_data_by_id",
        lambda *_args, **_kwargs: None,
    )

    def update_meta(_id, meta):
        current.meta = meta
        return current

    monkeypatch.setattr(
        knowledge_router.Knowledges, "update_knowledge_meta_by_id", update_meta
    )

    knowledge_router.retry_pending_knowledge_cleanups()

    cleanup = current.meta["vector_cleanup"]
    assert cleanup["status"] == "pending"
    assert cleanup["attempts"] == 2
    assert "Unable to reset knowledge metadata" in cleanup["last_error"]


def test_startup_retry_keeps_identity_when_model_reference_cleanup_fails(monkeypatch):
    current = _knowledge(operation="delete")
    deleted = []
    monkeypatch.setattr(
        knowledge_router.Knowledges,
        "get_knowledge_bases",
        lambda: [current],
    )
    monkeypatch.setattr(
        knowledge_router.VECTOR_DB_CLIENT,
        "has_collection",
        lambda **_kwargs: False,
    )

    def fail_model_cleanup(_knowledge_id):
        raise RuntimeError("model update failed")

    monkeypatch.setattr(
        knowledge_router,
        "_remove_knowledge_model_references",
        fail_model_cleanup,
    )
    monkeypatch.setattr(
        knowledge_router.Knowledges,
        "delete_knowledge_by_id",
        lambda knowledge_id: deleted.append(knowledge_id) or True,
    )

    def update_meta(_id, meta):
        current.meta = meta
        return current

    monkeypatch.setattr(
        knowledge_router.Knowledges, "update_knowledge_meta_by_id", update_meta
    )

    knowledge_router.retry_pending_knowledge_cleanups()

    assert deleted == []
    cleanup = current.meta["vector_cleanup"]
    assert cleanup["attempts"] == 2
    assert "model update failed" in cleanup["last_error"]
