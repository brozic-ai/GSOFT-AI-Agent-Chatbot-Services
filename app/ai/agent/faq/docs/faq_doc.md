# Báo Cáo Triển Khai FAQ Agent (LangGraph & Hybrid Search RRF)

Tài liệu này tổng hợp toàn bộ cấu trúc kiến trúc, quy trình xử lý và mã nguồn đã hoàn thiện cho **FAQ Agent** trong hệ thống Multi-Agent AI Services (`GSOFT-AI-Agent-Chatbot-Services`).

---

## 📐 1. Cấu Trúc Thư Mục FAQ Agent

Module FAQ Agent được xây dựng chuẩn kiến trúc LangGraph ReAct Agent:

```text
app/ai/agent/faq/
├── __init__.py               # Export faq_graph, FAQState, faq_node
├── state.py                  # Định nghĩa FAQState (kế thừa MessagesState)
├── docs/
│   └── walkthrough.md        # Tài liệu hướng dẫn & tổng kết chi tiết
├── tools/
│   ├── __init__.py           # Export FAQ_TOOLS
│   └── search.py             # Tool @search_faq_knowledge_base (Hybrid RRF Search)
├── nodes/
│   ├── __init__.py           # Export faq_agent_node
│   └── faq_node.py           # Node suy luận chính của LLM
├── prompts/
│   ├── registry.py           # Quản lý load Prompt
│   └── v1/
│       └── system.md         # System Prompt chỉ thị LLM & kịch bản Fallback
└── graph/
    ├── __init__.py           # Export faq_graph
    └── graph.py              # Đồ thị StateGraph độc lập của FAQ Agent
```

---

## 🔍 2. Thuật Toán Tìm Kiếm Hybrid Search RRF cho FAQ

File: [repository.py](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/modules/faq_knowledge/repository.py)

Hàm `search_faq_hybrid(query_embedding, query, top_k, rrf_min_score)` thực hiện tìm kiếm kết hợp trên bảng `dbo.FaqVectors`:

1. **Dense Vector Search**:
   - Sử dụng `VECTOR_DISTANCE('cosine', embedding, query_embedding)` trên SQL Server 2025.
2. **Sparse Full-Text Search (FTS)**:
   - Sử dụng `CONTAINSTABLE(dbo.FaqVectors, (question, answer), query_str)` qua chỉ mục `FtCatalog_FaqVectors`.
3. **Công thức hợp nhất RRF (Reciprocal Rank Fusion)**:
   $$\text{RRF\_Score} = \alpha \cdot \frac{1}{k + \text{vector\_rank}} + \beta \cdot \frac{1}{k + \text{fts\_rank\_pos}}$$
   *Với $\alpha = 0.6, \beta = 0.4, k = 60$.*
4. **Cơ chế Lọc Ngưỡng Fallback**:
   - Tất cả các kết quả có $\text{RRF\_Score} < 0.012$ sẽ tự động bị loại bỏ (filter out).
   - Nếu không còn kết quả nào $\rightarrow$ Tool trả về `"found": false` để kích hoạt kịch bản Fallback của Agent.

---

## 🛠️ 3. Công Cụ (Tool) & State Management

### State Management (`state.py`)
File: [state.py](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/ai/agent/faq/state.py)
```python
class FAQState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages] # Quản lý lịch sử hội thoại
    user_query: str                                      # Câu hỏi gốc từ user
    session_id: str                                      # ID phiên làm việc
    retrieved_faqs: list[dict]                           # Kết quả FAQ tra cứu được
    final_answer: str                                    # Câu trả lời cuối cùng
```

### FAQ Search Tool (`tools/search.py`)
File: [search.py](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/ai/agent/faq/tools/search.py)
- Tên tool: `search_faq_knowledge_base`
- Đóng gói logic gọi `TeiEmbeddingService.embed_query_cached()` và `FaqRepository.search_faq_hybrid()`.
- Trả về dạng JSON chuẩn hóa (`found`, `faqs`, `message`).

---

## 🤖 4. Node & Kịch Bản Fallback Nội Bộ

File: [faq_node.py](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/ai/agent/faq/nodes/faq_node.py)

- Node `faq_agent_node` nạp System Prompt từ [system.md](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/ai/agent/faq/prompts/v1/system.md) và bind `FAQ_TOOLS` vào mô hình LLM.
- **Kịch bản Fallback**:
  - Khi tool trả về `"found": false`, System Prompt ép buộc LLM không được tự ý suy đoán hay bịa câu trả lời, mà phải chủ động chuyển hướng câu trả lời thân thiện:
    > ℹ️ Hiện tại tôi chưa tìm thấy thông tin liên quan đến câu hỏi của bạn trong cơ sở dữ liệu FAQ nội bộ. Bạn vui lòng liên hệ **Bộ phận Hỗ trợ Nội bộ BVBank** hoặc gửi yêu cầu qua hệ thống eOffice để được giải đáp chi tiết nhé! 😊

---

## 🔄 5. Đồ Thị Trạng Thái (LangGraph ReAct Pattern)

File: [graph.py](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/ai/agent/faq/graph/graph.py)

Đồ thị ReAct 2-node hoàn chỉnh:

```text
               ┌───────────────────────┐
               │    Entry Point        │
               └───────────┬───────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │    faq_agent_node     │ ◄─────────────────────────┐
               └───────────┬───────────┘                           │
                           │                                       │
                Có gọi tool? (should_continue)                     │
                ┌──────────┴──────────┐                            │
                │ (Có)                │ (Không)                    │
                ▼                     ▼                            │
        ┌──────────────┐           ┌─────┐                         │
        │  tools_node  ├───────────┴─────┴─────────────────────────┘
        └──────────────┘ (Trả kết quả ToolMessage về cho Agent)
```

Export: **`faq_graph`** (đã qua `compile()`), sẵn sàng tích hợp trực tiếp vào hệ thống Supervisor tổng.

---

## 🚀 6. Cách Sử Dụng & Tích Hợp

### Gọi trực tiếp FAQ Graph:
```python
from app.ai.agent.faq import faq_graph

inputs = {
    "messages": [("user", "Hotline ngân hàng BVBank là số mấy?")],
    "user_query": "Hotline ngân hàng BVBank là số mấy?",
}

async for event in faq_graph.astream_events(inputs, version="v2"):
    # Stream output response
    pass
```

### Tích hợp vào Supervisor Agent:
Khi Supervisor Agent phân loại ý định `intent == "faq"`, Supervisor chỉ cần chuyển tiếp `state` tới node `faq_graph`.
