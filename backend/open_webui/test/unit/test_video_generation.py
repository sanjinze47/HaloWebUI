import asyncio
import pathlib
import sys
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.routers.openai import (  # noqa: E402
    OpenAIConfigForm,
    _apply_native_web_search_support_to_models_response,
    _validate_openai_api_configs,
    get_all_models_responses,
    update_config,
)
from open_webui.routers import videos as videos_router  # noqa: E402
from open_webui.models.video_generation_jobs import (  # noqa: E402
    VideoGenerationJobModel,
)
from open_webui.utils.video_generation import (  # noqa: E402
    is_video_generation_model_supported,
    normalize_video_generation_config,
    normalize_video_generation_model_ids,
    resolve_video_generation_capability,
    resolve_video_generation_compatibility,
)


def test_missing_mode_defaults_to_disabled_without_legacy_name():
    assert resolve_video_generation_compatibility({}) == "disabled"
    assert is_video_generation_model_supported("grok-imagine-video", {}) is False


def test_missing_mode_uses_grok2api_legacy_name_or_remark():
    assert (
        resolve_video_generation_compatibility({"name": "Grok2API relay"})
        == "grok2api"
    )
    assert (
        resolve_video_generation_compatibility({"remark": "internal grok2api"})
        == "grok2api"
    )


def test_explicit_disabled_overrides_legacy_name():
    config = {
        "name": "grok2api relay",
        "video_generation_compatibility": " disabled ",
    }

    assert resolve_video_generation_compatibility(config) == "disabled"
    assert is_video_generation_model_supported("grok-imagine-video", config) is False


def test_explicit_grok2api_supports_only_exact_or_configured_model_ids():
    config = {
        "video_generation_compatibility": "grok2api",
        "video_generation_model_ids": [" custom-video ", "custom-video"],
    }

    assert is_video_generation_model_supported("grok-imagine-video", config) is True
    assert is_video_generation_model_supported("grok-imagine-video-1.5", config) is True
    assert is_video_generation_model_supported("custom-video", config) is True
    assert is_video_generation_model_supported("grok-imagine-video-preview", config) is False
    assert is_video_generation_model_supported("other-video", config) is False


def test_video_capability_has_stable_contract_and_does_not_expose_config_values():
    capability = resolve_video_generation_capability(
        "grok-imagine-video",
        {
            "video_generation_compatibility": "grok2api",
            "api_key": "must-not-leak",
        },
    )

    assert capability["video_generation_supported"] is True
    assert capability["video_generation_support"] == {
        "mode": "grok2api",
        "async": True,
        "text_to_video": True,
        "image_to_video": True,
        "max_reference_images": 1,
        "duration": {"min": 1, "max": 15, "default": 8},
        "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
        "resolutions": ["480p", "720p"],
    }
    assert "api_key" not in capability

    capability["video_generation_support"]["duration"]["max"] = 1
    second_capability = resolve_video_generation_capability(
        "grok-imagine-video",
        {"video_generation_compatibility": "grok2api"},
    )
    assert second_capability["video_generation_support"]["duration"]["max"] == 15


@pytest.mark.parametrize(
    "value",
    [
        "custom-video",
        ["custom-video", 1],
        ["custom-video", "   "],
        {"id": "custom-video"},
    ],
)
def test_video_model_ids_reject_non_string_or_empty_values(value):
    with pytest.raises(ValueError, match="video_generation_model_ids"):
        normalize_video_generation_model_ids(value)


def test_video_config_normalization_adds_defaults_and_deduplicates_ids():
    original = {
        "remark": "Video relay",
        "video_generation_model_ids": [" custom-video ", "custom-video"],
    }

    normalized = normalize_video_generation_config(original)

    assert normalized["video_generation_compatibility"] == "disabled"
    assert normalized["video_generation_model_ids"] == ["custom-video"]
    assert "video_generation_compatibility" not in original


@pytest.mark.parametrize(
    "config",
    [
        {"video_generation_compatibility": "unknown"},
        {"video_generation_compatibility": 1},
    ],
)
def test_video_config_rejects_invalid_compatibility(config):
    with pytest.raises(ValueError, match="video generation|video_generation"):
        normalize_video_generation_config(config)


def test_capability_validation_rejects_invalid_ids_even_when_disabled():
    with pytest.raises(ValueError, match="video_generation_model_ids"):
        resolve_video_generation_capability(
            "grok-imagine-video",
            {
                "video_generation_compatibility": "disabled",
                "video_generation_model_ids": [""],
            },
        )


def test_openai_config_validation_normalizes_video_fields_without_keys():
    normalized = _validate_openai_api_configs(
        {
            "0": {"remark": "grok2api relay", "api_key": "secret"},
            "1": {"video_generation_compatibility": "disabled"},
        }
    )

    assert normalized["0"]["video_generation_compatibility"] == "grok2api"
    assert normalized["0"]["video_generation_model_ids"] == []
    assert normalized["1"]["video_generation_compatibility"] == "disabled"
    assert normalized["0"]["api_key"] == "secret"


def test_openai_models_response_gets_video_capability_after_prefix_resolution():
    body = {
        "object": "list",
        "data": [{"id": "abc12345.grok-imagine-video", "name": "Video"}],
    }

    result = _apply_native_web_search_support_to_models_response(
        body,
        url="https://relay.example/v1",
        api_config={
            "_resolved_prefix_id": "abc12345",
            "video_generation_compatibility": "grok2api",
        },
    )

    model = result["data"][0]
    assert model["video_generation_supported"] is True
    assert model["video_generation_support"]["mode"] == "grok2api"
    assert "api_key" not in model


def test_openai_aggregated_models_get_video_capability(monkeypatch):
    monkeypatch.setattr(
        "open_webui.routers.openai._get_openai_user_config",
        lambda _user: (
            ["https://relay.example/v1"],
            ["secret-key"],
            {"0": {"video_generation_compatibility": "grok2api"}},
        ),
    )
    monkeypatch.setattr(
        "open_webui.routers.openai._normalize_openai_connection_key",
        lambda key, config, *, url_idx=None: (key, config),
    )

    async def fake_send_get_request(*_args, **_kwargs):
        return {
            "object": "list",
            "data": [{"id": "grok-imagine-video", "name": "Grok Video"}],
        }

    monkeypatch.setattr(
        "open_webui.routers.openai.send_get_request",
        fake_send_get_request,
    )

    result = asyncio.run(
        get_all_models_responses(SimpleNamespace(), SimpleNamespace(id="user-1"))
    )

    model = result[0]["data"][0]
    assert model["video_generation_supported"] is True
    assert model["video_generation_support"]["image_to_video"] is True


def test_openai_config_update_validation_returns_http_400_for_invalid_video_ids():
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                config=SimpleNamespace(
                    OPENAI_API_BASE_URLS=[],
                    OPENAI_API_KEYS=[],
                    OPENAI_API_CONFIGS={},
                )
            )
        )
    )
    form_data = OpenAIConfigForm(
        OPENAI_API_BASE_URLS=[],
        OPENAI_API_KEYS=[],
        OPENAI_API_CONFIGS={"0": {"video_generation_model_ids": ["ok", 3]}},
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(update_config(request, form_data, user=SimpleNamespace(id="admin")))

    assert exc_info.value.status_code == 400


def test_video_model_route_extracts_models_from_standard_data_envelope(monkeypatch):
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                config=SimpleNamespace(
                    ENABLE_VIDEO_GENERATION=True,
                    ENABLE_VIDEO_GENERATION_SHARED_KEY=False,
                )
            )
        )
    )
    user = SimpleNamespace(id="user-1", role="user")
    model = {
        "id": "grok-imagine-video",
        "original_id": "grok-imagine-video",
        "selection_id": "modelref::openai::personal::none::grok-imagine-video",
        "name": "Grok Video",
        "owned_by": "openai",
        "model_ref": {
            "provider": "openai",
            "source": "personal",
            "connection_index": 0,
        },
    }

    async def fake_get_all_models(*_args, **_kwargs):
        return {"data": [model]}

    monkeypatch.setattr(videos_router, "_require_video_access", lambda *_args: None)
    monkeypatch.setattr(videos_router, "get_all_models", fake_get_all_models)
    monkeypatch.setattr(
        videos_router,
        "_get_connection_data",
        lambda *_args: (
            "https://relay.example/v1",
            "personal",
            {"video_generation_compatibility": "grok2api"},
            [SimpleNamespace(key="secret", id="key-1")],
            0,
            "",
        ),
    )

    response = asyncio.run(videos_router.get_video_models(request, user=user))

    assert response["models"][0]["model_id"] == "grok-imagine-video"
    assert response["models"][0]["video_generation_supported"] is True


def test_shared_video_models_use_configured_ids_when_models_endpoint_is_incomplete(monkeypatch):
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                config=SimpleNamespace(
                    ENABLE_VIDEO_GENERATION_SHARED_KEY=True,
                    OPENAI_API_BASE_URLS=["https://shared.example/v1"],
                    OPENAI_API_KEYS=["shared-secret"],
                    OPENAI_API_CONFIGS={
                        "0": {
                            "video_generation_compatibility": "grok2api",
                            "video_generation_model_ids": ["custom-video"],
                        }
                    },
                )
            )
        )
    )

    class FakeResponse:
        headers = {"content-type": "application/json"}

        def json(self):
            return {"data": [{"id": "grok-imagine-video"}]}

        def close(self):
            return None

    monkeypatch.setattr(videos_router, "_request_upstream", lambda *_args, **_kwargs: FakeResponse())

    models = asyncio.run(videos_router._discover_shared_video_models(request))

    assert {model["model_id"] for model in models} == {
        "grok-imagine-video",
        "custom-video",
    }
    assert all(model["model_ref"]["source"] == "shared" for model in models)


def test_submit_video_sends_grok2api_payload_once(monkeypatch):
    captured = []

    class FakeResponse:
        def json(self):
            return {"request_id": "request-1"}

        def close(self):
            return None

    def fake_request(method, url, api_key, **kwargs):
        captured.append((method, url, api_key, kwargs))
        return FakeResponse()

    monkeypatch.setattr(videos_router, "_request_upstream", fake_request)
    form = videos_router.VideoGenerationForm(
        model="grok-imagine-video",
        prompt="A slow camera move",
        reference_file_id=None,
        duration=8,
        aspect_ratio="16:9",
        resolution="720p",
    )

    request_id = videos_router._submit_video(
        "https://relay.example/v1",
        "secret",
        "grok-imagine-video",
        form,
        "data:image/png;base64,AAAA",
    )

    assert request_id == "request-1"
    assert len(captured) == 1
    method, url, api_key, kwargs = captured[0]
    assert method == "POST"
    assert url == "https://relay.example/v1/videos/generations"
    assert api_key == "secret"
    assert kwargs["payload"]["image"] == {"url": "data:image/png;base64,AAAA"}
    assert kwargs["payload"]["duration"] == 8


def test_download_video_requires_mp4_content_and_persists_file(monkeypatch):
    class FakeResponse:
        headers = {"content-type": "video/mp4; charset=binary"}

        def iter_content(self, chunk_size):
            assert chunk_size == 1024 * 1024
            return [b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"]

        def close(self):
            return None

    monkeypatch.setattr(videos_router, "_request_upstream", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(videos_router.Storage, "upload_file", lambda *_args: (20, "video-path"))
    monkeypatch.setattr(
        videos_router.Files,
        "insert_new_file",
        lambda user_id, form: SimpleNamespace(id=form.id, user_id=user_id),
    )

    file_id = videos_router._download_video_to_file(
        "https://relay.example/v1",
        "secret",
        "request-1",
        "user-1",
        "job-1",
    )

    assert file_id


def test_poll_provider_rejection_is_terminal_and_not_retried(monkeypatch):
    job = VideoGenerationJobModel(
        id="job-1",
        user_id="user-1",
        model_selection_id="selection-1",
        model_id="grok-imagine-video",
        provider="openai",
        source="personal",
        connection_index="0",
        credential_entry_id="key-1",
        upstream_request_id="request-1",
        duration=8,
        aspect_ratio="16:9",
        resolution="720p",
        status="pending",
        created_at=int(time.time()),
        updated_at=int(time.time()),
    )
    updates = []

    monkeypatch.setattr(videos_router.VideoGenerationJobs, "get_job_by_id", lambda *_args: job)
    monkeypatch.setattr(videos_router.VideoGenerationJobs, "claim_job", lambda *_args: job)
    monkeypatch.setattr(videos_router.Users, "get_user_by_id", lambda *_args: SimpleNamespace(id="user-1"))
    monkeypatch.setattr(
        videos_router,
        "_resolve_job_connection",
        lambda *_args: asyncio.sleep(0, result=("https://relay.example/v1", {}, "secret", 0, "")),
    )

    def reject(*_args, **_kwargs):
        raise videos_router.UpstreamVideoError(400, "provider_invalid_request", "The request was rejected.")

    monkeypatch.setattr(videos_router, "_poll_video", reject)
    monkeypatch.setattr(
        videos_router.VideoGenerationJobs,
        "update_job_by_id",
        lambda job_id, **kwargs: updates.append((job_id, kwargs)) or job,
    )

    asyncio.run(videos_router._process_job(SimpleNamespace(), "job-1"))

    assert updates
    assert updates[-1][1]["status"] == "failed"
    assert updates[-1][1]["error_code"] == "provider_invalid_request"
