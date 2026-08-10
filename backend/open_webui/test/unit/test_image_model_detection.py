import pathlib
import sys

import pytest

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.routers.images import (  # noqa: E402
    _classify_gemini_image_model,
    _classify_grok_image_model,
    _classify_openai_image_model,
    _extract_generated_images_from_openai_response,
    _should_parse_openai_image_response_as_stream,
    load_b64_image_data,
    _parse_natural_image_size,
    _validate_gpt_image_2_size,
)
from open_webui.routers.openai import (  # noqa: E402
    resolve_openai_image_edit_compatibility,
)


def test_openai_image_edit_compatibility_defaults_and_legacy_name():
    assert resolve_openai_image_edit_compatibility({}) == "standard"
    assert (
        resolve_openai_image_edit_compatibility({"remark": "Internal grok2api"})
        == "grok2api"
    )
    assert (
        resolve_openai_image_edit_compatibility(
            {
                "remark": "Internal grok2api",
                "image_edit_compatibility": "standard",
            }
        )
        == "standard"
    )


def test_openai_image_edit_compatibility_rejects_invalid_mode():
    with pytest.raises(ValueError, match="Invalid image edit compatibility mode"):
        resolve_openai_image_edit_compatibility({"image_edit_compatibility": "guess"})


def test_openai_dedicated_image_model_keeps_generations_default_for_unannotated_relays():
    classified = _classify_openai_image_model(
        {
            "id": "openai/gpt-image-1",
            "name": "OpenAI GPT Image 1",
            "architecture": {"output_modalities": ["text", "image"]},
        },
        base_url="https://openrouter.ai/api/v1",
        api_config={},
        source={"effective_source": "personal"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["text_output_supported"] is False
    assert classified["detection_method"] == "metadata"
    assert classified["supported_image_routes"] == ["generations", "chat", "edits"]
    assert classified["default_image_route"] == "generations"


def test_gpt_image_2_exposes_safe_custom_size_contract_without_api_key():
    classified = _classify_openai_image_model(
        {"id": "gpt-image-2", "name": "GPT Image 2"},
        base_url="https://relay.example/v1",
        api_config={"api_key": "must-not-leak"},
        source={"effective_source": "shared", "provider": "openai", "key": "secret"},
    )

    assert classified is not None
    assert classified["supports_custom_size"] is True
    assert "2048x1152" in classified["size_constraints"]["presets"]
    assert "key" not in classified
    assert "api_key" not in classified
    assert "key" not in classified["model_ref"]


def test_gpt_image_2_accepts_unicode_safe_natural_language_size_forms():
    assert _parse_natural_image_size("2048x1152") == "2048x1152"
    assert _parse_natural_image_size("\u5bbd 2048 \u9ad8 1152") == "2048x1152"
    assert _parse_natural_image_size("16:9 2K") == "2048x1152"
    assert _parse_natural_image_size("\u6b63\u65b9\u5f62 2048") == "2048x2048"


def test_gpt_image_2_size_validation_rejects_invalid_dimensions():
    assert _validate_gpt_image_2_size("2048x1152") == "2048x1152"
    assert _validate_gpt_image_2_size("3840x2160") == "3840x2160"
    for value in ("1000x1000", "4096x2160", "16x16", "3840x1024"):
        try:
            _validate_gpt_image_2_size(value)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 400
        else:
            raise AssertionError(f"expected 400 for {value}")


def test_shared_model_selection_id_keeps_credentials_server_side(monkeypatch):
    owner = type("Owner", (), {"id": "owner-1", "role": "admin"})()
    viewer = type("Viewer", (), {"id": "viewer-1", "role": "user"})()
    request = type("Request", (), {"state": type("State", (), {})()})()
    model = type("Model", (), {"user_id": owner.id, "base_model_id": None})()

    monkeypatch.setattr(
        "open_webui.routers.images.Models.get_model_by_id",
        lambda _model_id: model,
    )
    monkeypatch.setattr(
        "open_webui.routers.images.Users.get_user_by_id",
        lambda _user_id: owner,
    )
    monkeypatch.setattr(
        "open_webui.utils.user_connections.maybe_migrate_user_connections",
        lambda _request, user: user,
    )

    # The helper must select the owner's connection context without copying any
    # credential into a response object.
    from open_webui.routers import images as images_router

    images_router._apply_image_model_owner_context(
        request, viewer, "shared-model", {"owner_id": owner.id}
    )
    assert request.state.connection_user is owner


def test_openai_output_image_chat_model_uses_chat_image_mode_for_relays():
    classified = _classify_openai_image_model(
        {
            "id": "relay-image-preview",
            "name": "Relay Image Preview",
            "architecture": {"output_modalities": ["text", "image"]},
        },
        base_url="https://openrouter.ai/api/v1",
        api_config={},
        source={"effective_source": "personal"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_chat_image"
    assert classified["detection_method"] == "metadata"
    assert classified["default_image_route"] == "chat"


def test_openai_chat_completions_endpoint_prefers_chat_image_route():
    classified = _classify_openai_image_model(
        {
            "id": "gemini-3.1-flash-image-preview",
            "name": "gemini-3.1-flash-image-preview",
            "description": "High quality image generation and conversational editing.",
            "endpoints": ["/v1/chat/completions"],
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_chat_image"
    assert classified["supported_image_routes"] == ["chat"]
    assert classified["default_image_route"] == "chat"


def test_openai_chat_completions_endpoint_alone_does_not_make_image_model():
    classified = _classify_openai_image_model(
        {
            "id": "gpt-4o-mini",
            "name": "gpt-4o-mini",
            "endpoints": ["/v1/chat/completions"],
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is None


def test_openai_grok_imagine_video_is_not_detected_as_image_model():
    classified = _classify_openai_image_model(
        {
            "id": "grok-imagine-video",
            "name": "Grok Imagine Video",
            "description": "Text to video generation model.",
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is None


def test_openai_official_gpt_image_family_prefers_images_endpoint_mode():
    classified = _classify_openai_image_model(
        {
            "id": "gpt-image-1",
            "name": "GPT Image 1",
        },
        base_url="https://api.openai.com/v1",
        api_config={},
        source={"effective_source": "shared"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["supported_image_routes"] == ["generations", "edits"]
    assert classified["default_image_route"] == "generations"
    assert classified["supports_background"] is True


def test_openai_compat_gpt_image_without_endpoint_metadata_defaults_to_generations():
    classified = _classify_openai_image_model(
        {
            "id": "plus/gpt-image-2",
            "name": "plus/gpt-image-2",
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["supported_image_routes"] == ["generations", "chat", "edits"]
    assert classified["default_image_route"] == "generations"
    assert classified["reference_image_default_route"] == "edits"


def test_openai_compat_computetoken_gpt_image_2_defaults_to_generations():
    classified = _classify_openai_image_model(
        {
            "id": "gpt-image-2",
            "name": "gpt-image-2 | computer",
        },
        base_url="https://computetoken.ai/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["supported_image_routes"] == ["generations", "chat", "edits"]
    assert classified["default_image_route"] == "generations"
    assert classified["reference_image_default_route"] == "edits"


def test_openai_compat_gpt_image_with_explicit_generations_endpoint_keeps_generations_default():
    classified = _classify_openai_image_model(
        {
            "id": "plus/gpt-image-2",
            "name": "plus/gpt-image-2",
            "endpoints": ["/v1/images/generations"],
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["supported_image_routes"] == ["generations"]
    assert classified["default_image_route"] == "generations"
    assert classified["reference_image_default_route"] == ""


def test_openai_compat_gpt_image_with_nested_metadata_endpoint_keeps_generations_default():
    classified = _classify_openai_image_model(
        {
            "id": "plus/gpt-image-2",
            "name": "plus/gpt-image-2",
            "metadata": {"endpoints": ["/v1/images/generations"]},
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["supported_image_routes"] == ["generations"]
    assert classified["default_image_route"] == "generations"
    assert classified["reference_image_default_route"] == ""


def test_openai_compat_xai_named_model_stays_on_openai_image_route():
    classified = _classify_openai_image_model(
        {
            "id": "grok-imagine-image",
            "name": "Grok Imagine Image",
        },
        base_url="https://api.x.ai/v1",
        api_config={},
        source={"effective_source": "shared", "provider": "openai"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["supported_image_routes"] == ["generations"]
    assert classified["default_image_route"] == "generations"
    assert classified["reference_image_default_route"] == ""
    assert classified["supports_resolution"] is False


def test_openai_compat_grok_quality_model_offers_json_edit_route():
    classified = _classify_openai_image_model(
        {
            "id": "grok-imagine-image-quality",
            "name": "Grok Imagine Image Quality",
            "endpoints": ["/v1/images/generations"],
        },
        base_url="https://relay.example/v1",
        api_config={"image_edit_compatibility": "grok2api"},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["supported_image_routes"] == ["generations", "edits"]
    assert classified["default_image_route"] == "generations"
    assert classified["reference_image_default_route"] == "edits"


def test_openai_compat_grok_lite_model_does_not_offer_edit_route():
    classified = _classify_openai_image_model(
        {
            "id": "grok-imagine-image-lite",
            "name": "Grok Imagine Image Lite",
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["supported_image_routes"] == ["generations"]
    assert classified["default_image_route"] == "generations"


def test_openai_video_endpoint_only_model_is_not_detected_as_image_model():
    classified = _classify_openai_image_model(
        {
            "id": "grok-imagine-image",
            "name": "Grok Imagine Image",
            "endpoints": ["/v1/videos/generations"],
            "description": "Text to video generation model.",
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is None


def test_openai_model_with_image_and_video_endpoints_keeps_image_route():
    classified = _classify_openai_image_model(
        {
            "id": "media-image-video",
            "name": "Media Image Video",
            "endpoints": ["/v1/images/generations", "/v1/videos/generations"],
            "description": "Supports image generation and video generation.",
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["supported_image_routes"] == ["generations"]
    assert classified["default_image_route"] == "generations"


def test_openai_edit_only_endpoint_does_not_gain_generation_route():
    classified = _classify_openai_image_model(
        {
            "id": "gpt-image-edit-only",
            "name": "GPT Image Edit Only",
            "endpoints": ["/v1/images/edits"],
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["supported_image_routes"] == ["edits"]
    assert classified["default_image_route"] == ""


def test_openai_supported_endpoint_types_detect_image_and_responses_routes():
    classified = _classify_openai_image_model(
        {
            "id": "relay-image-preview",
            "name": "Relay Image Preview",
            "supported_endpoint_types": ["openai-response", "image-generation"],
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["supported_image_routes"] == ["generations", "responses"]
    assert classified["default_image_route"] == "generations"


def test_openai_bare_responses_endpoint_prefers_responses_route():
    classified = _classify_openai_image_model(
        {
            "id": "relay-image-preview",
            "name": "Relay Image Preview",
            "endpoints": ["responses"],
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_chat_image"
    assert classified["supported_image_routes"] == ["responses"]
    assert classified["default_image_route"] == "responses"


def test_openai_seedream_description_is_detected_as_image_model():
    classified = _classify_openai_image_model(
        {
            "id": "doubao-seedream-5.0-lite",
            "name": "Doubao Seedream 5.0 Lite",
            "description": "Doubao-Seedream-5.0-lite is ByteDance's latest image generation model.",
        },
        base_url="https://api.example.com/v1",
        api_config={},
        source={"effective_source": "shared"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"


def test_openai_flux_name_is_detected_as_dedicated_image_model():
    classified = _classify_openai_image_model(
        {
            "id": "black-forest-labs/flux-kontext-pro",
            "name": "FLUX Kontext Pro",
        },
        base_url="https://api.example.com/v1",
        api_config={},
        source={"effective_source": "shared"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"


def test_volcengine_seedream_prefers_images_endpoint_mode():
    classified = _classify_openai_image_model(
        {
            "id": "doubao-seedream-4-5-251128",
            "name": "Doubao Seedream 4.5",
        },
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_config={},
        source={"effective_source": "personal"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["detection_method"] == "heuristic"


def test_volcengine_seededit_prefers_images_endpoint_mode():
    classified = _classify_openai_image_model(
        {
            "id": "doubao-seededit-3-0-i2i-250628",
            "name": "Doubao SeedEdit 3.0",
        },
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_config={},
        source={"effective_source": "personal"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["detection_method"] == "heuristic"


def test_non_image_model_is_filtered_out():
    classified = _classify_openai_image_model(
        {
            "id": "text-embedding-3-small",
            "name": "text-embedding-3-small",
        },
        base_url="https://api.openai.com/v1",
        api_config={},
        source={"effective_source": "shared"},
    )

    assert classified is None


def test_gemini_predict_imagen_model_is_detected():
    classified = _classify_gemini_image_model(
        {
            "id": "imagen-3.0-generate-002",
            "displayName": "imagen-3.0-generate-002",
            "supportedGenerationMethods": ["predict"],
        },
        source={"effective_source": "shared"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "gemini_predict"


def test_gemini_generate_content_image_preview_is_detected():
    classified = _classify_gemini_image_model(
        {
            "id": "gemini-2.5-flash-image-preview",
            "displayName": "gemini-2.5-flash-image-preview",
            "supportedGenerationMethods": ["generateContent"],
        },
        source={"effective_source": "personal"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "gemini_generate_content_image"


def test_gemini_image_model_without_preview_suffix_is_detected():
    classified = _classify_gemini_image_model(
        {
            "id": "gemini-3.0-pro-image-4k",
            "displayName": "gemini-3.0-pro-image-4k",
            "supportedGenerationMethods": ["generateContent"],
        },
        source={"effective_source": "personal"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "gemini_generate_content_image"
    assert classified["supports_image_size"] is True


def test_gemini_image_understanding_model_is_not_detected_as_generation():
    classified = _classify_gemini_image_model(
        {
            "id": "gemini-image-understanding",
            "displayName": "gemini-image-understanding",
            "supportedGenerationMethods": ["generateContent"],
        },
        source={"effective_source": "personal"},
    )

    assert classified is None


def test_openai_compatible_gemini_image_model_without_preview_suffix_is_detected():
    classified = _classify_openai_image_model(
        {
            "id": "google/gemini-2.5-flash-image",
            "name": "google/gemini-2.5-flash-image",
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={"effective_source": "personal", "provider": "openai"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_chat_image"


def test_openai_compatible_gemini_images_endpoint_does_not_invent_chat_route():
    classified = _classify_openai_image_model(
        {
            "id": "gemini-3.1-flash-image-preview",
            "name": "gemini-3.1-flash-image-preview",
            "endpoints": ["/v1/images/generations"],
        },
        base_url="https://relay.example/v1",
        api_config={},
        source={
            "base_url": "https://relay.example/v1",
            "effective_source": "personal",
            "provider": "openai",
        },
    )

    assert classified is not None
    assert classified["generation_mode"] == "openai_images"
    assert classified["supported_image_routes"] == ["generations"]
    assert classified["default_image_route"] == "generations"


def test_grok_image_model_is_detected():
    classified = _classify_grok_image_model(
        {
            "id": "grok-imagine-image",
            "name": "Grok Imagine Image",
        },
        source={"effective_source": "personal", "provider": "grok"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "xai_images"
    assert classified["supports_resolution"] is True


def test_gemini_camelcase_modalities_are_detected_as_image_model():
    classified = _classify_gemini_image_model(
        {
            "name": "google/gemini-2.5-flash-image",
            "displayName": "Google: Gemini 2.5 Flash Image (Nano Banana)",
            "inputModalities": ["image", "text"],
            "outputModalities": ["image", "text"],
        },
        source={"effective_source": "settings"},
    )

    assert classified is not None
    assert classified["generation_mode"] == "gemini_generate_content_image"


def test_load_b64_image_data_normalizes_data_url_mime_type():
    loaded = load_b64_image_data("data:image/png;base64,YWJj")

    assert loaded == (b"abc", "image/png")


def test_openai_image_stream_detection_does_not_treat_json_response_as_stream():
    should_parse_stream = _should_parse_openai_image_response_as_stream(
        {"content-type": "application/json"},
        '{"data":[{"b64_json":"YWJj"}]}',
    )

    assert should_parse_stream is False


def test_openai_image_stream_detection_accepts_event_stream_header():
    should_parse_stream = _should_parse_openai_image_response_as_stream(
        {"content-type": "text/event-stream; charset=utf-8"},
        '{"data":[]}',
    )

    assert should_parse_stream is True


def test_openai_image_stream_detection_accepts_sse_body_without_header():
    should_parse_stream = _should_parse_openai_image_response_as_stream(
        {"content-type": "application/octet-stream"},
        'data: {"type":"image_generation.completed","b64_json":"YWJj"}\n\n',
    )

    assert should_parse_stream is True


def test_openai_response_extracts_markdown_embedded_image_data():
    images = _extract_generated_images_from_openai_response(
        {
            "choices": [
                {
                    "message": {
                        "content": "Here is your image: ![Generated](data:image/png;base64,YWJj)"
                    }
                }
            ]
        }
    )

    assert images == [(b"abc", "image/png")]


def test_openai_response_extracts_stream_delta_images():
    images = _extract_generated_images_from_openai_response(
        {
            "choices": [
                {
                    "delta": {
                        "images": [
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/png;base64,YWJj"},
                            }
                        ]
                    }
                }
            ]
        }
    )

    assert images == [(b"abc", "image/png")]


def test_openai_response_extracts_top_level_message_images():
    images = _extract_generated_images_from_openai_response(
        {
            "message": {
                "images": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,YWJj"},
                    }
                ]
            }
        }
    )

    assert images == [(b"abc", "image/png")]


def test_openai_response_extracts_file_image_event():
    images = _extract_generated_images_from_openai_response(
        {
            "type": "file",
            "file": {
                "mediaType": "image/jpeg",
                "base64": "YWJj",
            },
        }
    )

    assert images == [(b"abc", "image/jpeg")]


def test_openai_response_extracts_response_completed_image_generation_call():
    images = _extract_generated_images_from_openai_response(
        {
            "type": "response.completed",
            "response": {
                "output": [
                    {
                        "type": "image_generation_call",
                        "result": "YWJj",
                    }
                ],
            },
        }
    )

    assert images == [(b"abc", "image/png")]
