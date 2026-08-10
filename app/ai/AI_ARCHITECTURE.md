# 🤖 Hướng Dẫn Kiến Trúc & Xây Dựng AI Agent (BVBank AI System)

Tài liệu này hướng dẫn chi tiết về cấu trúc, nguyên lý vận hành, quy trình phân loại Intent và cách mở rộng hệ thống **Multi-Agent AI** thuộc phân hệ `app/ai`.

---

## 📐 1. Tổng Quan Kiến Trúc Multi-Agent

Hệ thống được thiết kế theo mô hình **Supervisor-Worker Pattern** kết hợp với **Agentic RAG** và **Phân quyền tài liệu RBAC (Role-Based Access Control)**.

```
                    ┌──────────────────────────┐
                    │    User Query / Request  │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │   SUPERVISOR AGENT    │
                     │  (Intent Classifier)  │
                     └───────────┬───────────┘
                                 │
         ┌───────────────────────┼───────────────────────┬───────────────────────┐
         │ (intent: faq)         │ (intent: rag)         │ (intent: gamspro)     │ (intent: fallback)
         ▼                       ▼                       ▼                       ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    FAQ AGENT    │     │  AGENTIC RAG    │     │  gAMSPro AGENT  │     │ FALLBACK HANDLER│
│  (Quick Lookup) │     │ (Deep Document) │     │(Asset Mgmt 8 Mod)│     │(Chitchat/Refuse)│
└─────────────────┘     └────────┬────────┘     └─────────────────┘     └─────────────────┘
                                 │
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  RAG RETRIEVAL SUBSYSTEM│
                    │ (SQL Vector + RBAC Filter)│
                    └─────────────────────────┘
```

---

## 📁 2. Cấu Trúc Thư Mục `app/ai`

```text
app/ai/
├── agent/                         # Các AI Agent độc lập
│   ├── supervisor/                # Supervisor Router Node (Phân loại Intent)
│   │   ├── graph/                 # LangGraph / Node workflow
│   │   ├── nodes/                 # Logic node classify_intent_node
│   │   ├── prompts/               # System & User prompts (v1/system.md)
│   │   ├── schemas.py             # Pydantic RouterOutput & IntentType Enum
│   │   └── state.py               # SupervisorState Schema
│   │
│   ├── faq/                       # Agent xử lý quy trình nhanh / tra cứu atomic
│   │   ├── graph/                 # Graph workflow
│   │   ├── prompts/               # Prompt registry
│   │   └── tools/                 # Tool tra cứu FAQ
│   │
│   └── agentic_rag/               # Agent tra cứu văn bản quy chế phức tạp
│       ├── graph/                 # ReAct / Plan-and-Execute Loop
│       ├── prompts/               # Prompt registry
│       └── tools/                 # Vector Retrieval Tools
│
├── memory/                        # Bộ nhớ hội thoại & Rewrite Query
│   └── conversation/
│       └── schemas.py             # ContextualizedQuery Pydantic Model
│
├── rag/                           # Subsystem RAG & Vector Store
│   ├── embedding/                 # TeiEmbeddingService (PyTorch GPU / TEI / Ollama)
│   └── retrieval/                 # VectorRetriever (Lọc phân quyền RBAC)
│
└── eval/                          # Khung đánh giá tự động (LLM Evaluation Framework)
    ├── metrics.py                 # Metric chấm điểm (ExactMatch, MinValue, LLMJudge)
    ├── report.py                  # Xuất báo cáo Rich Console & JSON Dashboard
    ├── runner.py                  # Trình thực thi Eval Test Cases
    └── scorer.py                  # Đánh giá & tính score tổng hợp
```

---

## 🎯 3. Quy Trình Vận Hành Của Supervisor Agent (Intent Classifier)

### 3.1. Các Phân Loại Intent (`IntentType`)

1. **`faq` (Frequently Asked Questions)**:
   - **Mô tả**: Các câu hỏi thủ tục nguyên tử, tra cứu thông tin tĩnh đơn giản (eOffice, VPP, HR self-service, giờ làm việc, người được sửa tài liệu, xuất PDF).
   - **Từ khóa nhận diện**: *"Làm thế nào để...", "Ở đâu...", "Mấy giờ...", "Bao nhiêu ngày...", "Ai được..."*

2. **`rag` (Business Process & Procedure Manual Retrieval)**:
   - **Mô tả**: Truy vấn quy trình nghiệp vụ nhiều bước từ Sổ tay HDSD Dịch vụ Văn phòng / VPP / eOffice, các luồng phê duyệt cấp quản lý, điều kiện trả về, báo cáo phân bổ chi phí.
   - **Ví dụ**: Các bước xác nhận PYC của Trưởng đơn vị, quy trình điều phối PYC, chỉnh sửa kỳ đăng ký, quy trình phê duyệt danh mục dịch vụ.

3. **`gamspro` (Hệ Thống Quản Lý Tài Sản gAMSPro - 8 Phân Hệ)**:
   - **Mô tả**: Các thao tác nghiệp vụ, quy trình, biểu mẫu liên quan trực tiếp đến 8 phân hệ gAMSPro:
     1. *Master Data & System Management* (Danh mục & Hệ thống)
     2. *Procurement Planning & Settlement* (Kế hoạch - Mua sắm - Thanh quyết toán)
     3. *Material Inventory Management* (Kho vật liệu - HCQT & Kế toán)
     4. *Fixed Assets & Tools Management* (TSCĐ & CCLD)
     5. *Real Estate, Headquarters & Capital Construction* (BĐS, Trụ sở & XDCB)
     6. *Request Slips & Fleet Operations* (PYC Xe, PYC Công tác & Vận hành xe)
     7. *Auto-payment & Business Proposals* (Thanh toán tự động & Tờ trình nghiệp vụ)
     8. *Mobile Apps* (App Mobile Kiểm kê & App Phê duyệt)
   - **Từ khóa nhận diện**: *"Phân hệ...", "Tài sản cố định", "PYCXE", "Tờ trình nghiệp vụ", "App kiểm kê", "gAMSPro", "Thẻ tài sản", "Điều chuyển TSCĐ"*.

4. **`fallback` (Out of Scope / Chitchat)**:
   - **Mô tả**: Lời chào hỏi xã giao, câu hỏi ngoài phạm vi nghiệp vụ (thời tiết, chứng khoán, công thức nấu ăn), truy vấn mơ hồ hoặc các nỗ lực Prompt Injection.

---

## 🔒 4. Cơ Chế Phân Quyền Tài Liệu RBAC (Security & Compliance)

Mọi truy vấn RAG trong `app/ai/rag/retrieval/retriever.py` đều bắt buộc tuân thủ quy tắc phân quyền **RBAC**:

- **Header Request**: Nhận chuỗi `X-User-Roles` (ví dụ: `"Employee,Manager"`) từ C# Gateway.
- **Quy Tắc SQL Vector Search**:
  - Chunk hợp lệ nếu `accessScope` = `'Public'` (hoặc `NULL`).
  - HOẶC `accessScope` = `'Restricted'` VÀ `X-User-Roles` có chứa vai trò `'admin'`.
  - HOẶC `accessScope` = `'Restricted'` VÀ danh sách vai trò người dùng trùng khớp với mảng `allowedRoles` lưu trong Metadata của Chunk.

---

## 🧪 5. Khung Đánh Giá Tự Động (Eval Framework)

Hệ thống tích hợp công cụ đánh giá tự động tại `app/ai/eval/` và script `scripts/run_eval.py`:

### Các Chỉ Số Đo Lường Đánh Giá (Evaluation Metrics)
1. **Chỉ số kiểm tra test case đơn lẻ**:
   - **`exact_field_match`**: So sánh chính xác field đầu ra (`target_agent`).
   - **`min_value`**: Đảm bảo mức độ tin cậy `confidence >= 0.85`.
   - **`latency`**: Kiểm tra thời gian phản hồi không quá ngưỡng (vd: 20.0s).
   - **`llm_judge`**: Sử dụng Gemini API đánh giá chất lượng ngữ nghĩa (`faithfulness`, `relevance`).

2. **Chỉ số phân loại tổng hợp (Classification Metrics)**:
   - **`Accuracy`**: Tỷ lệ phân loại đúng tổng thể trên toàn bộ tập test cases.
   - **`Precision`, `Recall`, `F1-Score`**: Tính toán tự động cho từng nhóm Intent (`faq`, `rag`, `gamspro`, `fallback`) và chỉ số trung bình `Macro F1`.
   - **`Confidence Calibration`**: Đánh giá độ tin cậy của điểm Confidence Score do LLM sinh ra bằng cách so sánh **Mean Confidence của các case đoán đúng** vs **Mean Confidence của các case đoán sai** để kết luận mức độ tự tin (Well Calibrated / Overconfident / Underconfident).

3. **Phân Tích Lỗi & Tự Động Hóa (Error Analysis & CI/CD Benchmark)**:
   - **`Confusion Matrix 2D`**: Trực quan hóa ma trận nhầm lẫn 2D giữa Expected Intent vs Actual Intent để phát hiện mẫu nhầm giữa `faq <-> rag` hoặc `rag <-> gamspro`.
   - **`Misclassified Cases Log`**: Log chi tiết câu query, intent kỳ vọng, intent dự đoán và **chuỗi LLM Reasoning** giúp tinh chỉnh System Prompt / Few-shot Examples.
   - **`Benchmark Audit Threshold`**: Kiểm tra tự động ngưỡng tối thiểu (mặc định Pass Rate $\ge 90\%$). Trả về exit status 1 để ngắt CI/CD build khi có rủi ro suy giảm chất lượng prompt (Prompt Regression).
   - **`LangSmith LLMOps Integration`**: Tự động đồng bộ feedback, accuracy, macro F1 và traces lên dashboard LangSmith khi khai báo `LANGCHAIN_TRACING_V2=true` và `LANGCHAIN_API_KEY`.

### Lệnh Chạy Eval (Poe Task)
```bash
# Chạy eval cho toàn bộ test cases của Supervisor Agent
uv run poe eval supervisor

# Chỉ chạy lại các test cases bị FAIL ở lần eval trước (bỏ qua các test cases đã PASS)
uv run poe eval supervisor --failed
# Hoặc viết gọn:
uv run poe eval supervisor -f

# Chạy eval với ngưỡng Benchmark tối thiểu (ví dụ: 90% Pass Rate)
uv run poe eval supervisor --threshold 0.90

# Chạy eval cho 1 test case cụ thể theo index (ví dụ: index 31)
uv run poe eval supervisor 31

# Chạy eval riêng cho FAQ Agent
uv run poe eval faq

# Chạy eval cho toàn bộ Agents
uv run poe eval --all
```

---

## 🛠️ 6. Hướng Dẫn Thêm AI Agent Mới Vào Hệ Thống

Để thêm 1 Agent mới (ví dụ: `finance_agent`), thực hiện 4 bước sau:

1. **Tạo thư mục Agent**:
   ```text
   app/ai/agent/finance/
   ├── graph/
   ├── prompts/v1/ (system.md, user.md)
   ├── eval/ (config.yaml, cases/case_01.json)
   └── tools/
   ```
2. **Khai báo Intent trong Enum**:
   Thêm `FINANCE = "finance"` vào `IntentType` trong `app/ai/agent/supervisor/schemas.py`.
3. **Cập nhật System Prompt Supervisor**:
   Thêm định nghĩa và từ khóa phân loại `finance` vào `app/ai/agent/supervisor/prompts/v1/system.md`.
4. **Đăng ký Entrypoint Eval**:
   Khai báo hàm async entrypoint trong `scripts/run_eval.py` vào dictionary `_AGENT_ENTRYPOINTS`.
