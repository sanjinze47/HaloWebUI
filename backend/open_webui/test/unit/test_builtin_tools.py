import pathlib
import sys
from types import SimpleNamespace


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.utils import builtin_tools  # noqa: E402


TOOL_CONFIG_KEYS = (
    "ENABLE_WEB_SEARCH_TOOL",
    "ENABLE_LIST_KNOWLEDGE_BASES",
    "ENABLE_SEARCH_KNOWLEDGE_BASES",
    "ENABLE_QUERY_KNOWLEDGE_FILES",
    "ENABLE_VIEW_KNOWLEDGE_FILE",
    "ENABLE_IMAGE_GENERATION_TOOL",
    "ENABLE_MEMORY_TOOLS",
    "ENABLE_CHAT_HISTORY_TOOLS",
    "ENABLE_TIME_TOOLS",
)

KNOWLEDGE_TOOL_NAMES = {
    "list_knowledge_bases",
    "search_knowledge_bases",
    "query_knowledge_bases",
    "search_knowledge_files",
    "view_knowledge_file",
}


def _request():
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                config=SimpleNamespace(
                    ENABLE_WEB_SEARCH=True,
                    ENABLE_IMAGE_GENERATION=True,
                    ENABLE_CHANNELS=False,
                    ENABLE_TERMINAL=False,
                )
            )
        )
    )


def _user():
    return SimpleNamespace(
        id="user-1", role="admin", email="user@example.com", name="User"
    )


def test_model_builtin_tool_config_overrides_global_defaults(monkeypatch):
    monkeypatch.setattr(
        builtin_tools,
        "get_user_native_tools_config",
        lambda *_args: {key: True for key in TOOL_CONFIG_KEYS},
    )

    tools = builtin_tools.get_builtin_tools(
        _request(),
        _user(),
        {
            "features": {"image_generation": True, "memory": True},
            "model": {
                "info": {
                    "meta": {
                        "builtin_tool_config": {key: False for key in TOOL_CONFIG_KEYS}
                    }
                }
            },
        },
    )

    assert not {"search_web", "generate_image"} & tools.keys()
    assert not KNOWLEDGE_TOOL_NAMES & tools.keys()
    assert not {"add_memory", "search_chats", "get_current_time"} & tools.keys()


def test_model_builtin_tool_config_enables_overrides_from_model_info(monkeypatch):
    monkeypatch.setattr(
        builtin_tools,
        "get_user_native_tools_config",
        lambda *_args: {key: False for key in TOOL_CONFIG_KEYS},
    )

    tools = builtin_tools.get_builtin_tools(
        _request(),
        _user(),
        {
            "features": {"image_generation": True, "memory": True},
            "model": {
                "info": {
                    "meta": {
                        "builtin_tool_config": {key: True for key in TOOL_CONFIG_KEYS}
                    }
                }
            },
        },
    )

    assert {"search_web", "generate_image"}.issubset(tools)
    assert KNOWLEDGE_TOOL_NAMES.issubset(tools)
    assert {"add_memory", "search_chats", "get_current_time"}.issubset(tools)
