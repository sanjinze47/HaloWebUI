import json
from typing import Any, Optional


GEMINI_COMPATIBILITY_MODES = {"strict", "auto"}


def resolve_gemini_compatibility_mode(
    api_config: Optional[dict], *, legacy_default: str = "auto"
) -> str:
    config = api_config if isinstance(api_config, dict) else {}
    mode = str(
        config.get("gemini_compatibility_mode") or legacy_default
    ).strip().lower()
    if mode not in GEMINI_COMPATIBILITY_MODES:
        allowed = ", ".join(sorted(GEMINI_COMPATIBILITY_MODES))
        raise ValueError(
            f"Invalid Gemini compatibility mode {mode!r}; expected one of: {allowed}."
        )
    return mode


def classify_unsupported_gemini_capability(
    status: int, body: Any
) -> Optional[str]:
    if status != 400:
        return None

    parsed = body
    if isinstance(body, str):
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = None

    violations: list[tuple[str, str]] = []
    error_message = ""
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            error_message = str(error.get("message") or "")
        details = error.get("details") if isinstance(error, dict) else None
        if isinstance(details, list):
            for detail in details:
                field_violations = (
                    detail.get("fieldViolations")
                    if isinstance(detail, dict)
                    else None
                )
                if isinstance(field_violations, list):
                    violations.extend(
                        (
                            str(item.get("field") or ""),
                            str(item.get("description") or ""),
                        )
                        for item in field_violations
                        if isinstance(item, dict)
                    )

    def _classify(text: str) -> Optional[str]:
        normalized = text.lower().replace("_", "")
        if any(
            name in normalized
            for name in ("functiondeclarations", "googlesearch", "toolconfig", "tools")
        ):
            return "tools"
        if any(
            name in normalized
            for name in ("thinkingconfig", "thinkingbudget", "includethoughts")
        ):
            return "thinking"
        if "responsemodalities" in normalized:
            return "response_modalities"
        return None

    if isinstance(body, str):
        message = body
    elif isinstance(parsed, dict):
        message = error_message or str(parsed.get("message") or "")
    else:
        message = str(body or "")

    lowered = message.lower()
    unsupported_terms = (
        "unsupported",
        "not supported",
        "unknown field",
        "unknown name",
        "invalid field",
        "unrecognized field",
    )

    for field, description in violations:
        violation_text = f"{description} {message}".lower()
        if not any(term in violation_text for term in unsupported_terms):
            continue
        capability = _classify(field)
        if capability:
            return capability

    if not any(term in lowered for term in unsupported_terms):
        return None
    return _classify(message)
