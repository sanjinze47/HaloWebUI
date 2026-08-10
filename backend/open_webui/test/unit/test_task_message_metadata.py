from open_webui import tasks as task_store


def test_chat_tasks_include_response_message_mapping():
    task_store.chat_tasks["chat-1"] = ["task-1", "task-2"]
    task_store.task_metadata["task-1"] = {
        "chat_id": "chat-1",
        "blocks_completion": True,
    }
    task_store.task_metadata["task-2"] = {
        "chat_id": "chat-1",
        "blocks_completion": False,
    }

    try:
        assert task_store.set_task_message_id("task-1", "message-1") is True
        assert task_store.set_task_message_id("task-2", "message-2") is True
        assert task_store.list_tasks_by_chat_id(
            "chat-1", blocks_completion_only=True
        ) == [{"task_id": "task-1", "message_id": "message-1"}]
    finally:
        task_store.chat_tasks.pop("chat-1", None)
        task_store.task_metadata.pop("task-1", None)
        task_store.task_metadata.pop("task-2", None)
