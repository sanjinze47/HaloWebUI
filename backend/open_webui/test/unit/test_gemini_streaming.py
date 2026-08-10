import asyncio
import json
import pathlib
import sys


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.routers import gemini as gemini_router


def _decode_sse_chunk(chunk: str) -> dict:
    assert chunk.startswith("data: ")
    return json.loads(chunk[len("data: ") :].strip())


def test_split_sse_events_keeps_remainder_without_requeue():
    events, remainder = gemini_router._split_sse_events("data: {\n\nrest")

    assert events == ["data: {"]
    assert remainder == "rest"


def test_parse_gemini_json_objects_skips_invalid_event_and_summarizes_warnings(
    monkeypatch,
):
    warnings = []
    monkeypatch.setattr(
        gemini_router.log, "warning", lambda message: warnings.append(message)
    )

    limiter = gemini_router._StreamWarningLimiter("stream-1", per_key_limit=1)

    assert (
        gemini_router._parse_gemini_json_objects(
            "{", warning_limiter=limiter, phase="event"
        )
        == []
    )
    assert (
        gemini_router._parse_gemini_json_objects(
            "{", warning_limiter=limiter, phase="event"
        )
        == []
    )

    limiter.flush()

    assert "JSON decode error (event)" in warnings[0]
    assert "Suppressed 1 additional json_decode_event warnings" in warnings[1]


def test_parse_gemini_json_objects_skips_non_dict_values(monkeypatch):
    warnings = []
    monkeypatch.setattr(
        gemini_router.log, "warning", lambda message: warnings.append(message)
    )

    payload = (
        '"error" '
        '{"candidates":[{"content":{"parts":[{"text":"hello"}]}}],"usageMetadata":{"totalTokenCount":1}}'
    )

    objs = gemini_router._parse_gemini_json_objects(payload, phase="event")

    assert len(objs) == 1
    assert objs[0]["candidates"][0]["content"]["parts"][0]["text"] == "hello"
    assert any(
        "Skipping non-dict Gemini stream payload (str): error" in warning
        for warning in warnings
    )


def test_image_chunks_use_delta_image_protocol():
    chunks = list(
        gemini_router._yield_image_chunks(
            [{"mime_type": "image/png", "data": "abcdefgh"}],
            "stream-1",
            "gemini-test",
        )
    )

    decoded = [_decode_sse_chunk(chunk) for chunk in chunks]

    assert decoded[0]["choices"][0]["delta"]["image"]["id"].startswith("img_")
    assert decoded[-1]["choices"][0]["delta"]["image"]["final"] is True
    assert (
        "".join(chunk["choices"][0]["delta"]["image"]["data"] for chunk in decoded)
        == "abcdefgh"
    )


def test_build_stream_chunks_from_gemini_obj_emits_image_delta_and_finish():
    gemini_obj = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "caption"},
                        {"inlineData": {"mimeType": "image/png", "data": "abcd"}},
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 1,
            "candidatesTokenCount": 2,
            "totalTokenCount": 3,
        },
    }

    chunks, _next_index, finished = gemini_router._build_stream_chunks_from_gemini_obj(
        gemini_obj,
        "stream-1",
        "gemini-test",
        0,
        default_finish_reason="stop",
    )

    decoded = [_decode_sse_chunk(chunk) for chunk in chunks]

    assert decoded[0]["choices"][0]["delta"]["content"] == "caption"
    assert decoded[1]["choices"][0]["delta"]["image"]["data"] == "abcd"
    assert decoded[-1]["choices"][0]["finish_reason"] == "stop"
    assert decoded[-1]["usage"]["total_tokens"] == 3
    assert finished is True


def test_extract_content_segments_skips_thought_inline_images():
    candidate = {
        "content": {
            "parts": [
                {"text": "internal", "thought": True},
                {
                    "inlineData": {"mimeType": "image/png", "data": "thought-image"},
                    "thought": True,
                },
                {"inlineData": {"mimeType": "image/png", "data": "final-image"}},
            ]
        }
    }

    text, images, grounding_md, thinking_content, tool_calls, next_index = (
        gemini_router._extract_content_segments(candidate)
    )

    assert text == ""
    assert images == [{"mime_type": "image/png", "data": "final-image"}]
    assert grounding_md == ""
    assert thinking_content == "internal"
    assert tool_calls == []
    assert next_index == 0


def test_build_stream_chunks_ignore_thought_inline_images():
    gemini_obj = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": "thought-image",
                            },
                            "thought": True,
                        },
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": "final-image",
                            }
                        },
                    ]
                }
            }
        ],
        "usageMetadata": {"totalTokenCount": 1},
    }

    chunks, _next_index, finished = gemini_router._build_stream_chunks_from_gemini_obj(
        gemini_obj,
        "stream-1",
        "gemini-test",
        0,
        default_finish_reason="stop",
    )

    decoded = [_decode_sse_chunk(chunk) for chunk in chunks]
    image_chunks = [
        chunk for chunk in decoded if chunk["choices"][0]["delta"].get("image")
    ]

    assert len(image_chunks) == 1
    assert image_chunks[0]["choices"][0]["delta"]["image"]["data"] == "final-image"
    assert finished is True


def test_image_compat_payloads_keep_response_modalities():
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "draw a cat"}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "thinkingConfig": {"thinkingBudget": 1024},
        },
        "tools": [{"googleSearch": {}}],
    }

    compat_payload = gemini_router._build_compat_payload(
        payload,
        drop_tools=True,
        drop_thinking=True,
        drop_response_modalities=False,
    )

    assert compat_payload.get("generationConfig", {}).get("responseModalities") == [
        "TEXT",
        "IMAGE",
    ]


class _CompatResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body
        self.release_count = 0

    async def text(self):
        return json.dumps(self._body)

    def release(self):
        self.release_count += 1


class _CompatSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.payloads = []

    async def post(self, url, json=None, headers=None):
        self.payloads.append(json)
        return self.responses.pop(0)


def test_gemini_auto_retries_only_the_rejected_optional_capability():
    first = _CompatResponse(
        400,
        {"error": {"message": "thinkingConfig is not supported by this model"}},
    )
    second = _CompatResponse(200, {})
    session = _CompatSession([first, second])
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
        "tools": [{"googleSearch": {}}],
        "generationConfig": {
            "thinkingConfig": {"thinkingBudget": 1024},
            "temperature": 0.2,
        },
    }

    response, used_payload, status, _error = asyncio.run(
        gemini_router._open_gemini_response(
            session,
            [("https://example.test/generateContent", {})],
            payload,
            log_prefix="test",
            compatibility_mode="auto",
        )
    )

    assert response is second
    assert status == 200
    assert len(session.payloads) == 2
    assert "thinkingConfig" not in used_payload["generationConfig"]
    assert used_payload["tools"] == payload["tools"]
    assert used_payload["generationConfig"]["temperature"] == 0.2
    assert first.release_count == 1


def test_gemini_strict_and_required_capabilities_do_not_retry():
    error_body = {"error": {"message": "thinkingConfig is not supported by this model"}}

    for mode, required in (("strict", set()), ("auto", {"thinking"})):
        first = _CompatResponse(400, error_body)
        session = _CompatSession([first])
        response, used_payload, status, _error = asyncio.run(
            gemini_router._open_gemini_response(
                session,
                [("https://example.test/generateContent", {})],
                {
                    "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
                    "generationConfig": {"thinkingConfig": {"thinkingBudget": 1024}},
                },
                log_prefix="test",
                compatibility_mode=mode,
                required_capabilities=required,
            )
        )

        assert response is None
        assert used_payload is None
        assert status == 400
        assert len(session.payloads) == 1
        assert first.release_count == 1
