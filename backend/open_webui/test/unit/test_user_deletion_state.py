import sys
from types import ModuleType, SimpleNamespace

from open_webui.models import users as user_models
from open_webui.models.users import UsersTable


_LAZY_TABLES = {
    "files": "Files",
    "prompts": "Prompts",
    "tools": "Tools",
    "functions": "Functions",
    "knowledge": "Knowledges",
    "skills": "Skills",
    "memories": "Memories",
    "messages": "Messages",
    "notes": "Notes",
    "channels": "Channels",
    "folders": "Folders",
    "tags": "Tags",
}


def _install_cleanup_tables(monkeypatch):
    tables = {
        "groups": user_models.Groups,
        "chats": user_models.Chats,
    }
    for module_name, table_name in _LAZY_TABLES.items():
        table = SimpleNamespace()
        module = ModuleType(f"open_webui.models.{module_name}")
        setattr(module, table_name, table)
        monkeypatch.setitem(sys.modules, module.__name__, module)
        tables[module_name] = table

    operations = {
        "groups": "remove_user_from_all_groups",
        "chats": "delete_chats_by_user_id",
        "files": "delete_files_by_user_id",
        "prompts": "delete_prompts_by_user_id",
        "tools": "delete_tools_by_user_id",
        "functions": "delete_functions_by_user_id",
        "knowledge": "delete_knowledge_by_user_id",
        "skills": "delete_skills_by_user_id",
        "memories": "delete_memories_by_user_id",
        "messages": "delete_messages_by_user_id",
        "notes": "delete_notes_by_user_id",
        "channels": "delete_channels_by_user_id",
        "folders": "delete_folders_by_user_id",
        "tags": "delete_tags_by_user_id",
    }
    for resource_type, method_name in operations.items():
        monkeypatch.setattr(
            tables[resource_type], method_name, lambda _user_id: True, raising=False
        )
    return tables


def test_user_resource_cleanup_reports_false_and_exceptions(monkeypatch):
    tables = _install_cleanup_tables(monkeypatch)
    monkeypatch.setattr(tables["files"], "delete_files_by_user_id", lambda _id: False)

    def fail_knowledge(_user_id):
        raise RuntimeError("vector metadata unavailable")

    monkeypatch.setattr(
        tables["knowledge"], "delete_knowledge_by_user_id", fail_knowledge
    )

    failures = UsersTable().cleanup_user_resources_by_id("user-1")

    assert failures == [
        {
            "type": "files",
            "id": "user-1",
            "error": "operation returned false",
        },
        {
            "type": "knowledge",
            "id": "user-1",
            "error": "vector metadata unavailable",
        },
    ]


def test_user_identity_record_is_kept_when_resource_cleanup_fails(monkeypatch):
    table = UsersTable()
    record_deletes = []
    monkeypatch.setattr(
        table,
        "cleanup_user_resources_by_id",
        lambda _id: [{"type": "files", "id": "user-1", "error": "failed"}],
    )
    monkeypatch.setattr(
        table,
        "delete_user_record_by_id",
        lambda user_id: record_deletes.append(user_id) or True,
    )

    assert table.delete_user_by_id("user-1") is False
    assert record_deletes == []
