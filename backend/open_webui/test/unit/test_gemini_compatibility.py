import pytest

from open_webui.utils.gemini_compatibility import (
    classify_unsupported_gemini_capability,
    resolve_gemini_compatibility_mode,
)


def test_missing_gemini_mode_keeps_legacy_auto_behavior():
    assert resolve_gemini_compatibility_mode({}) == "auto"


def test_invalid_gemini_mode_is_rejected():
    with pytest.raises(ValueError, match="Invalid Gemini compatibility mode"):
        resolve_gemini_compatibility_mode({"gemini_compatibility_mode": "loose"})


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("tools[0].functionDeclarations", "tools"),
        ("generationConfig.thinkingConfig.thinkingBudget", "thinking"),
        ("generationConfig.responseModalities", "response_modalities"),
    ],
)
def test_structured_field_violations_are_classified(field, expected):
    body = {
        "error": {
            "details": [
                {
                    "fieldViolations": [
                        {"field": field, "description": "Unknown field"}
                    ]
                }
            ],
        }
    }
    assert classify_unsupported_gemini_capability(400, body) == expected


def test_structured_value_validation_error_is_not_treated_as_unsupported():
    body = {
        "error": {
            "message": "Invalid request payload",
            "details": [
                {
                    "fieldViolations": [
                        {
                            "field": "generationConfig.thinkingConfig.thinkingBudget",
                            "description": "Value must be less than or equal to 8192",
                        }
                    ]
                }
            ],
        }
    }

    assert classify_unsupported_gemini_capability(400, body) is None


def test_unrelated_or_non_400_errors_do_not_trigger_compatibility_retry():
    assert (
        classify_unsupported_gemini_capability(
            400, '{"error":{"message":"Invalid request payload"}}'
        )
        is None
    )
    assert (
        classify_unsupported_gemini_capability(
            500, '{"error":{"message":"tools are unsupported"}}'
        )
        is None
    )
