import asyncio
import json
import pathlib
import sys


# Ensure `open_webui` is importable when running tests from repo root.
_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from open_webui.utils.openai_responses import (
    RESPONSES_TRANSPORT_DONE_EVENT,
    ResponsesCompatibilityError,
    ResponsesProtocolError,
    collect_responses_response,
    convert_chat_completions_to_responses_payload,
    convert_responses_to_chat_completions,
    normalize_url_citations,
    iter_responses_events,
    resolve_responses_compatibility,
    responses_events_to_chat_completions_sse,
)

import pytest


async def _aiter(chunks):
    for c in chunks:
        yield c


async def _collect_async(gen):
    items = []
    async for x in gen:
        items.append(x)
    return items


def test_convert_chat_completions_to_responses_payload_basic():
    chat = {
        "model": "gpt-test",
        "stream": True,
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "Hi",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "do", "arguments": "{\"x\":1}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "{\"ok\":true}"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "do",
                    "description": "does things",
                    "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}},
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "do"}},
        "max_tokens": 123,
    }

    r = convert_chat_completions_to_responses_payload(chat, native_web_search_tool_type=None)
    assert r["model"] == "gpt-test"
    assert r["stream"] is True
    assert r["instructions"] == "You are helpful."
    assert r["max_output_tokens"] == 123
    assert isinstance(r["input"], list)

    # user message preserved
    assert any(
        i.get("type") == "message"
        and i.get("role") == "user"
        and isinstance(i.get("content"), list)
        and i["content"][0].get("type") == "input_text"
        and i["content"][0].get("text") == "Hello"
        for i in r["input"]
    )
    # assistant message preserved (assistant history must use output_* content types)
    assert any(
        i.get("type") == "message"
        and i.get("role") == "assistant"
        and isinstance(i.get("content"), list)
        and i["content"][0].get("type") == "output_text"
        and i["content"][0].get("text") == "Hi"
        for i in r["input"]
    )
    # tool output preserved
    assert any(i.get("type") == "function_call_output" and i.get("call_id") == "call_1" for i in r["input"])
    # tool call carried as input item
    assert any(i.get("type") == "function_call" and i.get("call_id") == "call_1" for i in r["input"])

    # tools converted to Responses function tool format
    assert r["tools"][0]["type"] == "function"
    assert r["tools"][0]["name"] == "do"
    assert "parameters" in r["tools"][0]

    # tool_choice converted
    assert r["tool_choice"] == {"type": "function", "name": "do"}


def test_convert_responses_to_chat_completions_basic():
    responses = {
        "id": "resp_1",
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "Hello"}]},
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    cc = convert_responses_to_chat_completions(responses, model_id="gpt-test")
    assert cc["id"] == "resp_1"
    assert cc["choices"][0]["message"]["content"] == "Hello"
    assert cc["usage"]["output_tokens"] == 1


def test_normalize_url_citations_supports_official_and_nested_shapes():
    citations = normalize_url_citations(
        [
            {
                "type": "url_citation",
                "url": "https://example.com/article",
                "title": "Example article",
                "start_index": 3,
                "end_index": 10,
            },
            {
                "type": "url_citation",
                "url_citation": {
                    "url": "https://example.com/article",
                    "title": "Example article",
                    "start_index": 20,
                    "end_index": 30,
                },
            },
            {"type": "url_citation", "title": "Missing URL"},
        ]
    )

    assert citations == [
        {
            "type": "url_citation",
            "url": "https://example.com/article",
            "title": "Example article",
            "start_index": 3,
            "end_index": 10,
        }
    ]


def test_convert_responses_to_chat_completions_preserves_url_citations_and_sources():
    responses = {
        "id": "resp_citation",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "A sourced answer",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://example.com/article",
                                "title": "Example article",
                            }
                        ],
                    }
                ],
            }
        ],
    }

    cc = convert_responses_to_chat_completions(responses, model_id="gpt-test")
    annotation = cc["choices"][0]["message"]["annotations"][0]

    assert annotation["type"] == "url_citation"
    assert annotation["url_citation"]["url"] == "https://example.com/article"
    assert cc["sources"][0]["source"]["name"] == "Example article"


def test_convert_chat_completions_to_responses_payload_injects_native_web_search_tool():
    chat = {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "Find the latest updates"}],
    }

    r = convert_chat_completions_to_responses_payload(
        chat,
        native_web_search_tool_type="web_search",
    )

    assert r["tools"] == [{"type": "web_search"}]
    assert r["tool_choice"] == "auto"


def test_responses_compatibility_defaults_to_current_web_search_tool():
    compatibility = resolve_responses_compatibility({})

    assert compatibility["mode"] == "standard"
    assert compatibility["native_web_search_tool_type"] == "web_search"


def test_responses_compatibility_preserves_explicit_preview_tool():
    compatibility = resolve_responses_compatibility(
        {"native_web_search_tool_type": "web_search_preview"}
    )

    assert compatibility["native_web_search_tool_type"] == "web_search_preview"


def test_responses_compatibility_rejects_invalid_mode():
    with pytest.raises(ResponsesCompatibilityError):
        resolve_responses_compatibility({"responses_compatibility": "typo"})

    with pytest.raises(ResponsesCompatibilityError):
        convert_chat_completions_to_responses_payload(
            {"model": "gpt-test", "messages": []},
            responses_compatibility="typo",
        )


def test_convert_chat_completions_to_responses_payload_forces_native_web_search_tool():
    chat = {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "Find the latest updates"}],
    }

    r = convert_chat_completions_to_responses_payload(
        chat,
        native_web_search_tool_type="web_search",
        native_web_search_required=True,
    )

    assert r["tools"] == [{"type": "web_search"}]
    assert r["tool_choice"] == {"type": "web_search"}


def test_sub2api_native_web_search_uses_compatible_required_tool_choice():
    chat = {
        "model": "gpt-5.6-luna",
        "messages": [{"role": "user", "content": "Search today's news"}],
        "max_tokens": 512,
    }

    r = convert_chat_completions_to_responses_payload(
        chat,
        native_web_search_tool_type="web_search",
        native_web_search_required=True,
        responses_compatibility="sub2api",
    )

    assert r["tools"] == [{"type": "web_search"}]
    assert r["tool_choice"] == "required"
    assert "max_output_tokens" not in r


def test_convert_chat_completions_to_responses_payload_strips_include_usage_stream_option():
    chat = {
        "model": "gpt-test",
        "stream": True,
        "stream_options": {"include_usage": True, "include_obfuscation": True},
        "messages": [{"role": "user", "content": "Hello"}],
    }

    r = convert_chat_completions_to_responses_payload(
        chat,
        native_web_search_tool_type=None,
    )

    assert r["stream"] is True
    assert r["stream_options"] == {"include_obfuscation": True}


def test_convert_chat_completions_to_responses_payload_enables_reasoning_summary():
    chat = {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "Think carefully"}],
        "reasoning_effort": "high",
    }

    r = convert_chat_completions_to_responses_payload(
        chat,
        native_web_search_tool_type=None,
        default_reasoning_summary="auto",
    )

    assert r["reasoning"] == {"effort": "high", "summary": "auto"}


def test_convert_chat_completions_to_responses_payload_preserves_input_files():
    chat = {
        "model": "gpt-test",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Read these files"},
                    {"type": "input_file", "file_id": "file_123"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
                    {"type": "file", "file_id": "file_456"},
                ],
            }
        ],
    }

    r = convert_chat_completions_to_responses_payload(
        chat,
        native_web_search_tool_type=None,
    )

    assert r["input"][0]["type"] == "message"
    content = r["input"][0]["content"]
    assert {"type": "input_text", "text": "Read these files"} in content
    assert {"type": "input_file", "file_id": "file_123"} in content
    assert {"type": "input_file", "file_id": "file_456"} in content
    assert {"type": "input_image", "image_url": "https://example.com/a.png"} in content


def test_iter_responses_events_sse_fragmented():
    event1 = json.dumps({"type": "response.output_text.delta", "delta": "Hi"})
    event2 = json.dumps({"type": "response.completed", "response": {"usage": {"output_tokens": 2}}})
    payload = (
        f"data: {event1}\n\n"
        f"data: {event2}\n\n"
        "data: [DONE]\n\n"
    ).encode("utf-8")

    # Fragment across chunks to ensure buffer stitching works.
    chunks = [payload[:10], payload[10:35], payload[35:]]

    async def run():
        evs = iter_responses_events(_aiter(chunks), content_type="text/event-stream")
        return await _collect_async(evs)

    events = asyncio.run(run())
    assert events[0]["type"] == "response.output_text.delta"
    assert events[1]["type"] == "response.completed"
    assert events[2]["type"] == RESPONSES_TRANSPORT_DONE_EVENT


def test_iter_responses_events_ndjson():
    line1 = json.dumps({"type": "response.output_text.delta", "delta": "A"}) + "\n"
    line2 = json.dumps({"type": "response.completed"}) + "\n"
    chunks = [(line1 + line2).encode("utf-8")]

    async def run():
        evs = iter_responses_events(_aiter(chunks), content_type="application/x-ndjson")
        return await _collect_async(evs)

    events = asyncio.run(run())
    assert [e["type"] for e in events] == ["response.output_text.delta", "response.completed"]


def test_responses_events_to_chat_sse_text_and_done():
    events = [
        {"type": "response.output_text.delta", "delta": "Hello"},
        {"type": "response.completed", "response": {"usage": {"output_tokens": 1}}},
    ]

    async def run():
        sse = responses_events_to_chat_completions_sse(_aiter(events), model_id="gpt-test")
        return await _collect_async(sse)

    lines = asyncio.run(run())
    assert any('"content": "Hello"' in line for line in lines)
    assert lines[-1].strip() == "data: [DONE]"


def test_responses_stream_raw_eof_is_an_error_not_a_success_finish():
    async def run():
        events = _aiter([{"type": "response.output_text.delta", "delta": "partial"}])
        return await _collect_async(
            responses_events_to_chat_completions_sse(events, model_id="gpt-test")
        )

    lines = asyncio.run(run())
    assert any("upstream_stream_incomplete" in line for line in lines)
    assert not any('"finish_reason": "stop"' in line for line in lines)
    assert lines[-1].strip() == "data: [DONE]"


def test_responses_transport_done_is_a_success_finish():
    events = [
        {"type": "response.output_text.delta", "delta": "complete"},
        {"type": RESPONSES_TRANSPORT_DONE_EVENT},
    ]

    async def run():
        return await _collect_async(
            responses_events_to_chat_completions_sse(_aiter(events), model_id="gpt-test")
        )

    lines = asyncio.run(run())
    assert any('"finish_reason": "stop"' in line for line in lines)
    assert not any("upstream_stream_incomplete" in line for line in lines)


def test_responses_error_events_are_normalized_without_success_finish():
    events = [
        {
            "type": "response.failed",
            "response": {
                "status": "failed",
                "error": {"message": "quota exhausted", "code": "quota"},
            },
        }
    ]

    async def run():
        return await _collect_async(
            responses_events_to_chat_completions_sse(_aiter(events), model_id="gpt-test")
        )

    lines = asyncio.run(run())
    assert any("quota exhausted" in line and '"code": "quota"' in line for line in lines)
    assert not any('"finish_reason": "stop"' in line for line in lines)


def test_mixed_text_and_tool_stream_finishes_with_tool_calls():
    events = [
        {"type": "response.output_text.delta", "delta": "I will call a tool."},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": "call_1",
                "name": "lookup",
                "arguments": "{}",
            },
        },
        {"type": "response.completed", "response": {"status": "completed"}},
    ]

    async def run():
        return await _collect_async(
            responses_events_to_chat_completions_sse(_aiter(events), model_id="gpt-test")
        )

    lines = asyncio.run(run())
    assert any('"finish_reason": "tool_calls"' in line for line in lines)


def test_collect_responses_stream_requires_terminal_event():
    async def run():
        return await collect_responses_response(
            _aiter([{"type": "response.output_text.done", "text": "partial"}])
        )

    with pytest.raises(ResponsesProtocolError) as exc:
        asyncio.run(run())
    assert exc.value.error["code"] == "upstream_stream_incomplete"


def test_collect_responses_stream_builds_response_on_transport_done():
    async def run():
        return await collect_responses_response(
            _aiter(
                [
                    {"type": "response.output_text.delta", "delta": "hello"},
                    {"type": RESPONSES_TRANSPORT_DONE_EVENT},
                ]
            )
        )

    response = asyncio.run(run())
    converted = convert_responses_to_chat_completions(response, model_id="gpt-test")
    assert converted["choices"][0]["message"]["content"] == "hello"


def test_collect_responses_merges_accumulated_events_into_minimal_terminal_response():
    async def run():
        return await collect_responses_response(
            _aiter(
                [
                    {"type": "response.output_text.delta", "delta": "hello"},
                    {
                        "type": "response.output_text.annotation.added",
                        "annotation": {
                            "type": "url_citation",
                            "url": "https://example.com/source",
                            "title": "Example source",
                        },
                    },
                    {
                        "type": "response.reasoning_text.delta",
                        "item_id": "reasoning-1",
                        "delta": "checked context",
                    },
                    {
                        "type": "response.function_call_arguments.delta",
                        "item_id": "call-1",
                        "delta": '{"q":"halo"}',
                    },
                    {
                        "type": "response.function_call_arguments.done",
                        "item_id": "call-1",
                        "name": "lookup",
                    },
                    {
                        "type": "response.completed",
                        "response": {
                            "status": "completed",
                            "usage": {"output_tokens": 2},
                        },
                    },
                ]
            )
        )

    converted = convert_responses_to_chat_completions(
        asyncio.run(run()), model_id="gpt-test"
    )
    choice = converted["choices"][0]
    assert choice["message"]["content"] == "hello"
    assert choice["message"]["reasoning_content"] == "checked context"
    assert choice["message"]["tool_calls"][0]["function"] == {
        "name": "lookup",
        "arguments": '{"q":"halo"}',
    }
    assert choice["finish_reason"] == "tool_calls"
    assert converted["sources"][0]["source"]["url"] == "https://example.com/source"


def test_collect_responses_does_not_duplicate_reasoning_done_after_deltas():
    async def run():
        return await collect_responses_response(
            _aiter(
                [
                    {
                        "type": "response.reasoning_summary_text.delta",
                        "item_id": "reasoning-1",
                        "output_index": 0,
                        "summary_index": 0,
                        "delta": "checked context",
                    },
                    {
                        "type": "response.reasoning_summary_text.done",
                        "item_id": "reasoning-1",
                        "output_index": 0,
                        "summary_index": 0,
                        "text": "checked context",
                    },
                    {
                        "type": "response.completed",
                        "response": {"status": "completed"},
                    },
                ]
            )
        )

    converted = convert_responses_to_chat_completions(
        asyncio.run(run()), model_id="gpt-test"
    )
    assert converted["choices"][0]["message"]["reasoning_content"] == (
        "checked context"
    )


def test_completed_response_output_is_emitted_when_stream_has_no_delta_events():
    events = [
        {
            "type": "response.completed",
            "response": {
                "id": "resp-final",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "final text"}],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call-final",
                        "name": "lookup",
                        "arguments": "{}",
                    },
                ],
            },
        }
    ]

    async def run():
        return await _collect_async(
            responses_events_to_chat_completions_sse(
                _aiter(events), model_id="gpt-test"
            )
        )

    lines = asyncio.run(run())
    assert any('"content": "final text"' in line for line in lines)
    assert any(
        '"name": "lookup"' in line and '"id": "call-final"' in line
        for line in lines
    )
    assert any('"finish_reason": "tool_calls"' in line for line in lines)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("failed", "upstream_error"),
        ("incomplete", "response_incomplete"),
        ("cancelled", "response_cancelled"),
        ("in_progress", "response_not_completed"),
    ],
)
def test_direct_responses_failure_statuses_are_rejected(status, code):
    payload = {"status": status, "error": {"message": "failed"}}
    if status != "failed":
        payload.pop("error")
    with pytest.raises(ResponsesProtocolError) as exc:
        convert_responses_to_chat_completions(payload, model_id="gpt-test")
    assert exc.value.error["code"] == code


def test_responses_events_to_chat_sse_emits_annotation_added_event_once():
    citation = {
        "type": "url_citation",
        "url": "https://example.com/article",
        "title": "Example article",
        "start_index": 0,
        "end_index": 5,
    }
    events = [
        {"type": "response.output_text.delta", "delta": "Hello"},
        {"type": "response.output_text.annotation.added", "annotation": citation},
        {"type": "response.output_text.annotation.added", "annotation": citation},
        {"type": "response.completed", "response": {"output": []}},
    ]

    async def run():
        sse = responses_events_to_chat_completions_sse(_aiter(events), model_id="gpt-test")
        return await _collect_async(sse)

    lines = asyncio.run(run())
    annotation_lines = [line for line in lines if '"annotations"' in line]

    assert len(annotation_lines) == 1
    assert '"url": "https://example.com/article"' in annotation_lines[0]


def test_responses_events_to_chat_sse_deduplicates_same_url_at_different_offsets():
    events = [
        {
            "type": "response.output_text.annotation.added",
            "annotation": {
                "type": "url_citation",
                "url": "https://example.com/article",
                "title": "Example article",
                "start_index": 0,
                "end_index": 5,
            },
        },
        {
            "type": "response.output_text.annotation.added",
            "annotation": {
                "type": "url_citation",
                "url": "https://example.com/article",
                "title": "Example article",
                "start_index": 10,
                "end_index": 15,
            },
        },
        {"type": "response.completed"},
    ]

    async def run():
        sse = responses_events_to_chat_completions_sse(_aiter(events), model_id="gpt-test")
        return await _collect_async(sse)

    lines = asyncio.run(run())
    annotation_lines = [line for line in lines if '"annotations"' in line]
    assert len(annotation_lines) == 1


def test_convert_responses_to_chat_completions_ignores_citations_without_url():
    responses = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "No source",
                        "annotations": [{"type": "url_citation", "title": "Missing URL"}],
                    }
                ],
            }
        ]
    }

    cc = convert_responses_to_chat_completions(responses, model_id="gpt-test")
    assert "annotations" not in cc["choices"][0]["message"]
    assert "sources" not in cc


def test_convert_responses_to_chat_completions_preserves_reasoning_summary():
    responses = {
        "id": "resp_1",
        "output": [
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "先检查上下文。"}],
            },
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "结论。"}],
            },
        ],
    }

    cc = convert_responses_to_chat_completions(responses, model_id="gpt-test")
    assert cc["choices"][0]["message"]["reasoning_content"] == "先检查上下文。"
    assert cc["choices"][0]["message"]["content"] == "结论。"


def test_responses_events_to_chat_sse_reasoning_summary_part_done():
    events = [
        {
            "type": "response.reasoning_summary_part.done",
            "item_id": "rs_1",
            "output_index": 0,
            "summary_index": 0,
            "part": {"type": "summary_text", "text": "先看输入，再回答。"},
        },
        {"type": "response.completed"},
    ]

    async def run():
        sse = responses_events_to_chat_completions_sse(_aiter(events), model_id="gpt-test")
        return await _collect_async(sse)

    lines = asyncio.run(run())
    assert any('"reasoning_content": "先看输入，再回答。"' in line for line in lines)


def test_responses_events_to_chat_sse_reasoning_text_delta():
    events = [
        {
            "type": "response.reasoning_text.delta",
            "item_id": "r_1",
            "output_index": 0,
            "content_index": 0,
            "delta": "正在推理",
        },
        {"type": "response.completed"},
    ]

    async def run():
        sse = responses_events_to_chat_completions_sse(_aiter(events), model_id="gpt-test")
        return await _collect_async(sse)

    lines = asyncio.run(run())
    assert any('"reasoning_content": "正在推理"' in line for line in lines)


def test_responses_events_to_chat_sse_tool_call_delta_and_name():
    events = [
        {"type": "response.function_call_arguments.delta", "item_id": "call_x", "delta": "{\"a\":"},
        {"type": "response.function_call_arguments.delta", "item_id": "call_x", "delta": "1}"},
        {"type": "response.function_call_arguments.done", "item_id": "call_x", "name": "do", "arguments": "{\"a\":1}"},
        {"type": "response.completed"},
    ]

    async def run():
        sse = responses_events_to_chat_completions_sse(_aiter(events), model_id="gpt-test")
        return await _collect_async(sse)

    lines = asyncio.run(run())
    # At least one chunk includes tool_calls.
    assert any('"tool_calls"' in line for line in lines)
    # Name should be emitted at least once.
    assert any('"name": "do"' in line for line in lines)
