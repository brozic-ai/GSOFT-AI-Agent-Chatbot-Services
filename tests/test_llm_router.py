"""Router regressions: isolated I/O; never executes business tools or writes DB."""

import importlib
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

from app.ai.agent.supervisor.schemas import RouterOutput
from app.ai.orchestration.router import route_after_classification
from app.ai.rag.context.builder import RagContextBuilder
from app.ai.rag.retrieval.query_analyzer import determine_dynamic_top_k
from app.ai.rag.retrieval.retriever import VectorRetriever
from app.core.config import settings
from app.llmops.factory import get_model_for_level
from app.llmops.token_budget import (
    PromptBudgetError,
    PromptTokenCounter,
    prepare_rag_prompt,
)
from app.modules.chat.api.v1.endpoints import router
from app.modules.chat.api.v1.schemas import ChatRequest
from app.routers.dependencies import get_chat_service

classifier = importlib.import_module("app.ai.agent.supervisor.nodes.classify")
generator = importlib.import_module("app.ai.agent.agentic_rag.nodes.generator_node")
retrieve = importlib.import_module("app.ai.agent.agentic_rag.nodes.retrieve_node")
adapters = importlib.import_module("app.ai.orchestration.nodes.agent_adapters")
faq = importlib.import_module("app.ai.agent.faq.nodes.faq_node")
registry = importlib.import_module("app.ai.agent.supervisor.prompts.registry")


def route(intent="rag", confidence=0.9, query="Hướng dẫn tạo tờ trình"):
    return RouterOutput(
        reasoning="test", intent=intent, query=query, confidence=confidence
    )


def fixture_docs(n=10, length=1000):
    return [
        f"Bước {i + 1}: Hồ sơ số {i}. "
        + ("Kiểm tra chứng từ nghiệp vụ. " * length)[:length]
        for i in range(n)
    ], [{"source": f"file-{i}.txt", "page": i + 1} for i in range(n)]


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1/ai/chat")
        self.service = MagicMock()

        async def stream(**kwargs):
            yield "event: chat_ended\ndata: {}\n\n"

        self.service.generate_rag_response_stream.side_effect = stream
        self.app.dependency_overrides[get_chat_service] = lambda: self.service
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_chat_sse_accepts_all_levels_without_edit_flag(self):
        for level in ("low", "medium", "high"):
            with self.subTest(level=level):
                response = self.client.post(
                    "/api/v1/ai/chat/stream",
                    json={"message": "test", "model_level": level},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("chat_ended", response.text)
                args = self.service.generate_rag_response_stream.call_args.kwargs
                self.assertEqual(args["model_level"], level)
                self.assertIsNone(args["edit_message_id"])

    def test_edit_id_is_forwarded(self):
        response = self.client.post(
            "/api/v1/ai/chat/stream",
            json={"message": "test", "is_edit": True, "edit_message_id": 42},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.service.generate_rag_response_stream.call_args.kwargs[
                "edit_message_id"
            ],
            42,
        )

    def test_normalizes_levels(self):
        for value, expected in [
            (None, "medium"),
            ("", "medium"),
            (" HIGH ", "high"),
            ("LOW", "low"),
        ]:
            self.assertEqual(ChatRequest(model_level=value).model_level, expected)

    def test_rejects_invalid_levels_before_service(self):
        for value in ["bogus", "max", 1, [], {}]:
            with self.subTest(value=value):
                response = self.client.post(
                    "/api/v1/ai/chat/stream",
                    json={"message": "test", "model_level": value},
                )
                self.assertEqual(response.status_code, 422)
        self.service.generate_rag_response_stream.assert_not_called()

    def test_factory_uses_configured_models_and_rejects_unknown(self):
        for level in ["low", "medium", "high"]:
            self.assertEqual(
                get_model_for_level(level, enable_fallback=False).model_name,
                getattr(settings, f"MODEL_LEVEL_{level.upper()}_MODEL"),
            )
        with self.assertRaises(ValueError):
            get_model_for_level("bogus")


class ClassifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_instruction_followups_never_trigger_procurement(self):
        for query, previous in [
            (
                "Tiếp tục hướng dẫn các bước còn lại",
                "Hướng dẫn sử dụng gAMSPro: Bước 1 tạo tờ trình.",
            ),
            (
                "Liệt kê tất cả các bước còn lại trong tài liệu",
                "Quy trình phê duyệt tờ trình có 8 bước.",
            ),
            (
                "Có hướng dẫn chi tiết hơn không?",
                "Quy trình tạo tờ trình trên gAMSPro gồm 5 bước.",
            ),
            (
                "Tiếp tục giải thích định dạng báo cáo",
                "Tài liệu hướng dẫn export báo cáo ra Excel.",
            ),
            (
                "Bước tiếp theo là gì?",
                "Hướng dẫn tạo tờ trình trên gAMSPro: Bước 1 đăng nhập.",
            ),
        ]:
            with (
                self.subTest(query=query),
                patch.object(classifier, "get_router_model") as model,
            ):
                result = await classifier.classify_intent_node(
                    {
                        "user_query": query,
                        "chat_history": [{"role": "assistant", "content": previous}],
                    }
                )
                self.assertEqual(result["intent"], "rag")
                model.assert_not_called()
                self.assertIn(previous, result["route"].query)

    async def test_actual_record_followups_stay_procurement(self):
        for query in ["Xem tiếp trang 2", "Còn nữa không?", "Tiếp tục"]:
            result = await classifier.classify_intent_node(
                {
                    "user_query": query,
                    "chat_history": [
                        {
                            "role": "assistant",
                            "content": "Danh sách tờ trình PUR/2026/000097.",
                        }
                    ],
                }
            )
            self.assertEqual(result["intent"], "procurement")

    async def test_new_request_does_not_inherit_previous_manual(self):
        llm = MagicMock()
        llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=route("procurement")
        )
        with (
            patch.object(classifier, "get_router_model", return_value=llm),
            patch.object(classifier, "get_supervisor_messages", return_value=[]),
        ):
            result = await classifier.classify_intent_node(
                {
                    "user_query": "Tạo tờ trình mua 5 máy tính",
                    "chat_history": [
                        {"role": "assistant", "content": "Hướng dẫn tạo tờ trình."}
                    ],
                }
            )
            self.assertEqual(result["intent"], "procurement")
            llm.with_structured_output.return_value.ainvoke.assert_awaited_once()

    async def test_continue_new_action_does_not_inherit_manual_intent(self):
        llm = MagicMock()
        llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=route("procurement")
        )
        with (
            patch.object(classifier, "get_router_model", return_value=llm),
            patch.object(classifier, "get_supervisor_messages", return_value=[]),
        ):
            result = await classifier.classify_intent_node(
                {
                    "user_query": "Tiếp tục tạo tờ trình mới cho tôi",
                    "chat_history": [
                        {"role": "assistant", "content": "Hướng dẫn tạo tờ trình."}
                    ],
                }
            )
        self.assertEqual(result["intent"], "procurement")
        llm.with_structured_output.return_value.ainvoke.assert_awaited_once()

    async def test_export_alone_is_not_procurement_evidence(self):
        llm = MagicMock()
        llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=route("fallback")
        )
        with (
            patch.object(classifier, "get_router_model", return_value=llm),
            patch.object(classifier, "get_supervisor_messages", return_value=[]),
        ):
            result = await classifier.classify_intent_node(
                {
                    "user_query": "Tiếp tục",
                    "chat_history": [
                        {"role": "assistant", "content": "Export completed."}
                    ],
                }
            )
            self.assertEqual(result["intent"], "fallback")
            llm.with_structured_output.return_value.ainvoke.assert_awaited_once()

    async def test_json_fallback_covers_setup_and_invoke(self):
        for phase in ["setup", "invoke"]:
            with self.subTest(phase=phase):
                llm = MagicMock()
                llm.ainvoke = AsyncMock(
                    return_value=AIMessage(
                        content="```json\n" + route().model_dump_json() + "\n```"
                    )
                )
                if phase == "setup":
                    llm.with_structured_output.side_effect = NotImplementedError(
                        "unsupported"
                    )
                else:
                    llm.with_structured_output.return_value.ainvoke = AsyncMock(
                        side_effect=ValueError("parse")
                    )
                with (
                    patch.object(classifier, "get_router_model", return_value=llm),
                    patch.object(
                        classifier, "get_supervisor_messages", return_value=[]
                    ),
                ):
                    result = await classifier.classify_intent_node(
                        {"user_query": "test", "chat_history": []}
                    )
                self.assertEqual(result["intent"], "rag")
                llm.ainvoke.assert_awaited_once()

    async def test_scope_flag_blocks_general_faq_but_keeps_company_faq(self):
        for query, expected in [
            ("Thủ đô của Pháp là gì?", "fallback"),
            ("Giờ làm việc công ty?", "faq"),
        ]:
            result = route("faq").model_copy(update={"in_scope": False})
            llm = MagicMock()
            llm.with_structured_output.return_value.ainvoke = AsyncMock(
                return_value=result
            )
            with (
                patch.object(classifier, "get_router_model", return_value=llm),
                patch.object(classifier, "get_supervisor_messages", return_value=[]),
            ):
                actual = await classifier.classify_intent_node(
                    {"user_query": query, "chat_history": []}
                )
            self.assertEqual(actual["intent"], expected)

    def test_confidence_validation_and_dict_equivalence(self):
        for invalid in [-1, 1.5, float("nan"), float("inf")]:
            with self.assertRaises(ValidationError):
                route(confidence=invalid)
            self.assertEqual(
                route_after_classification(
                    {"route": {"intent": "rag", "confidence": invalid}}
                ),
                "fallback_agent",
            )
        for confidence, expected in [
            (0, "fallback_agent"),
            (0.49, "fallback_agent"),
            (0.5, "rag_agent"),
            (1, "rag_agent"),
        ]:
            obj = route(confidence=confidence)
            for value in [obj, obj.model_dump()]:
                self.assertEqual(route_after_classification({"route": value}), expected)
        self.assertEqual(
            route_after_classification(
                {"route": {"intent": "not_rag", "confidence": 1}}
            ),
            "fallback_agent",
        )

    def test_local_prompt_fallback_keeps_history_and_scope(self):
        with patch.object(registry, "get_langfuse_client", return_value=None):
            messages = registry.get_supervisor_messages(
                "Còn nữa không?",
                [{"role": "assistant", "content": "UNIQUE_HISTORY PUR/2026/000097"}],
            )
        text = "\n".join(str(m.content) for m in messages)
        self.assertIn("UNIQUE_HISTORY", text)
        self.assertIn("general knowledge", text.lower())
        self.assertEqual(sum(isinstance(m, SystemMessage) for m in messages), 1)

    def test_system_only_remote_prompt_keeps_history(self):
        prompt = MagicMock()
        prompt.compile.return_value = [{"role": "system", "content": "Classify"}]
        client = MagicMock()
        client.get_prompt.return_value = prompt
        with patch.object(registry, "get_langfuse_client", return_value=client):
            messages = registry.get_supervisor_messages(
                "Còn nữa không?", [{"role": "assistant", "content": "UNIQUE_HISTORY"}]
            )
        self.assertIn("UNIQUE_HISTORY", str(messages[-1].content))


class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_budgets_survive_query_analysis_and_reranking(self):
        for query in [
            "Hướng dẫn phê duyệt",
            "Hạn mức tối đa bao nhiêu tiền?",
            "Liệt kê tất cả các bước phê duyệt",
        ]:
            candidate_counts = []
            for k in [3, 5, 10]:
                with self.subTest(query=query, k=k):
                    repo, embedding, ranker = MagicMock(), MagicMock(), MagicMock()
                    docs, citations = fixture_docs(30, 50)
                    repo.search_vector_chunks.return_value = {
                        "ids": [list(range(30))],
                        "documents": [docs],
                        "metadatas": [citations],
                        "citations": [citations],
                        "distances": [[0.1] * 30],
                    }
                    embedding.embed_query_cached = AsyncMock(
                        return_value=([0.0], False)
                    )
                    ranker.rerank_with_scores.side_effect = lambda q, d, top: [
                        (i, 0.9) for i in range(top)
                    ]
                    result = await VectorRetriever(
                        repo, embedding, ranker
                    ).retrieve_context(
                        query, top_k=k, user_roles="Audit", user_department="Test"
                    )
                    self.assertEqual(len(result["documents"][0]), k)
                    self.assertEqual(ranker.rerank_with_scores.call_args.args[2], k)
                    self.assertEqual(
                        repo.search_vector_chunks.call_args.kwargs["user_roles"],
                        "Audit",
                    )
                    self.assertEqual(
                        repo.search_vector_chunks.call_args.kwargs["user_department"],
                        "Test",
                    )
                    candidate_counts.append(
                        repo.search_vector_chunks.call_args.kwargs["top_k"]
                    )
            self.assertEqual(candidate_counts, sorted(candidate_counts))

    def test_omitting_budget_retains_dynamic_query_analysis(self):
        self.assertGreater(determine_dynamic_top_k("Liệt kê tất cả các bước")[0], 5)
        self.assertEqual(
            determine_dynamic_top_k("Liệt kê tất cả các bước", requested_top_k=5)[0], 5
        )


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_template_count_and_serving_window(self):
        requests = []

        def handle(request):
            requests.append(request)
            if request.url.path == "/v1/models":
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "id": settings.MODEL_LEVEL_HIGH_MODEL,
                                "meta": {"n_ctx": 4096, "n_ctx_train": 262144},
                            }
                        ]
                    },
                )
            if request.url.path == "/apply-template":
                return httpx.Response(200, json={"prompt": "rendered-template"})
            return httpx.Response(200, json={"tokens": [1, 2, 3, 4]})

        client = httpx.AsyncClient(
            base_url="http://test", transport=httpx.MockTransport(handle)
        )
        with patch("app.llmops.token_budget.httpx.AsyncClient", return_value=client):
            async with PromptTokenCounter("high") as counter:
                count = await counter.count(
                    [SystemMessage(content="test"), HumanMessage(content="xin chào")]
                )
                self.assertEqual(count, 4)
                self.assertEqual(counter.window, min(4096, settings.LLM_CONTEXT_WINDOW))
        payload = json.loads(requests[1].content)
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(payload["model"], settings.MODEL_LEVEL_HIGH_MODEL)
        self.assertTrue(json.loads(requests[2].content)["parse_special"])

    async def test_tokenizer_unavailable_uses_conservative_bound(self):
        client = httpx.AsyncClient(
            base_url="http://test",
            transport=httpx.MockTransport(lambda _: httpx.Response(404)),
        )
        counter = PromptTokenCounter("high")
        counter.client = client
        messages = [HumanMessage(content="Mã hồ sơ tiếng Việt 123456789")]
        self.assertGreaterEqual(
            await counter.count(messages), len(messages[0].content.encode("utf-8"))
        )
        self.assertFalse(counter.native)
        await client.aclose()

    async def test_full_prompt_history_and_output_fit_budget(self):
        docs, citations = fixture_docs(10, 3000)
        counter = MagicMock()
        counter.__aenter__ = AsyncMock(return_value=counter)
        counter.__aexit__ = AsyncMock(return_value=None)
        counter.window = 1400
        counter.count = AsyncMock(
            side_effect=lambda ms: sum(len(str(m.content)) for m in ms)
        )
        with patch("app.llmops.token_budget.PromptTokenCounter", return_value=counter):
            messages, used, metadata = await prepare_rag_prompt(
                level="high",
                system_prompt="Grounding instructions",
                query="Bước tiếp theo?",
                history=[
                    HumanMessage(content="Tạo hồ sơ"),
                    AIMessage(content="UNIQUE_HISTORY: Bước 1 đăng nhập"),
                    HumanMessage(content="Bước tiếp theo?"),
                ],
                documents=docs,
                citations=citations,
                max_chars=24000,
                max_tokens=300,
            )
        count = sum(len(str(m.content)) for m in messages)
        self.assertLessEqual(count + 300 + settings.LLM_CONTEXT_SAFETY_TOKENS, 1400)
        self.assertIn("UNIQUE_HISTORY", "\n".join(m.content for m in messages))
        self.assertTrue(used)
        self.assertEqual(used[0]["source"], "file-0.txt")
        self.assertTrue(metadata["context_truncated"])
        self.assertIn("lược bớt", messages[-1].content)

    async def test_oversized_fixed_prompt_fails_before_inference(self):
        counter = MagicMock()
        counter.__aenter__ = AsyncMock(return_value=counter)
        counter.__aexit__ = AsyncMock(return_value=None)
        counter.window = 1000
        counter.count = AsyncMock(return_value=2000)
        with (
            patch("app.llmops.token_budget.PromptTokenCounter", return_value=counter),
            self.assertRaises(PromptBudgetError),
        ):
            await prepare_rag_prompt(
                level="low",
                system_prompt="long",
                query="long",
                history=[],
                documents=["test"],
                citations=[{}],
                max_chars=6000,
                max_tokens=300,
            )

    def test_character_budget_keeps_partial_ranked_document_and_source(self):
        docs, citations = fixture_docs(3, 4900)
        context, metas, refs = RagContextBuilder.build(
            docs, citations, max_context_chars=6000
        )
        self.assertLessEqual(len(context), 6000)
        self.assertEqual(len(metas), 2)
        self.assertEqual([r["source"] for r in refs], ["file-0.txt", "file-1.txt"])
        self.assertIn("lược bớt", context)
        self.assertEqual(
            RagContextBuilder.build(docs, citations, max_context_chars=0), ("", [], [])
        )


class GraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_escalates_before_truncation_and_normalizes_low(self):
        docs, citations = fixture_docs(3, 4800)
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=AIMessage(content="OK"))
        prepare = AsyncMock(
            return_value=([HumanMessage(content="test")], citations, {})
        )
        for level in ["low", " LOW "]:
            with (
                self.subTest(level=level),
                patch.object(settings, "ENABLE_ROUTER_SMART_ESCALATION", True),
                patch.object(generator, "prepare_rag_prompt", prepare),
                patch.object(generator, "get_generator_prompt", return_value="test"),
                patch.object(
                    generator, "get_model_for_level", return_value=llm
                ) as factory,
            ):
                result = await generator.generator_node(
                    {
                        "documents": docs,
                        "citations": citations,
                        "model_level": level,
                        "user_query": "test",
                    }
                )
                self.assertEqual(factory.call_args.kwargs["level"], "medium")
                self.assertEqual(
                    prepare.call_args.kwargs["max_chars"],
                    settings.MODEL_LEVEL_MEDIUM_MAX_CHARS,
                )
                self.assertEqual(
                    result["routing_metadata"]["requested_model_level"], "low"
                )

    async def test_disable_escalation_and_empty_documents(self):
        docs, citations = fixture_docs(7, 1500)
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=AIMessage(content="OK"))
        with (
            patch.object(settings, "ENABLE_ROUTER_SMART_ESCALATION", False),
            patch.object(
                generator,
                "prepare_rag_prompt",
                AsyncMock(return_value=([HumanMessage(content="test")], citations, {})),
            ),
            patch.object(generator, "get_generator_prompt", return_value="test"),
            patch.object(generator, "get_model_for_level", return_value=llm) as factory,
        ):
            await generator.generator_node(
                {"documents": docs, "citations": citations, "model_level": "low"}
            )
            self.assertEqual(factory.call_args.kwargs["level"], "low")
            factory.reset_mock()
            await generator.generator_node({"documents": [], "model_level": "high"})
            factory.assert_not_called()

    async def test_adapter_graph_preserves_rewritten_query_level_history_and_citations(
        self,
    ):
        retriever = MagicMock()
        docs, citations = fixture_docs(1, 100)
        retriever.retrieve_context = AsyncMock(
            return_value={"documents": [docs], "citations": [citations]}
        )
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=AIMessage(content="Test answer"))
        prepared = AsyncMock(
            return_value=(
                [HumanMessage(content="test")],
                citations,
                {"effective_model_level": "high"},
            )
        )
        for level, k in [("low", 3), ("medium", 5), ("high", 10)]:
            with (
                self.subTest(level=level),
                patch.object(retrieve, "get_vector_retriever", return_value=retriever),
                patch.object(generator, "prepare_rag_prompt", prepared),
                patch.object(generator, "get_generator_prompt", return_value="test"),
                patch.object(
                    generator, "get_model_for_level", return_value=llm
                ) as factory,
            ):
                result = await adapters.call_rag_agent(
                    {
                        "model_level": level,
                        "user_query": "Bước tiếp theo?",
                        "route": route(
                            query="Bước tiếp theo trong quy trình tạo hồ sơ"
                        ),
                        "messages": [
                            HumanMessage(content="Tạo hồ sơ"),
                            AIMessage(content="UNIQUE_HISTORY"),
                            HumanMessage(content="Bước tiếp theo?"),
                        ],
                        "user_info": {"roles": "Audit", "department": "Test"},
                    }
                )
                self.assertEqual(
                    retriever.retrieve_context.call_args.kwargs["query"],
                    "Bước tiếp theo trong quy trình tạo hồ sơ",
                )
                self.assertEqual(
                    retriever.retrieve_context.call_args.kwargs["top_k"], k
                )
                self.assertEqual(factory.call_args.kwargs["level"], level)
                self.assertTrue(
                    any(
                        m.content == "UNIQUE_HISTORY"
                        for m in prepared.call_args.kwargs["history"]
                    )
                )
                self.assertEqual(result["citations"], citations)
                self.assertIn("routing_metadata", result)

    async def test_faq_generation_respects_selected_level(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=AIMessage(content="8h"))
        for level in ["low", "medium", "high"]:
            with (
                self.subTest(level=level),
                patch.object(faq, "get_system_prompt", return_value="test"),
                patch.object(faq, "get_model_for_level", return_value=llm) as factory,
            ):
                await faq.generate_faq_node(
                    {
                        "model_level": level,
                        "user_query": "Giờ làm",
                        "retrieved_faqs": [{"question": "Giờ làm", "answer": "8h"}],
                    }
                )
                self.assertEqual(factory.call_args.kwargs["level"], level)

    async def test_subgraph_adapters_forward_levels(self):
        for level in ["low", "medium", "high"]:
            state = {
                "model_level": level,
                "user_query": "test",
                "messages": [HumanMessage(content="test")],
            }
            with patch.object(
                adapters.faq_graph,
                "ainvoke",
                AsyncMock(return_value={"final_answer": "OK"}),
            ) as call:
                await adapters.call_faq_agent(state)
                self.assertEqual(call.call_args.args[0]["model_level"], level)
            with patch.object(
                adapters.procurement_graph,
                "ainvoke",
                AsyncMock(return_value={"messages": [AIMessage(content="OK")]}),
            ) as call:
                await adapters.call_procurement_agent(state)
                self.assertEqual(call.call_args.args[0]["model_level"], level)

    async def test_procurement_responder_respects_level_without_executing_tools(self):
        responder = importlib.import_module(
            "app.ai.agent.procurement.nodes.responder_node"
        )
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=AIMessage(content="Test answer"))
        for level in ["low", "medium", "high"]:
            with (
                patch.object(responder, "get_generator_messages", return_value=[]),
                patch.object(
                    responder, "get_model_for_level", return_value=llm
                ) as factory,
            ):
                await responder.responder_node(
                    {
                        "model_level": level,
                        "messages": [
                            HumanMessage(content="test"),
                            ToolMessage(content="synthetic", tool_call_id="1"),
                        ],
                    }
                )
                self.assertEqual(factory.call_args.kwargs["level"], level)


class HttpGraphIntegrationTests(unittest.TestCase):
    def test_http_to_compiled_orchestrator_and_rag_graph_all_levels(self):
        from contextlib import ExitStack

        from app.modules.chat.service import ChatService

        fast_lookup = importlib.import_module(
            "app.ai.orchestration.nodes.faq_fast_lookup_node"
        )
        repo = MagicMock()
        service = ChatService(MagicMock(), MagicMock(), repo)
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/ai/chat")
        app.dependency_overrides[get_chat_service] = lambda: service
        docs, citations = fixture_docs(1, 100)
        retriever = MagicMock()
        retriever.retrieve_context = AsyncMock(
            return_value={"documents": [docs], "citations": [citations]}
        )
        router_llm = MagicMock()
        router_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=route()
        )
        answer_llm = MagicMock()
        answer_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="Kết quả kiểm thử [1].")
        )
        counter = MagicMock()
        counter.__aenter__ = AsyncMock(return_value=counter)
        counter.__aexit__ = AsyncMock(return_value=None)
        counter.window = 8192
        counter.count = AsyncMock(
            side_effect=lambda ms: sum(len(str(m.content)) for m in ms)
        )
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    fast_lookup, "find_fast_faq_match", AsyncMock(return_value=None)
                )
            )
            stack.enter_context(
                patch.object(classifier, "get_router_model", return_value=router_llm)
            )
            stack.enter_context(
                patch.object(classifier, "get_supervisor_messages", return_value=[])
            )
            stack.enter_context(
                patch.object(retrieve, "get_vector_retriever", return_value=retriever)
            )
            stack.enter_context(
                patch.object(
                    generator,
                    "get_generator_prompt",
                    return_value="Answer from documents",
                )
            )
            factory = stack.enter_context(
                patch.object(generator, "get_model_for_level", return_value=answer_llm)
            )
            stack.enter_context(
                patch(
                    "app.llmops.token_budget.PromptTokenCounter", return_value=counter
                )
            )
            stack.enter_context(
                patch(
                    "app.llmops.langfuse.get_langfuse_langchain_config", return_value={}
                )
            )
            stack.enter_context(
                patch("app.modules.chat.service.asyncio.sleep", AsyncMock())
            )
            client = stack.enter_context(TestClient(app))
            for level, k in [("low", 3), ("medium", 5), ("high", 10)]:
                with self.subTest(level=level):
                    response = client.post(
                        "/api/v1/ai/chat/stream",
                        json={
                            "message": "Hướng dẫn tạo tờ trình",
                            "model_level": level,
                        },
                    )
                    self.assertEqual(response.status_code, 200)
                    events = response.text.split("\n\n")
                    ended = next(
                        json.loads(e.split("data: ", 1)[1])
                        for e in events
                        if e.startswith("event: chat_ended")
                    )
                    self.assertEqual(
                        ended["routing_metadata"]["effective_model_level"], level
                    )
                    self.assertIn("file-0.txt", response.text)
                    self.assertEqual(factory.call_args.kwargs["level"], level)
                    self.assertEqual(
                        retriever.retrieve_context.call_args.kwargs["top_k"], k
                    )
            repo.save_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
