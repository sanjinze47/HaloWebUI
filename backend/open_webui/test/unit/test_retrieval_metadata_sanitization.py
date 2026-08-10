import pathlib
import sys
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document


pytest.importorskip("chromadb")

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.routers import retrieval as retrieval_module  # noqa: E402
from open_webui.retrieval.vector.dbs import chroma as chroma_module  # noqa: E402
from open_webui.retrieval.vector.dbs.chroma import ChromaClient  # noqa: E402


class _Collection:
    def __init__(self):
        self.add_batch = None

    def add(self, *batch):
        self.add_batch = batch


class _ChromaApi:
    def __init__(self, collection):
        self.collection = collection

    def get_or_create_collection(self, name, metadata):
        return self.collection


def _build_request():
    config = SimpleNamespace(
        ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER=False,
        TEXT_SPLITTER="character",
        CHUNK_SIZE=200,
        CHUNK_OVERLAP=0,
        CHUNK_MIN_SIZE=0,
        RAG_EMBEDDING_ENGINE="test-engine",
        RAG_EMBEDDING_MODEL="test-model",
    )
    state = SimpleNamespace(
        config=config,
        EMBEDDING_FUNCTION=lambda texts, prefix, user=None: [
            [0.1, 0.2] for _ in texts
        ],
    )
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_save_docs_to_vector_db_with_none_metadata_uses_sanitized_chroma_insert(
    monkeypatch,
):
    collection = _Collection()
    chroma_client = ChromaClient.__new__(ChromaClient)
    chroma_client.client = _ChromaApi(collection)

    monkeypatch.setattr(chroma_client, "query", lambda collection_name, filter: None)
    monkeypatch.setattr(chroma_client, "has_collection", lambda collection_name: False)
    monkeypatch.setattr(retrieval_module, "VECTOR_DB_CLIENT", chroma_client)
    monkeypatch.setattr(
        chroma_module,
        "create_batches",
        lambda **kwargs: [
            (
                kwargs["ids"],
                kwargs["embeddings"],
                kwargs["metadatas"],
                kwargs["documents"],
            )
        ],
    )

    result = retrieval_module.save_docs_to_vector_db(
        _build_request(),
        docs=[
            Document(
                page_content="hello world",
                metadata={
                    "page": 0,
                    "title": "Intro",
                    "headings": ["Section 1"],
                    "snippet": None,
                },
            )
        ],
        collection_name="kb-demo",
        metadata={
            "file_id": "file-1",
            "name": "report.pdf",
            "hash": "hash-1",
        },
        user=SimpleNamespace(id="user-1"),
    )

    assert result is True
    assert collection.add_batch is not None
    assert collection.add_batch[2] == [
        {
            "page": 0,
            "title": "Intro",
            "headings": "['Section 1']",
            "start_index": 0,
            "file_id": "file-1",
            "name": "report.pdf",
            "hash": "hash-1",
            "embedding_config": '{"engine": "test-engine", "model": "test-model"}',
        }
    ]


def test_save_docs_rolls_back_vectors_when_metadata_commit_fails(monkeypatch):
    old_result = SimpleNamespace(
        ids=[["old-1"]],
        documents=[["old content"]],
        metadatas=[[{"file_id": "file-1", "hash": "old-hash"}]],
    )

    class _VectorClient:
        def __init__(self):
            self.deleted = []
            self.inserted = []

        def query(self, collection_name, filter):
            return old_result

        def has_collection(self, collection_name):
            return True

        def delete(self, collection_name, ids=None, filter=None):
            self.deleted.append(list(ids or []))

        def insert(self, collection_name, items):
            self.inserted.append(items)

    vector_client = _VectorClient()
    monkeypatch.setattr(retrieval_module, "VECTOR_DB_CLIENT", vector_client)

    def fail_metadata_commit():
        raise RuntimeError("metadata commit failed")

    with pytest.raises(RuntimeError, match="metadata commit failed"):
        retrieval_module.save_docs_to_vector_db(
            _build_request(),
            docs=[Document(page_content="new content", metadata={})],
            collection_name="kb-demo",
            metadata={
                "file_id": "file-1",
                "name": "report.pdf",
                "hash": "new-hash",
            },
            overwrite=True,
            split=False,
            after_insert=fail_metadata_commit,
        )

    assert vector_client.deleted[0] == ["old-1"]
    assert vector_client.deleted[1] == [vector_client.inserted[0][0]["id"]]
    assert vector_client.deleted[2] == ["old-1"]
    assert vector_client.inserted[-1] == [
        {
            "id": "old-1",
            "text": "old content",
            "vector": [0.1, 0.2],
            "metadata": {"file_id": "file-1", "hash": "old-hash"},
        }
    ]


def test_restore_vector_snapshot_replaces_partial_reindex_with_original_vectors(
    monkeypatch,
):
    restored = []
    deleted = []
    snapshot = SimpleNamespace(
        ids=[["old-1"]],
        documents=[["old content"]],
        metadatas=[[{"file_id": "file-1"}]],
        embeddings=[[[0.7, 0.8]]],
    )
    vector_client = SimpleNamespace(
        has_collection=lambda **_kwargs: True,
        delete_collection=lambda **kwargs: deleted.append(kwargs["collection_name"]),
        insert=lambda **kwargs: restored.extend(kwargs["items"]),
    )
    monkeypatch.setattr(retrieval_module, "VECTOR_DB_CLIENT", vector_client)

    retrieval_module.restore_vector_snapshot(
        _build_request(), "kb-demo", snapshot, user=SimpleNamespace(id="user-1")
    )

    assert deleted == ["kb-demo"]
    assert restored == [
        {
            "id": "old-1",
            "text": "old content",
            "vector": [0.7, 0.8],
            "metadata": {"file_id": "file-1"},
        }
    ]
