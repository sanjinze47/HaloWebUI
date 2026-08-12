"""Compatibility metadata for OpenAI-compatible video generation gateways."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional


VIDEO_GENERATION_COMPATIBILITY_MODES = frozenset({"disabled", "grok2api"})
VIDEO_GENERATION_BUILTIN_MODEL_IDS = frozenset(
    {
        "grok-imagine-video",
        "grok-imagine-video-1.5",
    }
)

VIDEO_GENERATION_ASPECT_RATIOS = (
    "1:1",
    "16:9",
    "9:16",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
)
VIDEO_GENERATION_RESOLUTIONS = ("480p", "720p")

_VIDEO_GENERATION_SUPPORT = {
    "mode": "grok2api",
    "async": True,
    "text_to_video": True,
    "image_to_video": True,
    "max_reference_images": 1,
    "duration": {
        "min": 1,
        "max": 15,
        "default": 8,
    },
    "aspect_ratios": list(VIDEO_GENERATION_ASPECT_RATIOS),
    "resolutions": list(VIDEO_GENERATION_RESOLUTIONS),
}

_MISSING = object()


def _legacy_grok2api_name(config: dict[str, Any]) -> bool:
    labels = (config.get("name"), config.get("remark"))
    return any("grok2api" in str(label).strip().lower() for label in labels if label)


def normalize_video_generation_model_ids(value: Any = _MISSING) -> list[str]:
    """Validate and normalize explicitly configured video model IDs."""
    if value is _MISSING:
        return []
    if not isinstance(value, list):
        raise ValueError("video_generation_model_ids must be an array of strings.")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(
                "video_generation_model_ids must contain only strings."
            )
        model_id = item.strip()
        if not model_id:
            raise ValueError(
                "video_generation_model_ids must not contain empty values."
            )
        if model_id in seen:
            continue
        seen.add(model_id)
        normalized.append(model_id)

    return normalized


def resolve_video_generation_compatibility(config: Optional[dict]) -> str:
    """Resolve the explicit or legacy video gateway compatibility mode."""
    config = config if isinstance(config, dict) else {}
    if "video_generation_compatibility" in config:
        configured_mode = config.get("video_generation_compatibility")
        if not isinstance(configured_mode, str):
            raise ValueError(
                "video_generation_compatibility must be disabled or grok2api."
            )
        mode = configured_mode.strip().lower()
        if mode not in VIDEO_GENERATION_COMPATIBILITY_MODES:
            allowed = ", ".join(sorted(VIDEO_GENERATION_COMPATIBILITY_MODES))
            raise ValueError(
                "Invalid video generation compatibility mode "
                f"{mode!r}; expected one of: {allowed}."
            )
        return mode

    if _legacy_grok2api_name(config):
        return "grok2api"
    return "disabled"


def normalize_video_generation_config(config: Any) -> dict[str, Any]:
    """Return a validated, JSON-safe copy of one OpenAI connection config."""
    if not isinstance(config, dict):
        raise ValueError("Each OpenAI API config must be an object.")

    normalized = dict(config)
    normalized["video_generation_compatibility"] = (
        resolve_video_generation_compatibility(config)
    )
    normalized["video_generation_model_ids"] = normalize_video_generation_model_ids(
        config.get("video_generation_model_ids", _MISSING)
    )
    return normalized


def _normalize_model_id(model_id: Any) -> str:
    if model_id is None:
        return ""
    return str(model_id).strip()


def is_video_generation_model_supported(
    model_id: Any,
    config: Optional[dict] = None,
) -> bool:
    """Return whether this connection explicitly supports the requested model."""
    api_config = config if isinstance(config, dict) else {}
    mode = resolve_video_generation_compatibility(api_config)
    configured_ids = normalize_video_generation_model_ids(
        api_config.get("video_generation_model_ids", _MISSING)
    )
    if mode != "grok2api":
        return False

    normalized_model_id = _normalize_model_id(model_id)
    if not normalized_model_id:
        return False

    return normalized_model_id in VIDEO_GENERATION_BUILTIN_MODEL_IDS or (
        normalized_model_id in configured_ids
    )


def resolve_video_generation_capability(
    model_id: Any,
    api_config: Optional[dict] = None,
) -> dict[str, Any]:
    """Return the stable, provider-neutral capability fields for one model."""
    supported = is_video_generation_model_supported(model_id, api_config)
    return {
        "video_generation_supported": supported,
        "video_generation_support": (
            deepcopy(_VIDEO_GENERATION_SUPPORT) if supported else None
        ),
    }


__all__ = [
    "VIDEO_GENERATION_ASPECT_RATIOS",
    "VIDEO_GENERATION_BUILTIN_MODEL_IDS",
    "VIDEO_GENERATION_COMPATIBILITY_MODES",
    "VIDEO_GENERATION_RESOLUTIONS",
    "is_video_generation_model_supported",
    "normalize_video_generation_config",
    "normalize_video_generation_model_ids",
    "resolve_video_generation_capability",
    "resolve_video_generation_compatibility",
]
