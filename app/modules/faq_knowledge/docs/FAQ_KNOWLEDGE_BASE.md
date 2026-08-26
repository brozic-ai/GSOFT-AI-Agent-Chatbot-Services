# Báo Cáo Triển Khai Module FAQ Knowledge Base & Nhập Dữ Liệu Từ Excel

Báo cáo này tổng hợp chi tiết toàn bộ các công việc đã thực hiện để xây dựng module **FAQ Knowledge Base** trong hệ thống backend FastAPI (`GSOFT-AI-Agent-Chatbot-Services`).

---

## 📐 1. Kiến Trúc & Cấu Trúc Mã Nguồn

Module được thiết kế theo mô hình **Domain-Driven Design (DDD)** đồng bộ với các phân hệ hiện có của ứng dụng:

```text
app/modules/faq_knowledge/
├── __init__.py
├── model.py                 # SQLAlchemy ORM Model (bảng FAQ_Knowledge_Base)
├── schema.py                # Pydantic Schemas cho request/response validation
├── repository.py            # Tầng tương tác CSDL & logic chuẩn hóa chống trùng
├── service.py               # Business logic xử lý CRUD & Đọc file Excel bằng Pandas
├── docs/
│   └── FAQ_KNOWLEDGE_BASE.md# Tài liệu chi tiết module
└── api/
    ├── __init__.py
    └── v1/
        ├── __init__.py
        └── endpoints.py     # FastAPI REST API Endpoints (/api/v1/faq)
```

---

## 🗄️ 2. Thiết Kế Cơ Sở Dữ Liệu (`FAQ_Knowledge_Base`)

File: [model.py](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/modules/faq_knowledge/model.py)

Bảng **`dbo.FAQ_Knowledge_Base`** bao gồm các trường dữ liệu và chỉ mục ràng buộc sau:

| Tên Cột DB | Tên Trong Python Model | Kiểu Dữ Liệu | Ràng Buộc | Mô Tả |
|---|---|---|---|---|
| `Id` | `id` | `INTEGER` | Primary Key, Auto-increment | Định danh duy nhất |
| `Question` | `question` | `NVARCHAR(MAX)` | `NOT NULL` | Câu hỏi gốc |
| `QuestionNormalized` | `question_normalized` | `NVARCHAR(MAX)` | `NOT NULL`, `UNIQUE` (`UQ_FAQ_QuestionNormalized`) | Câu hỏi đã chuẩn hóa (lowercase, trim) để chống trùng |
| `Answer` | `answer` | `NVARCHAR(MAX)` | `NOT NULL` | Câu trả lời tương ứng |
| `Category` | `category` | `NVARCHAR(200)` | `NULLABLE`, Index (`IX_FAQ_Category`) | Phân loại/Chủ đề (eOffice, VPP, Nhân sự,...) |
| `Metadata` | `metadata_json` | `NVARCHAR(MAX)` | `NULLABLE` | Siêu dữ liệu bổ sung dạng JSON |
| `CreatedAt` | `created_at` | `DATETIME2` | `NOT NULL`, Default `utcnow` | Thời điểm tạo bản ghi |
| `UpdatedAt` | `updated_at` | `DATETIME2` | `NULLABLE`, OnUpdate `utcnow` | Thời điểm cập nhật gần nhất |

---

## 🛡️ 3. Cơ Chế Kiểm Tra Trùng Lặp Tự Động (Duplication Check)

Hệ thống kết hợp **2 lớp bảo vệ chống trùng lặp**:

1. **Chuẩn hóa chuỗi (Normalization)**:
   - Trước khi lưu hoặc tìm kiếm, câu hỏi được chuyển về chữ thường (`lowercase`) và loại bỏ các khoảng trắng thừa đầu/cuối/trung gian.
   - Ví dụ: `" Chi nhánh  BVBank mấy giờ mở cửa? "` $\rightarrow$ `"chi nhánh bvbank mấy giờ mở cửa?"`.

2. **Xử lý 2 lớp**:
   - **Tầng Application**: Trong [repository.py](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/modules/faq_knowledge/repository.py), hàm `exists_normalized()` kiểm tra nhanh trong CSDL trước khi thêm mới.
   - **Tầng Database**: Ràng buộc `UniqueConstraint("QuestionNormalized")` đóng vai trò safety net đảm bảo không thể lọt dữ liệu trùng dù gọi song song (concurrent requests).

---

## 📊 4. Service Nhập Dữ Liệu File Excel (Pandas Ingestion)

File: [service.py](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/modules/faq_knowledge/service.py)

Hàm `import_from_excel(file: UploadFile)` thực hiện các bước:

1. **Kiểm tra định dạng**: Chỉ nhận file `.xlsx` hoặc `.xls`.
2. **Đọc dữ liệu**: Sử dụng `pandas.read_excel()` để parse dữ liệu.
3. **Nhận diện cột linh hoạt**: Tự động khớp tên cột case-insensitive:
   - **Cột câu hỏi**: `Câu hỏi`, `Question`, `Q`, `Cau hoi`
   - **Cột câu trả lời**: `Câu trả lời`, `Answer`, `A`, `Cau tra loi`
4. **Bỏ qua trùng lặp & Ghi log**:
   - Kiểm tra trùng lặp trên DB cho từng dòng.
   - Nếu bị trùng $\rightarrow$ Tăng biến đếm `skipped_count`, log thông tin câu hỏi bị skip, lưu danh sách xem trước (preview max 20 câu).
   - Nếu dữ liệu hợp lệ $\rightarrow$ Bulk insert vào DB.
5. **Trả về thống kê tổng quan**:
   ```json
   {
     "total_rows": 50,
     "imported_count": 42,
     "skipped_count": 7,
     "error_count": 1,
     "skipped_questions": [ ... ],
     "errors": [ ... ]
   }
   ```

---

## 🚀 5. Danh Sách API Endpoints (RESTful API)

File: [endpoints.py](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/modules/faq_knowledge/api/v1/endpoints.py)

Đã đăng ký tất cả các endpoint tại prefix `/api/v1/faq`:

| Method | Endpoint | Mô Tả | Response Status / Schema |
|---|---|---|---|
| `GET` | `/api/v1/faq/` | Lấy danh sách FAQ (có phân trang `page`, `page_size`, lọc theo `category`) | `200 OK` (`FaqListResponse`) |
| `GET` | `/api/v1/faq/{faq_id}` | Lấy thông tin chi tiết 1 câu hỏi theo ID | `200 OK` / `404 Not Found` |
| `POST` | `/api/v1/faq/` | Thêm mới 1 câu hỏi thủ công | `201 Created` / `409 Conflict` (nếu trùng câu hỏi) |
| `PUT` | `/api/v1/faq/{faq_id}` | Cập nhật nội dung câu hỏi / câu trả lời theo ID | `200 OK` / `409 Conflict` |
| `DELETE` | `/api/v1/faq/{faq_id}` | Xóa vĩnh viễn 1 bản ghi FAQ | `200 OK` / `404 Not Found` |
| `POST` | `/api/v1/faq/upload-excel` | Upload file Excel `.xlsx/.xls` nhập liệu hàng loạt | `200 OK` (`UploadExcelResponse`) |

---

## 🔗 6. Các Tích Hợp Hệ Thống

1. **Router Registration** ([router.py](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/routers/router.py)):
   - Đăng ký `faq_router` vào `api_v1_router` với tag `"FAQ Knowledge Base"`.
2. **Auto Database Migration** ([database.py](file:///c:/Users/Admin/Documents/GSOFT_Projects/Main_system/GSOFT-AI-Agent-Chatbot-Services/app/core/database.py)):
   - Thêm `import app.modules.faq_knowledge.model` vào hàm `init_db()` để bảng `FAQ_Knowledge_Base` tự động được khởi tạo khi ứng dụng khởi động.

---

## 🧪 7. Kiểm Thử & Nghiệm Thu

1. **Khởi động ứng dụng**:
   ```bash
   uvicorn app.main:app --reload
   ```
2. **Kiểm tra Swagger UI**:
   - Truy cập `http://localhost:8000/docs`.
   - Tìm nhóm tag **FAQ Knowledge Base** để thử nghiệm trực tiếp các API CRUD và Upload File Excel.
