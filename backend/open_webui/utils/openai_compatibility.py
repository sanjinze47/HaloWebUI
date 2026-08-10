from typing import Any, Optional


CHAT_COMPLETION_TOKEN_PARAMETERS = {
    "auto",
    "max_tokens",
    "max_completion_tokens",
}


def resolve_chat_completion_token_parameter(api_config: Optional[dict]) -> str:
    config = api_config if isinstance(api_config, dict) else {}
    mode = str(config.get("chat_completion_token_parameter") or "auto").strip().lower()
    if mode not in CHAT_COMPLETION_TOKEN_PARAMETERS:
        allowed = ", ".join(sorted(CHAT_COMPLETION_TOKEN_PARAMETERS))
        raise ValueError(
            f"Invalid chat completion token parameter {mode!r}; expected one of: {allowed}."
        )
    return mode


def apply_chat_completion_token_parameter(
    payload: dict[str, Any],
    *,
    api_config: Optional[dict],
    url: str,
    is_o1_o3: bool = False,
) -> dict[str, Any]:
    mode = resolve_chat_completion_token_parameter(api_config)
    if mode == "auto":
        if is_o1_o3:
            selected = "max_completion_tokens"
        elif "api.openai.com" not in url:
            selected = "max_tokens"
        else:
            if "max_tokens" in payload and "max_completion_tokens" in payload:
                payload.pop("max_tokens", None)
            return payload
    else:
        selected = mode

    other = (
        "max_tokens" if selected == "max_completion_tokens" else "max_completion_tokens"
    )
    if selected not in payload and other in payload:
        payload[selected] = payload[other]
    payload.pop(other, None)
    return payload
