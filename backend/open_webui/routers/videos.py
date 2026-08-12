from __future__ import annotations

import asyncio
import base64
import copy
import json
import logging
import tempfile
import time
import uuid
from typing import Any, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from open_webui.models.files import FileForm, Files
from open_webui.models.users import Users
from open_webui.models.video_generation_jobs import (
    VIDEO_JOB_ACTIVE_STATUSES,
    VideoGenerationJobForm,
    VideoGenerationJobModel,
    VideoGenerationJobs,
)
from open_webui.routers.files import _user_can_access_file
from open_webui.storage.provider import Storage
from open_webui.utils.access_control import has_permission
from open_webui.utils.api_key_pool import get_api_key_attempts
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.model_identity import (
    build_model_lookup,
    build_model_ref,
    build_selection_id,
    derive_connection_id,
    get_model_ref_from_model,
    resolve_model_from_lookup,
)
from open_webui.utils.models import get_all_models
from open_webui.utils.user_connections import get_user_connections
from open_webui.utils.video_generation import (
    VIDEO_GENERATION_ASPECT_RATIOS,
    VIDEO_GENERATION_RESOLUTIONS,
    normalize_video_generation_config,
    resolve_video_generation_capability,
)


log = logging.getLogger(__name__)
router = APIRouter()

VIDEO_MAX_INPUT_BYTES = 20 * 1024 * 1024
VIDEO_MAX_OUTPUT_BYTES = 256 * 1024 * 1024
VIDEO_MAX_POLL_SECONDS = 2 * 60 * 60
VIDEO_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_DEFAULT_DURATION = 8

_worker_task: Optional[asyncio.Task] = None
_running_jobs: set[str] = set()


class VideoConfigForm(BaseModel):
    enabled: Optional[bool] = None
    shared_key_enabled: Optional[bool] = None


class VideoGenerationForm(BaseModel):
    model: str = Field(min_length=1, max_length=512)
    prompt: Optional[str] = Field(default=None, max_length=10000)
    reference_file_id: Optional[str] = Field(default=None, max_length=128)
    duration: int = Field(default=VIDEO_DEFAULT_DURATION, ge=1, le=15)
    aspect_ratio: str = Field(default="16:9", max_length=8)
    resolution: str = Field(default="720p", max_length=8)


class UpstreamVideoError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def _video_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state.config, "ENABLE_VIDEO_GENERATION", False))


def _can_use_video(request: Request, user) -> bool:
    if not _video_enabled(request):
        return False
    if getattr(user, "role", None) == "admin":
        return True
    try:
        return has_permission(
            user.id,
            "features.video_generation",
            request.app.state.config.USER_PERMISSIONS,
        )
    except Exception:
        return False


def _require_video_access(request: Request, user) -> None:
    if not _can_use_video(request, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "video_generation_disabled",
                "message": "Video generation is disabled or you do not have permission to use it.",
            },
        )


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _video_url(base_url: str, path: str) -> str:
    base = _clean_str(base_url).rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}/v1/{path.lstrip('/')}"


def _extract_models(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("data") or payload.get("models") or payload.get("items")
    if not isinstance(payload, list):
        return []
    return [model for model in payload if isinstance(model, dict)]


def _safe_upstream_message(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("message") or value.get("error") or value.get("detail")
    message = _clean_str(value)
    return message[:400] if message else "The video provider rejected the request."


def _json_response(response: requests.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:
        body = {}
    return body if isinstance(body, dict) else {}


def _request_upstream(
    method: str,
    url: str,
    api_key: str,
    *,
    payload: Optional[dict[str, Any]] = None,
    stream: bool = False,
) -> requests.Response:
    try:
        response = requests.request(
            method,
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json, video/mp4",
                "Content-Type": "application/json",
            },
            json=payload,
            stream=stream,
            timeout=90,
        )
    except requests.RequestException as exc:
        raise UpstreamVideoError(502, "provider_transport_error", "Video provider connection failed.") from exc

    if response.status_code >= 400:
        body = _json_response(response)
        response.close()
        raise UpstreamVideoError(
            response.status_code,
            str(body.get("code") or "provider_request_failed")[:80],
            _safe_upstream_message(body),
        )
    return response


def _get_connection_data(
    request: Request,
    user,
    model_ref: dict[str, Any],
) -> tuple[str, str, dict[str, Any], list[str], int, str]:
    source = _clean_str(model_ref.get("source") or "personal") or "personal"
    provider = _clean_str(model_ref.get("provider") or "openai").lower()
    if provider != "openai":
        raise HTTPException(status_code=400, detail={"code": "video_provider_unsupported", "message": "Video generation requires an OpenAI-compatible connection."})

    if source == "shared":
        if not bool(getattr(request.app.state.config, "ENABLE_VIDEO_GENERATION_SHARED_KEY", False)):
            raise HTTPException(status_code=403, detail={"code": "video_shared_key_disabled", "message": "The workspace shared video connection is disabled."})
        base_urls = list(getattr(request.app.state.config, "OPENAI_API_BASE_URLS", []) or [])
        keys = list(getattr(request.app.state.config, "OPENAI_API_KEYS", []) or [])
        configs = getattr(request.app.state.config, "OPENAI_API_CONFIGS", {}) or {}
    else:
        connections = get_user_connections(user)
        provider_config = connections.get("openai") if isinstance(connections, dict) else {}
        provider_config = provider_config if isinstance(provider_config, dict) else {}
        base_urls = list(provider_config.get("OPENAI_API_BASE_URLS") or [])
        keys = list(provider_config.get("OPENAI_API_KEYS") or [])
        configs = provider_config.get("OPENAI_API_CONFIGS") or {}

    configs = configs if isinstance(configs, dict) else {}
    connection_id = _clean_str(model_ref.get("connection_id") or model_ref.get("prefix_id"))
    raw_index = model_ref.get("connection_index")
    index: Optional[int] = None
    if raw_index is not None and _clean_str(raw_index) != "":
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            index = None
    if connection_id:
        for candidate_index, candidate_url in enumerate(base_urls):
            candidate = configs.get(str(candidate_index), configs.get(candidate_url, {})) or {}
            candidate_id = _clean_str(
                candidate.get("prefix_id")
                or candidate.get("_resolved_prefix_id")
                or (
                    _shared_connection_id(
                        candidate_index,
                        candidate_url,
                        keys[candidate_index] if candidate_index < len(keys) else "",
                        candidate,
                    )
                    if source == "shared"
                    else ""
                )
            )
            if candidate_id == connection_id:
                index = candidate_index
                break
    if index is None or index < 0 or index >= len(base_urls):
        raise HTTPException(status_code=400, detail={"code": "video_connection_unavailable", "message": "The selected video connection is no longer available."})

    url = _clean_str(base_urls[index])
    config = configs.get(str(index), configs.get(url, {})) or {}
    config = normalize_video_generation_config(config)
    prefix_id = _clean_str(config.get("prefix_id") or config.get("_resolved_prefix_id") or connection_id)
    connection_key = prefix_id or f"idx:{index}:{url}"
    fallback_key = keys[index] if index < len(keys) else ""
    attempts = get_api_key_attempts(
        provider="openai",
        connection_key=connection_key,
        api_config=config,
        fallback_key=fallback_key,
        include_retry=False,
    )
    if not attempts or not attempts[0].key:
        raise HTTPException(status_code=400, detail={"code": "video_credential_unavailable", "message": "The selected video connection has no usable API key."})
    return url, source, config, attempts, index, prefix_id


def _shared_connection_id(index: int, url: str, key: str, config: dict[str, Any]) -> str:
    configured = _clean_str(config.get("prefix_id") or config.get("_resolved_prefix_id"))
    if configured:
        return configured
    derived = derive_connection_id(
        provider="openai",
        source="shared",
        url=url,
        api_key=key,
        auth_type=config.get("auth_type"),
    )
    # Keep shared selections distinct without exposing the shared credential.
    return derived or f"shared-{index}"


async def _discover_shared_video_models(request: Request) -> list[dict[str, Any]]:
    if not bool(getattr(request.app.state.config, "ENABLE_VIDEO_GENERATION_SHARED_KEY", False)):
        return []

    base_urls = list(getattr(request.app.state.config, "OPENAI_API_BASE_URLS", []) or [])
    keys = list(getattr(request.app.state.config, "OPENAI_API_KEYS", []) or [])
    configs = getattr(request.app.state.config, "OPENAI_API_CONFIGS", {}) or {}
    configs = configs if isinstance(configs, dict) else {}
    result: list[dict[str, Any]] = []

    for index, base_url in enumerate(base_urls):
        url = _clean_str(base_url)
        if not url:
            continue
        raw_config = configs.get(str(index), configs.get(url, {})) or {}
        try:
            config = normalize_video_generation_config(raw_config)
        except ValueError:
            continue
        if config.get("enable", True) is False:
            continue
        connection_key = _shared_connection_id(
            index,
            url,
            keys[index] if index < len(keys) else "",
            config,
        )
        attempts = get_api_key_attempts(
            provider="openai",
            connection_key=connection_key,
            api_config=config,
            fallback_key=keys[index] if index < len(keys) else "",
            include_retry=False,
        )
        if not attempts or not attempts[0].key:
            continue

        discovered: list[dict[str, Any]] = []
        try:
            response = await asyncio.to_thread(
                _request_upstream,
                "GET",
                _video_url(url, "models"),
                attempts[0].key,
            )
            try:
                discovered = _extract_models(_json_response(response))
            finally:
                response.close()
        except UpstreamVideoError:
            # Explicit model IDs remain usable when a grok2api model list is incomplete.
            discovered = []

        connection_id = _shared_connection_id(
            index,
            url,
            keys[index] if index < len(keys) else "",
            config,
        )
        seen_ids: set[str] = set()
        candidates = [
            *discovered,
            *({"id": model_id, "name": model_id} for model_id in config.get("video_generation_model_ids", [])),
        ]
        for candidate in candidates:
            model_id = _clean_str(candidate.get("id") or candidate.get("model_id") or candidate.get("name"))
            if not model_id:
                continue
            prefix = f"{connection_id}."
            if model_id.startswith(prefix):
                model_id = model_id[len(prefix) :]
            if model_id in seen_ids:
                continue
            capability = resolve_video_generation_capability(model_id, config)
            if not capability.get("video_generation_supported"):
                continue
            seen_ids.add(model_id)
            model_ref = build_model_ref(
                provider="openai",
                source="shared",
                connection_index=index,
                connection_id=connection_id,
            )
            selection_id = build_selection_id(
                provider="openai",
                source="shared",
                connection_id=connection_id,
                connection_index=index,
                model_id=model_id,
            )
            result.append(
                {
                    "id": selection_id,
                    "selection_id": selection_id,
                    "model_id": model_id,
                    "original_id": model_id,
                    "name": _clean_str(candidate.get("name") or model_id),
                    "model_ref": model_ref,
                    "source": "shared",
                    "connection_name": _clean_str(config.get("remark") or config.get("name")) or "Workspace shared",
                    **capability,
                }
            )
    return result


async def _resolve_video_model(request: Request, user, selection_id: str) -> dict[str, Any]:
    models = _extract_models(await get_all_models(request, user=user))
    if bool(getattr(request.app.state.config, "ENABLE_VIDEO_GENERATION_SHARED_KEY", False)):
        models.extend(await _discover_shared_video_models(request))
    requested = _clean_str(selection_id)
    lookup, ambiguous = build_model_lookup(models)
    selected = resolve_model_from_lookup(lookup, ambiguous, requested)
    if not selected:
        raise HTTPException(status_code=400, detail={"code": "video_model_unavailable", "message": "The selected video model is unavailable."})

    model_ref = get_model_ref_from_model(selected)
    model_ref.setdefault("provider", "openai")
    model_id = _clean_str(selected.get("original_id") or selected.get("model_id") or selected.get("id"))
    _url, _source, config, _attempts, _index, _prefix = _get_connection_data(request, user, model_ref)
    capability = resolve_video_generation_capability(model_id, config)
    if not capability.get("video_generation_supported"):
        raise HTTPException(status_code=400, detail={"code": "video_model_unsupported", "message": "The selected model does not support video generation through this connection."})
    return {
        "model": selected,
        "model_id": model_id,
        "model_ref": model_ref,
        "capability": capability,
    }


def _validate_options(form: VideoGenerationForm, capability: dict[str, Any]) -> None:
    support = capability.get("video_generation_support") or {}
    duration = support.get("duration") or {}
    ratios = support.get("aspect_ratios") or list(VIDEO_GENERATION_ASPECT_RATIOS)
    resolutions = support.get("resolutions") or list(VIDEO_GENERATION_RESOLUTIONS)
    if not int(duration.get("min", 1)) <= form.duration <= int(duration.get("max", 15)):
        raise HTTPException(status_code=400, detail={"code": "video_duration_invalid", "message": "The selected duration is not supported by this model."})
    if form.aspect_ratio not in ratios:
        raise HTTPException(status_code=400, detail={"code": "video_aspect_ratio_invalid", "message": "The selected aspect ratio is not supported by this model."})
    if form.resolution not in resolutions:
        raise HTTPException(status_code=400, detail={"code": "video_resolution_invalid", "message": "The selected resolution is not supported by this model."})
    if not _clean_str(form.prompt) and not form.reference_file_id:
        raise HTTPException(status_code=400, detail={"code": "video_prompt_or_image_required", "message": "Provide a prompt or one reference image."})


def _read_reference_data_url(file_id: str, user) -> str:
    file = Files.get_file_by_id(file_id)
    if not file or not _user_can_access_file(file, user, "read"):
        raise HTTPException(status_code=404, detail={"code": "reference_file_not_found", "message": "The reference image is unavailable."})
    content_type = _clean_str((file.meta or {}).get("content_type")).lower()
    if content_type not in VIDEO_ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail={"code": "reference_file_type_invalid", "message": "Only JPEG, PNG, and WebP reference images are supported."})
    if not file.path:
        raise HTTPException(status_code=400, detail={"code": "reference_file_unavailable", "message": "The reference image has no stored content."})
    try:
        local_path = Storage.get_file(file.path)
        with open(local_path, "rb") as source:
            data = source.read(VIDEO_MAX_INPUT_BYTES + 1)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "reference_file_unavailable", "message": "The reference image could not be read."}) from exc
    if len(data) > VIDEO_MAX_INPUT_BYTES:
        raise HTTPException(status_code=413, detail={"code": "reference_file_too_large", "message": "Reference images must be 20 MiB or smaller."})
    if not data:
        raise HTTPException(status_code=400, detail={"code": "reference_file_empty", "message": "The reference image is empty."})
    return f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"


def _serialize_job(job: VideoGenerationJobModel, *, user_id: str) -> dict[str, Any]:
    payload = job.model_dump()
    payload.pop("credential_entry_id", None)
    payload["error"] = (
        {"code": job.error_code, "message": job.error_message}
        if job.error_code or job.error_message
        else None
    )
    if job.result_file_id:
        file = Files.get_file_by_id(job.result_file_id)
        if file and file.user_id == user_id:
            name = (file.meta or {}).get("name") or file.filename
            payload["result_file_name"] = name
            payload["result_file_url"] = f"/api/v1/files/{file.id}/content"
            payload["file_exists"] = True
        else:
            payload["file_exists"] = False
    return payload


def _submit_video(
    base_url: str,
    api_key: str,
    model_id: str,
    form: VideoGenerationForm,
    reference_data_url: Optional[str],
) -> str:
    payload: dict[str, Any] = {
        "model": model_id,
        "duration": form.duration,
        "aspect_ratio": form.aspect_ratio,
        "resolution": form.resolution,
    }
    if _clean_str(form.prompt):
        payload["prompt"] = form.prompt.strip()
    if reference_data_url:
        payload["image"] = {"url": reference_data_url}
    response = _request_upstream(
        "POST",
        _video_url(base_url, "videos/generations"),
        api_key,
        payload=payload,
    )
    try:
        body = _json_response(response)
    finally:
        response.close()
    request_id = _clean_str(body.get("request_id") or body.get("id"))
    if not request_id:
        raise UpstreamVideoError(502, "provider_invalid_response", "The video provider returned no request ID.")
    return request_id


def _poll_video(base_url: str, api_key: str, request_id: str) -> dict[str, Any]:
    response = _request_upstream(
        "GET",
        _video_url(base_url, f"videos/{request_id}"),
        api_key,
    )
    try:
        return _json_response(response)
    finally:
        response.close()


def _download_video_to_file(base_url: str, api_key: str, request_id: str, user_id: str, job_id: str) -> str:
    response = _request_upstream(
        "GET",
        _video_url(base_url, f"videos/{request_id}/content"),
        api_key,
        stream=True,
    )
    storage_path = None
    try:
        content_type = _clean_str(response.headers.get("content-type")).split(";", 1)[0].lower()
        if content_type != "video/mp4":
            raise UpstreamVideoError(502, "provider_invalid_video_type", "The video provider returned an unsupported content type.")
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as output:
            total = 0
            prefix = b""
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > VIDEO_MAX_OUTPUT_BYTES:
                    raise UpstreamVideoError(413, "provider_video_too_large", "The generated video exceeds the 256 MiB limit.")
                if len(prefix) < 16:
                    prefix += chunk[: 16 - len(prefix)]
                output.write(chunk)
            if total < 12 or prefix[4:8] != b"ftyp":
                raise UpstreamVideoError(502, "provider_invalid_video", "The provider returned an invalid MP4 video.")
            output.seek(0)
            filename = f"video_generation_{job_id}.mp4"
            _size, storage_path = Storage.upload_file(output, filename)
        file_id = str(uuid.uuid4())
        file_item = Files.insert_new_file(
            user_id,
            FileForm(
                id=file_id,
                filename=f"video_generation_{job_id}.mp4",
                path=storage_path,
                meta={
                    "name": f"video_generation_{job_id}.mp4",
                    "content_type": "video/mp4",
                    "size": total,
                    "data": {"source": "video_generation", "job_id": job_id},
                },
            ),
        )
        if not file_item:
            raise RuntimeError("Failed to persist generated video metadata.")
        return file_id
    except Exception:
        if storage_path:
            try:
                Storage.delete_file(storage_path)
            except Exception:
                log.exception("Failed to clean up generated video storage")
        raise
    finally:
        response.close()


async def _resolve_job_connection(request: Request, job: VideoGenerationJobModel, user):
    model_ref = {
        "provider": job.provider,
        "source": job.source,
        "connection_id": job.connection_id,
        "connection_index": job.connection_index,
    }
    base_url, _source, config, attempts, index, prefix_id = _get_connection_data(request, user, model_ref)
    selected = next((attempt for attempt in attempts if attempt.id == job.credential_entry_id), None)
    if selected is None:
        raise HTTPException(status_code=409, detail={"code": "video_credential_unavailable", "message": "The API key used by this video task is no longer available."})
    return base_url, config, selected.key, index, prefix_id


async def _process_job(request: Request, job_id: str) -> None:
    try:
        job = await asyncio.to_thread(VideoGenerationJobs.get_job_by_id, job_id)
        if not job or job.status not in VIDEO_JOB_ACTIVE_STATUSES:
            return
        job = await asyncio.to_thread(VideoGenerationJobs.claim_job, job.id, job.status)
        if not job:
            return
        now = int(time.time())
        if now - int(job.created_at or now) > VIDEO_MAX_POLL_SECONDS:
            await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job.id, status="timed_out", error_code="video_generation_timeout", error_message="The video task exceeded the two-hour limit.", completed_at=now)
            return
        user = await asyncio.to_thread(Users.get_user_by_id, job.user_id)
        if not user:
            await asyncio.to_thread(VideoGenerationJobs.delete_job_by_id, job.id)
            return
        if job.status == "submitting":
            await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job.id, status="failed", error_code="submission_outcome_unknown", error_message="The task was interrupted before its provider request ID was recorded.", completed_at=now)
            return
        try:
            base_url, _config, api_key, _index, _prefix = await _resolve_job_connection(request, job, user)
            body = await asyncio.to_thread(_poll_video, base_url, api_key, job.upstream_request_id)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job.id, status="failed", error_code=detail.get("code", "credential_unavailable"), error_message=detail.get("message", "The video credential is unavailable."), completed_at=now)
            return
        except UpstreamVideoError as exc:
            if exc.status_code < 500 and exc.status_code not in {408, 425, 429}:
                await asyncio.to_thread(
                    VideoGenerationJobs.update_job_by_id,
                    job.id,
                    status="failed",
                    error_code=exc.code,
                    error_message=exc.message,
                    completed_at=now,
                    last_polled_at=now,
                    next_poll_at=None,
                )
                return
            attempt = int(job.attempt_count or 0) + 1
            delay = min(30, 2 ** min(attempt, 5))
            await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job.id, status="pending", attempt_count=attempt, next_poll_at=now + delay, last_polled_at=now, error_code=None, error_message=None)
            return

        state = _clean_str(body.get("status")).lower()
        progress = body.get("progress")
        try:
            progress = max(0, min(100, int(progress))) if progress is not None else job.progress
        except (TypeError, ValueError):
            progress = job.progress
        if state in {"pending", "processing", "running"}:
            await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job.id, status="pending", progress=progress, next_poll_at=now + 3, last_polled_at=now, attempt_count=int(job.attempt_count or 0) + 1)
            return
        if state in {"failed", "error"}:
            error = body.get("error") if isinstance(body.get("error"), dict) else {}
            await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job.id, status="failed", progress=progress, error_code=_clean_str(error.get("code") or "provider_generation_failed")[:80], error_message=_safe_upstream_message(error), completed_at=now, last_polled_at=now)
            return
        if state != "done":
            await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job.id, status="pending", progress=progress, next_poll_at=now + 3, last_polled_at=now)
            return

        downloading = await asyncio.to_thread(
            VideoGenerationJobs.update_job_by_id,
            job.id,
            status="downloading",
            progress=100,
            last_polled_at=now,
            next_poll_at=int(time.time()) + 300,
        )
        if not downloading or downloading.status != "downloading":
            return
        try:
            file_id = await asyncio.to_thread(_download_video_to_file, base_url, api_key, job.upstream_request_id, job.user_id, job.id)
        except UpstreamVideoError as exc:
            await asyncio.to_thread(
                VideoGenerationJobs.update_job_by_id,
                job.id,
                status="failed",
                error_code=exc.code,
                error_message=exc.message,
                completed_at=int(time.time()),
                next_poll_at=None,
            )
            return
        except Exception:
            await asyncio.to_thread(
                VideoGenerationJobs.update_job_by_id,
                job.id,
                status="failed",
                error_code="video_file_persist_failed",
                error_message="The generated video could not be saved.",
                completed_at=int(time.time()),
                next_poll_at=None,
            )
            return
        await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job.id, status="completed", progress=100, result_file_id=file_id, completed_at=int(time.time()), next_poll_at=None)
    except Exception as exc:
        log.exception("Video generation job %s failed: %s", job_id, type(exc).__name__)
        try:
            await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job_id, status="failed", error_code="video_generation_worker_error", error_message="The video task failed while being processed.", completed_at=int(time.time()))
        except Exception:
            log.exception("Failed to persist video generation worker error")
    finally:
        _running_jobs.discard(job_id)


async def _video_worker(request: Request) -> None:
    while True:
        try:
            jobs = await asyncio.to_thread(VideoGenerationJobs.get_due_jobs, limit=10)
            for job in jobs:
                if job.id in _running_jobs:
                    continue
                _running_jobs.add(job.id)
                asyncio.create_task(_process_job(request, job.id))
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Video generation worker iteration failed")
            await asyncio.sleep(5)


async def start_video_generation_worker(request: Request) -> None:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_video_worker(request))


async def stop_video_generation_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    _worker_task = None
    _running_jobs.clear()


@router.get("/config")
async def get_video_config(request: Request, user=Depends(get_admin_user)):
    return {
        "enabled": bool(getattr(request.app.state.config, "ENABLE_VIDEO_GENERATION", False)),
        "shared_key_enabled": bool(getattr(request.app.state.config, "ENABLE_VIDEO_GENERATION_SHARED_KEY", False)),
    }


@router.post("/config/update")
async def update_video_config(request: Request, form_data: VideoConfigForm, user=Depends(get_admin_user)):
    if form_data.enabled is not None:
        request.app.state.config.ENABLE_VIDEO_GENERATION = form_data.enabled
    if form_data.shared_key_enabled is not None:
        request.app.state.config.ENABLE_VIDEO_GENERATION_SHARED_KEY = form_data.shared_key_enabled
    return await get_video_config(request, user=user)


@router.get("/models")
async def get_video_models(request: Request, user=Depends(get_verified_user)):
    _require_video_access(request, user)
    models = _extract_models(await get_all_models(request, user=user))
    models.extend(await _discover_shared_video_models(request))
    result = []
    for model in models or []:
        if not isinstance(model, dict):
            continue
        model_ref = get_model_ref_from_model(model)
        provider = _clean_str(model_ref.get("provider") or model.get("owned_by")).lower()
        if provider != "openai":
            continue
        model_id = _clean_str(model.get("original_id") or model.get("model_id") or model.get("id"))
        try:
            _url, _source, config, _attempts, _index, _prefix = _get_connection_data(request, user, model_ref)
            capability = resolve_video_generation_capability(model_id, config)
        except (HTTPException, ValueError):
            continue
        if not capability.get("video_generation_supported"):
            continue
        item = {
            "id": _clean_str(model.get("selection_id") or model.get("id")),
            "selection_id": _clean_str(model.get("selection_id") or model.get("id")),
            "model_id": model_id,
            "name": _clean_str(model.get("name") or model_id),
            "model_ref": copy.deepcopy(model_ref),
            **capability,
        }
        result.append(item)
    return {"models": result}


@router.post("/generations", status_code=status.HTTP_202_ACCEPTED)
async def create_video_generation(request: Request, form_data: VideoGenerationForm, user=Depends(get_verified_user)):
    _require_video_access(request, user)
    resolved = await _resolve_video_model(request, user, form_data.model)
    _validate_options(form_data, resolved["capability"])
    reference_data_url = _read_reference_data_url(form_data.reference_file_id, user) if form_data.reference_file_id else None
    model_ref = resolved["model_ref"]
    base_url, source, config, attempts, index, prefix_id = _get_connection_data(request, user, model_ref)
    attempt = attempts[0]
    job = VideoGenerationJobs.insert_new_job(
        user.id,
        VideoGenerationJobForm(
            model_selection_id=_clean_str(resolved["model"].get("selection_id") or form_data.model),
            model_id=resolved["model_id"],
            provider="openai",
            source=source,
            connection_id=prefix_id or None,
            connection_index=str(index),
            credential_entry_id=attempt.id,
            prompt=form_data.prompt.strip() if form_data.prompt else None,
            duration=form_data.duration,
            aspect_ratio=form_data.aspect_ratio,
            resolution=form_data.resolution,
            reference_file_id=form_data.reference_file_id,
            next_poll_at=int(time.time()) + 120,
        ),
    )
    if not job:
        raise HTTPException(status_code=500, detail={"code": "video_job_persist_failed", "message": "The video task could not be saved."})
    try:
        request_id = await asyncio.to_thread(_submit_video, base_url, attempt.key, resolved["model_id"], form_data, reference_data_url)
    except UpstreamVideoError as exc:
        await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job.id, status="failed", error_code=exc.code, error_message=exc.message, completed_at=int(time.time()))
        raise HTTPException(status_code=exc.status_code if 400 <= exc.status_code < 500 else 502, detail={"code": exc.code, "message": exc.message, "job_id": job.id}) from exc
    except Exception as exc:
        await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job.id, status="failed", error_code="submission_outcome_unknown", error_message="The provider result is unknown; the task was not retried.", completed_at=int(time.time()))
        raise HTTPException(status_code=502, detail={"code": "submission_outcome_unknown", "message": "The provider result is unknown; the task was not retried.", "job_id": job.id}) from exc
    updated = await asyncio.to_thread(VideoGenerationJobs.update_job_by_id, job.id, status="pending", upstream_request_id=request_id, submitted_at=int(time.time()), next_poll_at=int(time.time()) + 2)
    return _serialize_job(updated or job, user_id=user.id)


@router.get("/jobs")
async def get_video_jobs(request: Request, skip: int = 0, limit: int = 50, user=Depends(get_verified_user)):
    _require_video_access(request, user)
    skip = max(0, skip)
    limit = min(100, max(1, limit))
    jobs = await asyncio.to_thread(VideoGenerationJobs.get_jobs_by_user_id, user.id, skip=skip, limit=limit)
    return {"jobs": [_serialize_job(job, user_id=user.id) for job in jobs]}


@router.get("/jobs/{job_id}")
async def get_video_job(request: Request, job_id: str, user=Depends(get_verified_user)):
    _require_video_access(request, user)
    job = await asyncio.to_thread(VideoGenerationJobs.get_job_by_id_and_user_id, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "video_job_not_found", "message": "Video task not found."})
    return _serialize_job(job, user_id=user.id)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video_job(request: Request, job_id: str, user=Depends(get_verified_user)):
    _require_video_access(request, user)
    job = await asyncio.to_thread(VideoGenerationJobs.get_job_by_id_and_user_id, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "video_job_not_found", "message": "Video task not found."})
    if job.status in VIDEO_JOB_ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail={"code": "video_job_active", "message": "Active video tasks cannot be deleted."})
    if job.result_file_id:
        file = Files.get_file_by_id(job.result_file_id, include_pending=True)
        if file:
            try:
                if file.path:
                    Storage.delete_file(file.path)
                if not Files.delete_file_by_id(file.id):
                    raise RuntimeError("file row cleanup failed")
            except Exception as exc:
                raise HTTPException(status_code=503, detail={"code": "video_file_cleanup_pending", "message": "The generated video could not be deleted and can be retried."}) from exc
    if not await asyncio.to_thread(VideoGenerationJobs.delete_job_by_id, job.id):
        raise HTTPException(status_code=500, detail={"code": "video_job_delete_failed", "message": "The video task could not be deleted."})
    return None


__all__ = ["router", "start_video_generation_worker", "stop_video_generation_worker"]
