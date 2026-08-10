import pytest

from open_webui.utils.openai_compatibility import (
    apply_chat_completion_token_parameter,
    resolve_chat_completion_token_parameter,
)


@pytest.mark.parametrize(
    ("mode", "expected", "removed"),
    [
        ("max_tokens", "max_tokens", "max_completion_tokens"),
        ("max_completion_tokens", "max_completion_tokens", "max_tokens"),
    ],
)
def test_explicit_token_parameter_wins(mode, expected, removed):
    payload = {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 10,
        "max_completion_tokens": 20,
    }

    result = apply_chat_completion_token_parameter(
        payload,
        api_config={"chat_completion_token_parameter": mode},
        url="https://custom.example/v1",
    )

    assert result[expected] == (10 if expected == "max_tokens" else 20)
    assert removed not in result


def test_auto_preserves_official_legacy_payload():
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
    }
    result = apply_chat_completion_token_parameter(
        payload, api_config={}, url="https://api.openai.com/v1"
    )
    assert result["max_tokens"] == 5
    assert "max_completion_tokens" not in result


def test_auto_preserves_custom_gateway_legacy_rewrite():
    payload = {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "hi"}],
        "max_completion_tokens": 5,
    }
    result = apply_chat_completion_token_parameter(
        payload, api_config={}, url="https://custom.example/v1"
    )
    assert result["max_tokens"] == 5
    assert "max_completion_tokens" not in result


def test_o1_uses_completion_tokens_even_with_auto():
    payload = {
        "model": "o1-mini",
        "messages": [{"role": "system", "content": "hi"}],
        "max_tokens": 5,
    }
    result = apply_chat_completion_token_parameter(
        payload, api_config={}, url="https://custom.example/v1", is_o1_o3=True
    )
    assert result["max_completion_tokens"] == 5
    assert "max_tokens" not in result


def test_invalid_token_parameter_is_rejected():
    with pytest.raises(ValueError, match="Invalid chat completion token parameter"):
        resolve_chat_completion_token_parameter(
            {"chat_completion_token_parameter": "guess"}
        )


def test_explicit_token_parameter_is_reasserted_after_extra_fields_are_added():
    payload = apply_chat_completion_token_parameter(
        {"max_tokens": 10},
        api_config={"chat_completion_token_parameter": "max_tokens"},
        url="https://custom.example/v1",
    )
    payload["max_completion_tokens"] = 20

    result = apply_chat_completion_token_parameter(
        payload,
        api_config={"chat_completion_token_parameter": "max_tokens"},
        url="https://custom.example/v1",
    )

    assert result["max_tokens"] == 10
    assert "max_completion_tokens" not in result
