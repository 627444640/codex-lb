from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

import httpx
import test_assistant as helpers

from monitor.assistant import AssistantError
from monitor.assistant_schemas import ChatRequest, ChatResponse
from monitor.assistant_stream import DiffusionState, ModelSnapshot, SSEDecoder, answer_preview


def frame(text, finish=None):
    return (
        "data: "
        + json.dumps(
            {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": finish}]}, ensure_ascii=False
        )
        + "\r\n\r\n"
    ).encode()


def answer(text, source_id=2):
    return json.dumps({"answer": text, "source_ids": [source_id]}, ensure_ascii=False)


class PacketStream(httpx.AsyncByteStream):
    def __init__(self, packets):
        self.packets, self.closed = packets, False

    async def __aiter__(self):
        for packet in self.packets:
            yield packet

    async def aclose(self):
        self.closed = True


class DecoderTests(unittest.TestCase):
    def test_utf8_crlf_and_multiple_data_lines_across_byte_boundaries(self):
        raw = (
            ': comment\r\ndata: {"choices":\r\ndata: [{"index"'
            ':0,"delta":{"content":"中文"},"finish_reason":n'
            "ull}]}\r\n\r\n"
        ).encode()
        decoder = SSEDecoder()
        events = []
        for value in raw:
            events.extend(decoder.feed(bytes([value])))
        self.assertEqual(len(events), 1)
        self.assertEqual(json.loads(events[0])["choices"][0]["delta"]["content"], "中文")

    def test_partial_answer_never_exposes_schema_and_revisions_replace_text(self):
        self.assertEqual(answer_preview('{"answer":"第一版'), "第一版")
        self.assertEqual(answer_preview('{"answer":"换行\\n内容\\u4e'), "换行\n内容")
        self.assertEqual(answer_preview('{"source_ids":[2]'), "")
        state = DiffusionState()
        for text in (answer("旧稿很长"), answer("短稿")):
            event = json.loads(frame(text).decode().split("data: ", 1)[1])
            self.assertEqual(state.consume(json.dumps(event)), json.loads(text)["answer"])
        self.assertEqual(json.loads(state.text)["answer"], "短稿")

    def test_frame_and_total_budgets_are_bounded(self):
        with self.assertRaises(ValueError):
            SSEDecoder().feed(b"data: " + b"x" * 262144)
        decoder = SSEDecoder()
        with self.assertRaises(ValueError):
            for _ in range(1100):
                decoder.feed(b":" + b"x" * 4096 + b"\n\n")


class DiffusionTests(unittest.TestCase):
    setUp = helpers.AssistantTests.setUp
    configure = helpers.AssistantTests.configure
    ask = helpers.AssistantTests.ask

    def model_packets(self, packets):
        real_client = httpx.AsyncClient
        stream = PacketStream(packets)

        def handler(request):
            payload = json.loads(request.content)
            self.assertEqual(request.url.path, "/v1/chat/completions")
            self.assertTrue(payload["stream"] and payload["diffusing"])
            self.assertEqual(payload["response_format"]["type"], "json_schema")
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, stream=stream)

        return stream, patch(
            "monitor.assistant.httpx.AsyncClient",
            lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
        )

    def source_id(self):
        return next(
            g.id for g in self.app.state.guides.list(public=True) if g.slug == "error-websocket-payload-too-large"
        )

    def test_browser_stream_replaces_drafts_and_only_completes_after_valid_terminal(self):
        self.configure()
        source = self.source_id()
        content = (
            frame(answer("第一版会修改", source))
            + frame(answer("最终中文建议", source), "stop")
            + b"data: [DONE]\r\n\r\n"
        )
        stream, mock = self.model_packets([content[i : i + 7] for i in range(0, len(content), 7)])
        with mock:
            response = self.ask(stream=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/event-stream", response.headers["content-type"])
        events = [(p.splitlines()[0], json.loads(p.split("data: ", 1)[1])) for p in response.text.strip().split("\n\n")]
        self.assertEqual([e[0] for e in events], ["event: snapshot", "event: snapshot", "event: completed"])
        self.assertEqual(events[1][1], {"text": "最终中文建议"})
        self.assertNotIn("sources", events[0][1])
        self.assertEqual(events[-1][1]["answer"], "最终中文建议")
        self.assertEqual(len(events[-1][1]["sources"]), 1)
        self.assertTrue(stream.closed)
        self.assertEqual(self.app.state.assistant.active, 0)

    def test_bad_terminal_or_invalid_citations_discard_provisional_answer(self):
        self.configure()
        source = self.source_id()
        for suffix in (
            b"",
            frame(answer("截断", source), "length"),
            b"data: broken\n\n",
            frame(answer("伪来源", 999999), "stop") + b"data: [DONE]\n\n",
            b"data: [DONE]\n\n",
        ):
            stream, mock = self.model_packets([frame(answer("未完成草稿", source)), suffix])
            with mock:
                response = self.ask(stream=True)
            self.assertIn("event: error", response.text)
            self.assertNotIn("event: completed", response.text)
            self.assertNotIn("999999", response.text)
            self.assertTrue(stream.closed)
            self.assertEqual(self.app.state.assistant.active, 0)

    def test_closed_consumer_closes_upstream_and_releases_capacity(self):
        self.configure()
        source = self.source_id()
        stream, mock = self.model_packets(
            [frame(answer("待完成", source)), frame(answer("完成", source), "stop"), b"data: [DONE]\n\n"]
        )

        async def scenario():
            with mock:
                events = self.app.state.assistant.ask_stream(
                    ChatRequest(question="payload_too_large"), "synthetic-peer"
                )
                self.assertIsInstance(await anext(events), ModelSnapshot)
                self.assertEqual(self.app.state.assistant.active, 1)
                await events.aclose()
            self.assertTrue(stream.closed)
            self.assertEqual(self.app.state.assistant.active, 0)

        asyncio.run(scenario())

    def test_withdrawn_guide_after_snapshot_never_completes(self):
        self.configure()
        source = self.source_id()
        stream, mock = self.model_packets(
            [frame(answer("待确认", source)), frame(answer("已完成", source), "stop"), b"data: [DONE]\n\n"]
        )

        async def scenario():
            with mock:
                events = self.app.state.assistant.ask_stream(
                    ChatRequest(question="payload_too_large"), "synthetic-peer"
                )
                self.assertIsInstance(await anext(events), ModelSnapshot)
                row = self.app.state.guides.get(source)
                self.app.state.guides.set_deleted(row.id, row.revision)
                with self.assertRaises(AssistantError):
                    async for event in events:
                        self.assertNotIsInstance(event, ChatResponse)
            self.assertTrue(stream.closed)
            self.assertEqual(self.app.state.assistant.active, 0)

        asyncio.run(scenario())

    def test_empty_match_stream_completes_without_model_call(self):
        self.configure()
        response = self.ask("XYZZY_UNCOVERED_993", stream=True)
        self.assertIn("event: completed", response.text)
        self.assertNotIn("event: snapshot", response.text)
        self.assertEqual(self.app.state.assistant.used(), 0)

    def test_disabled_stream_reports_an_error_without_starting_model_work(self):
        response = self.ask(stream=True)
        self.assertIn("event: error", response.text)
        self.assertNotIn("event: completed", response.text)
        self.assertEqual(self.app.state.assistant.active, 0)
        self.assertEqual(self.app.state.assistant.used(), 0)

    def test_cancel_before_first_snapshot_closes_the_upstream(self):
        self.configure()
        real_client = httpx.AsyncClient

        async def scenario():
            started = asyncio.Event()

            class WaitingStream(httpx.AsyncByteStream):
                closed = False

                async def __aiter__(self):
                    started.set()
                    await asyncio.Event().wait()
                    yield b""

                async def aclose(self):
                    self.closed = True

            upstream = WaitingStream()

            def handler(request):
                return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, stream=upstream)

            with patch(
                "monitor.assistant.httpx.AsyncClient",
                lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
            ):
                stream = self.app.state.assistant.ask_stream(
                    ChatRequest(question="payload_too_large"), "synthetic-peer"
                )
                pending = asyncio.create_task(anext(stream))
                await asyncio.wait_for(started.wait(), timeout=5)
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
                await stream.aclose()
            self.assertTrue(upstream.closed)
            self.assertEqual(self.app.state.assistant.active, 0)

        asyncio.run(scenario())
