# LLM routing and context budgets

The user selects `low`, `medium`, or `high`. The HTTP API normalizes case/whitespace,
uses medium for null/empty input, and rejects unknown values with HTTP 422.

| Level | Default model | Retrieval top-k | Document character ceiling | Output ceiling |
| --- | --- | ---: | ---: | ---: |
| low | Qwen3.5-2B_Q4_k_m | 3 | 6000 | 900 |
| medium | Qwen3.5-4B-M-TS-Q4_K_M | 5 | 16000 | 1600 |
| high | Qwen3.5-4B-M-TS-Q4_K_M | 10 | 24000 | 2400 |

The selection applies to RAG, generated FAQ answers and procurement models.
Supervisor intent classification uses the dedicated `ROUTER_MODEL`. Exact FAQ
matches and fixed fallback responses do not require generation. High uses the
same default 4B model as medium; it does not turn on thinking or increase the
serving context window.

Explicit retrieval budgets survive query analysis and reranking. The number of
usable results can still be smaller because of source availability, permissions,
reranker filtering, deduplication and prompt limits. Query-only callers that omit
top_k still use dynamic query analysis.

With `ENABLE_ROUTER_SMART_ESCALATION`, low escalates to medium if the cleaned
candidate context exceeds low's character budget or has more than six documents.
This decision is made before truncation, and the generator then uses medium's
context/output settings. It does not perform another retrieval.

RAG reserves the generated answer plus `LLM_CONTEXT_SAFETY_TOKENS` from
`LLM_CONTEXT_WINDOW`. When dynamic output budgeting is enabled, the reservation
is the larger of the procedure-step estimate and half the level's output ceiling,
capped at that ceiling. With dynamic budgeting disabled the full ceiling is used.

The current llama.cpp server supports `/apply-template` and `/tokenize`, which
count the actual rendered chat prompt including history and delimiters. `/v1/models`
can further lower the configured window using the serving `meta.n_ctx`; training
context metadata is never used. `LLM_CONTEXT_WINDOW` must match the deployed model
server (default 8192). These endpoints use the same base URL/API credential as
completion requests. Tokenizer requests time out at `LLM_TOKENIZER_TIMEOUT` seconds.

If native token counting is unavailable, a conservative UTF-8 byte bound plus
message overhead is used. This may reject a long fixed prompt rather than send an
oversized completion. Do not configure a larger window than the server actually
supports. No model server settings are changed by the application.

When needed, only retrieved context and oldest history are reduced; the current
question and grounding instructions are preserved. Partial document chunks are
marked, and citations refer only to retained chunks. An oversized fixed prompt is
handled without making a completion request. RAG `chat_ended.routing_metadata`
reports requested/effective levels, prompt/output token budgets, serving window
and whether the context was reduced.

Follow-up queries retain the conversation history and use the supervisor's
self-contained query for retrieval. Manual/instruction continuations are kept
separate from navigation of actual procurement records. The classifier validates
confidence within [0,1] and checks out-of-domain FAQ scope. These checks reduce
known errors; classifier output still requires evaluation on representative data.

Regression tests (no live database writes):

```sh
rtk proxy env BV_RUN_SQLSERVER_TESTS=0 .venv/bin/python -B -m unittest discover -s tests -v
```

`tests/test_llm_router.py` covers HTTP/SSE through the compiled orchestration/RAG
graphs with external I/O mocked, model propagation, follow-ups, context counting,
escalation, exact retrieval budgets, validation, and prompt/JSON fallbacks.
