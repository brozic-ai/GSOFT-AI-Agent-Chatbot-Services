# 📖 User Story & Demo Script — Procurement Agent (gAMSPro Chatbot BVBank)

> **Nhân vật chính:** 
> - **Anh Trương Quang Bảo** (`baotq` - Chuyên viên Phòng Hỗ trợ — Hội sở BVBank)
> - **Lãnh đạo phê duyệt** (Sếp / Cấp thẩm quyền ký duyệt số)
> - **Trợ lý AI gAMSPro** (BVBank Procurement Copilot)
> 
> **Mục tiêu:** Trình diễn luồng nghiệp vụ khép kín từ **Khởi tạo tờ trình ➔ Đối soát hạn mức ngân sách ➔ Trình duyệt ➔ Thẩm định phê duyệt hồ sơ cho Lãnh đạo ➔ Truy vết đơn hàng PO**.  
> **Định vị:** Trợ lý AI Enterprise hỗ trợ self-service 24/7, liên thông dữ liệu chuẩn xác 100% từ Core gAMSPro theo thời gian thực.

---

## 🎯 5 ĐIỂM BVBANK CHÚ TRỌNG NHẤT (GIÁ TRỊ CỐT LÕI)

1. **Kiểm soát Ngân sách & Tuân thủ Hạn mức (Budget Compliance):**
   - Đảm bảo Tờ trình mua sắm không vượt hạn mức Kế hoạch đã duyệt. AI tự động đối soát số tiền đề xuất với số dư ngân sách khả dụng.
2. **Hành động & Phê duyệt An toàn (Actionable AI & Security Guardrails):**
   - Hỗ trợ tạo mới Tờ trình Lưu Nháp và gửi phê duyệt trực tiếp trên gAMSPro qua API.
   - **Tuyệt đối không tự ý ký duyệt thay Lãnh đạo**: AI đóng vai trò thẩm định chuyên môn (Risk/Benefit analysis) và cung cấp đường dẫn tương đối (Relative Deep Link) để Lãnh đạo tự bấm duyệt.
3. **Thu thập thông tin đa lượt thông minh (Multi-turn Slot Filling):**
   - Khi cán bộ yêu cầu tạo tờ trình mà thiếu thông tin (số tiền, kế hoạch), AI tự động trò chuyện lịch sự hỏi bổ sung cho đến khi đủ thông tin mới khởi tạo.
4. **Truy vết Liên thông End-to-End (Cross-module Traceability):**
   - Xâu chuỗi 3 phân hệ: `Tờ trình Nghiệp vụ` ➔ `Kế hoạch Mua sắm` ➔ `Đơn đặt hàng PO`. CBNV không cần chuyển đổi nhiều màn hình thủ công hay tra cứu phân tán.
5. **Tuyệt đối Không Ảo giác (Zero Hallucination):**
   - Mọi dữ liệu (mã tờ trình, số tiền, ngày duyệt, hạn mức ngân sách, tiến độ PO) 100% truy vấn trực tiếp từ API gAMSPro thông qua Tool Calls theo thời gian thực.

---

## 🎬 KỊCH BẢN DEMO CHI TIẾT (DEMO SCRIPT)

### MÀN 1: GIỚI THIỆU & KHẢO SÁT NĂNG LỰC
> **Mục tiêu:** Thể hiện Agent hiểu rõ nghiệp vụ ngân hàng và chào hỏi đúng ngữ cảnh.

**Người dùng (Anh Bảo):**  
"Trợ lý Mua sắm gAMSPro có thể hỗ trợ tôi những nghiệp vụ gì?"

**Chatbot:**  
"Xin chào anh Bảo! Tôi là **Trợ lý Mua sắm Doanh nghiệp (gAMSPro)** của BVBank. Tôi sẵn sàng hỗ trợ anh các nghiệp vụ sau:
1. 📄 **Tra cứu Tờ trình Mua sắm:** Xem danh sách, chi tiết tiến độ, số tiền và trạng thái phê duyệt.
2. 📊 **Đối soát Kế hoạch Ngân sách:** Kiểm tra hạn mức, số tiền đã thực hiện và số dư khả dụng.
3. 📝 **Thu thập thông tin & Lập Tờ trình mới:** Hỗ trợ tạo tờ trình Lưu Nháp trực tiếp vào hệ thống gAMSPro.
4. 📤 **Trình duyệt & Thẩm định:** Gửi phê duyệt hồ sơ và lập Báo cáo Thẩm định rủi ro/lợi ích cho Lãnh đạo.
5. 🚚 **Theo dõi Đơn đặt hàng PO:** Truy vết đơn hàng, nhà cung cấp và hạn giao hàng."

---

### MÀN 2: TRA CỨU DANH SÁCH TỜ TRÌNH MUA SẮM
> **Công cụ kích hoạt:** `search_request_docs`

**Người dùng (Anh Bảo):**  
"Cho tôi xem danh sách các Tờ trình mua sắm tôi đã lập gần đây."

**Chatbot** *(Gọi tool: `search_request_docs(user_name="baotq")`)*:  
"Xin chào anh Bảo! Dưới đây là các tờ trình mua sắm gần đây nhất của anh trên gAMSPro:

1. 📄 **PUR/2025/000052** — Trạng thái: ✅ **Đã duyệt** — **50,000,000 VNĐ**
2. 📄 **PUR/2026/000065** — Trạng thái: ⚠️ **Lưu Nháp** — **7,000,000 VNĐ**

Anh muốn xem chi tiết hoặc thực hiện thao tác với tờ trình nào ạ?"

---

### MÀN 3: XEM CHI TIẾT TỜ TRÌNH HIỆN CÓ
> **Công cụ kích hoạt:** `get_request_doc_detail`

**Người dùng (Anh Bảo):**  
"Cho tôi xem chi tiết tờ trình PUR/2025/000052 đi."

**Chatbot** *(Gọi tool: `get_request_doc_detail(doc_identifier="PUR/2025/000052")`)*:  
"Đây là thông tin chi tiết **Tờ trình số PUR/2025/000052**:

| Thông tin chỉ tiêu | Chi tiết dữ liệu từ gAMSPro |
|:---|:---|
| **Mã hệ thống (REQ_ID)** | `TRRD00000269630` |
| **Người lập** | Trương Quang Bảo (Phòng Hỗ trợ — Hội sở BVBank) |
| **Đơn vị chịu chi phí** | Hội sở BVBank — Phòng Hỗ trợ |
| **Tổng tiền đề xuất** | **50,000,000 VNĐ** |
| **Ngày tạo tờ trình** | 22/12/2025 |
| **Trạng thái** | ✅ **Đã duyệt (Chờ đầu mối mua sắm xử lý)** |
| **Kế hoạch liên kết** | 📌 `0049/2025/TTr-0690905` |

👉 [Xem hồ sơ chi tiết trên gAMSPro](/app/admin/request-doc-view;id=TRRD00000269630)

Anh có muốn tôi đối soát hạn mức ngân sách của Kế hoạch liên kết `0049/2025/TTr-0690905` không?"

---

### MÀN 4: ĐỐI SOÁT HẠN MỨC KẾ HOẠCH NGÂN SÁCH
> **Công cụ kích hoạt:** `check_plan_budget_detail`

**Người dùng (Anh Bảo):**  
"Kiểm tra luôn Kế hoạch liên kết giúp tôi."

**Chatbot** *(Gọi tool: `check_plan_budget_detail(ma_ke_hoach="0049/2025/TTr-0690905")`)*:  
"📊 **BÁO CÁO ĐỐI SOÁT KẾ HOẠCH NGÂN SÁCH `0049/2025/TTr-0690905`:**

| Thông tin Kế hoạch | Chi tiết Ngân sách |
|:---|:---|
| **Mã Kế hoạch** | `0049/2025/TTr-0690905` |
| **Tên Kế hoạch** | Kế hoạch mua sắm Trang thiết bị năm 2025 |
| **Đơn vị quản lý** | Hội sở — Phòng Hỗ trợ |
| **Trạng thái Kế hoạch** | ✅ **Đã phê duyệt** |
| **Tổng hạn mức ngân sách** | **156,750,000 VNĐ** |
| **Ngân sách đã thực hiện** | 31,350,000 VNĐ |
| **Ngân sách còn lại khả dụng** | 🟩 **125,400,000 VNĐ** |

🟢 **ĐÁNH GIÁ TỰ ĐỘNG TUÂN THỦ NGÂN SÁCH:**  
Kế hoạch đã được phê duyệt hợp lệ. Ngân sách còn lại khả dụng (**125,400,000 VNĐ**) hoàn toàn đủ để chi trả cho khoản đề xuất **50,000,000 VNĐ** của Tờ trình."

---

### MÀN 5: THU THẬP THÔNG TIN ĐA LƯỢT (SLOT FILLING) & TẠO TỜ TRÌNH MỚI
> **Cơ chế:** Multi-turn Slot Filling ➔ Kích hoạt `create_request_doc`

**Người dùng (Anh Bảo - Lượt 1, thiếu thông tin):**  
"Tạo tờ trình Mua máy in laser văn phòng cho tôi"

**Chatbot** *(Nhận diện thiếu Số tiền & Kế hoạch ➔ Không gọi tool, hỏi bổ sung)*:  
"Dạ, tôi đã ghi nhận tiêu đề tờ trình là **'Mua máy in laser văn phòng'**.

Để hoàn tất việc tạo tờ trình trên gAMSPro, anh Bảo vui lòng cho biết thêm:
1. 💰 **Tổng số tiền đề xuất dự kiến** (VNĐ) là bao nhiêu?
2. 📌 **Mã Kế hoạch ngân sách liên kết** (ví dụ: `0049/2025/TTr-0690905`)?"

**Người dùng (Anh Bảo - Lượt 2, bổ sung đủ thông tin):**  
"Dự kiến 15 triệu, liên kết kế hoạch 0049/2025/TTr-0690905"

**Chatbot** *(Gọi tool: `create_request_doc(tieu_de="Mua máy in laser văn phòng", tong_tien=15000000, ma_ke_hoach="0049/2025/TTr-0690905")`)*:  
"✅ **TẠO TỜ TRÌNH THÀNH CÔNG TRÊN GAMS PRO!**

- **Số Tờ trình:** 📄 `PUR/2026/000088`
- **Mã hệ thống (REQ_ID):** `TRRD00000269719`
- **Tiêu đề:** Mua máy in laser văn phòng
- **Tổng tiền đề xuất:** **15,000,000 VNĐ**
- **Trạng thái:** ⚠️ **Lưu Nháp** (Chờ gửi phê duyệt)
- **Kế hoạch liên kết:** 📌 `0049/2025/TTr-0690905`

👉 **Đường dẫn xem hồ sơ:** [Xem chi tiết Tờ trình trên gAMSPro](/app/admin/request-doc-view;id=TRRD00000269719)

Anh có muốn gửi phê duyệt tờ trình này ngay bây giờ không ạ?"

---

### MÀN 6: GỬI PHÊ DUYỆT TỜ TRÌNH
> **Công cụ kích hoạt:** `submit_request_doc_approval`

**Người dùng (Anh Bảo):**  
"Gửi phê duyệt tờ trình vừa tạo giúp tôi"

**Chatbot** *(Gọi tool: `submit_request_doc_approval(doc_identifier="PUR/2026/000088")`)*:  
"✅ **GỬI PHÊ DUYỆT TỜ TRÌNH THÀNH CÔNG!**

- **Số Tờ trình:** 📄 `PUR/2026/000088`
- **Trạng thái mới:** ⏳ **Đã gửi phê duyệt** (Đang chờ cấp quản lý ký duyệt số)

👉 **Theo dõi hồ sơ trên web:** [PUR/2026/000088](/app/admin/request-doc-view;id=TRRD00000269719)

Hồ sơ đã được chuyển tiếp đến cấp thẩm quyền. Bất kỳ lúc nào, anh có thể hỏi tôi để kiểm tra tiến độ xử lý nhé!"

---

### MÀN 7: CỐ VẤN THẨM ĐỊNH PHÊ DUYỆT CHO LÃNH ĐẠO (AI KHÔNG TỰ DUYỆT)
> **Cơ chế:** Guardrail bảo mật ➔ Gọi `get_request_doc_detail` + `check_plan_budget_detail` ➔ Cung cấp Deep Link.

**Người dùng (Lãnh đạo / Sếp hỏi):**  
"Tôi có nên duyệt tờ trình PUR/2026/000065 không? Phân tích lợi hại giúp tôi."

**Chatbot** *(Phân tích rủi ro & thẩm định chuyên môn)*:  
"Chào anh! Theo quy định phân quyền bảo mật ngân hàng, **Trợ lý AI không được phép tự ý thay mặt Lãnh đạo ký duyệt hồ sơ**. Tôi xin gửi Báo cáo Thẩm định Chuyên môn để anh xem xét phê duyệt:

📊 **BÁO CÁO THẨM ĐỊNH TỜ TRÌNH PUR/2026/000065:**
- **Mã hệ thống:** `TRRD00000269696`
- **Người lập:** Trương Quang Bảo (Phòng Hỗ trợ — Hội sở)
- **Tổng tiền đề xuất:** 7,000,000 VNĐ
- **Kế hoạch liên kết:** `0030/2025/TTr-0690905` (Hạn mức: 182.2M | Đã dùng: 25.0M | Khả dụng: **157.1M VNĐ**)

⚖️ **PHÂN TÍCH LỢI ÍCH & RỦI RO:**
- **Lợi ích:** Đảm bảo trang thiết bị làm việc kịp thời cho đơn vị, đúng danh mục kế hoạch đã duyệt.
- **Kiểm soát Ngân sách:** 🟢 **AN TOÀN**. Ngân sách còn lại khả dụng (157,188,480 VNĐ) hoàn toàn đủ để cover khoản 7,000,000 VNĐ, không có rủi ro vượt hạn mức.
- **Khuyến nghị Chuyên môn:** 🟢 **ĐỦ ĐIỀU KIỆN ĐỂ PHÊ DUYỆT**.

👉 **Anh vui lòng nhấn vào đường dẫn dưới đây để trực tiếp xem chi tiết và bấm Ký duyệt trên hệ thống gAMSPro:**  
🔗 [Xem chi tiết và Ký duyệt Tờ trình PUR/2026/000065](/app/admin/request-doc-view;id=TRRD00000269696)"

---

### MÀN 8: THEO DÕI ĐƠN ĐẶT HÀNG PO (PURCHASE ORDER)
> **Công cụ kích hoạt:** `get_po_master_status`

**Người dùng (Anh Bảo):**  
"Tra cứu thông tin đơn đặt hàng PO PO069/26/0006."

**Chatbot** *(Gọi tool: `get_po_master_status(po_code="PO069/26/0006")`)*:  
"🚚 **THÔNG TIN ĐƠN ĐẶT HÀNG PO: `PO069/26/0006`**

| Thông tin Đơn hàng | Chi tiết dữ liệu từ gAMSPro |
|:---|:---|
| **Mã Đơn hàng PO** | `PO069/26/0006` |
| **Nhà cung cấp** | testzzzzz |
| **Tổng giá trị đơn hàng** | **12,765 VNĐ** |
| **Trạng thái PO** | ✅ **Đã duyệt PO** |
| **Hạn giao hàng cam kết**| 📅 **30/05/2025** |

Đơn hàng đang được nhà cung cấp triển khai theo đúng tiến độ cam kết."

---

### MÀN 9: XỬ LÝ NGOẠI LỆ / TRA CỨU KHÔNG TỒN TẠI
> **Cơ chế:** Graceful Error Handling (Xử lý mượt mà, không crash hay lộ lỗi hệ thống)

**Người dùng (Anh Bảo):**  
"Tra cứu tờ trình số PUR/2099/999999."

**Chatbot** *(Gọi tool `get_request_doc_detail` ➔ Nhận diện mã không tồn tại)*:  
"Dạ, tôi đã tìm kiếm trên hệ thống gAMSPro nhưng **không tìm thấy thông tin Tờ trình số `PUR/2099/999999`**.

Anh vui lòng kiểm tra lại số hiệu tờ trình hoặc hỏi tôi để xem danh sách các tờ trình anh đã lập gần đây nhé!"

---

## 📊 TỔNG KẾT LUỒNG HỘI THOẠI & KĨ THUẬT TOOL CALL

| # | Màn Demo | Câu hỏi của người dùng | Tool Call / Kỹ thuật tương ứng | Điểm nhấn Trình diễn |
|:---:|:---|:---|:---|:---|
| **1** | **Giới thiệu** | *"Hỗ trợ nghiệp vụ gì?"* | Persona & Conversational Knowledge | Định vị chuẩn chuyên viên Mua sắm BVBank |
| **2** | **Danh sách** | *"Xem danh sách Tờ trình gần đây?"* | `search_request_docs` | Phân loại trạng thái (Lưu Nháp / Đã duyệt) |
| **3** | **Chi tiết** | *"Xem chi tiết PUR/2025/000052?"* | `get_request_doc_detail` | Thông tin người lập, số tiền, mã Kế hoạch liên kết |
| **4** | **Ngân sách** | *"Kiểm tra Kế hoạch liên kết?"* | `check_plan_budget_detail` | Đối soát tự động số dư khả dụng (Budget Check) |
| **5** | **Tạo mới** | *"Tạo tờ trình Mua máy in..."* | **Multi-turn Slot Filling** ➔ `create_request_doc` | Hỏi bù thông tin còn thiếu, tạo bản ghi thật trên CSDL |
| **6** | **Trình duyệt** | *"Gửi phê duyệt tờ trình vừa tạo"* | `submit_request_doc_approval` | Chuyển trạng thái sang chờ duyệt qua API thật |
| **7** | **Thẩm định** | *"Tôi có nên duyệt tờ trình này không?"* | **Approval Advisor** (No Auto-Approve) | Phân tích Lợi/Hại, gửi Deep Link cho Sếp tự ký |
| **8** | **Đơn hàng PO**| *"Tra cứu đơn hàng PO069/26/0006"* | `get_po_master_status` | Truy vết nhà cung cấp, hạn giao hàng thực tế |
| **9** | **Ngoại lệ** | *"Tra cứu tờ trình PUR/2099/999999"* | **Graceful Handling** | Ứng xử ân cần, hướng dẫn tra cứu lại |

---

## 🚀 THÔNG ĐIỆP PITCHING CHỐT HẠ CHO BAN LÃNH ĐẠO (CLOSING PITCH)

* **Về Tốc độ Xử lý:** Tối ưu hóa thời gian tra cứu dữ liệu liên phân hệ từ **15 phút thao tác thủ công xuống dưới 2 giây**.
* **Về Độ Chính xác:** Loại bỏ 100% rủi ro ảo giác (Zero Hallucination) nhờ kết nối dữ liệu trực tiếp qua gAMSPro RESTful API.
* **Về An toàn Tài chính:** Tự động hóa khâu đối soát tuân thủ hạn mức ngân sách (Budget Compliance) ngay từ khi tạo Tờ trình.
* **Về Bảo mật & Phân quyền:** Tuân thủ tuyệt đối quy chế ngân hàng: AI chỉ thẩm định và điều hướng Deep Link, quyền ký duyệt số luôn thuộc về Lãnh đạo.
* **Về Trải nghiệm Vận hành:** Chuyển đổi mô hình tra cứu thụ động thành Trợ lý Số chủ động hướng dẫn quy trình, chuẩn hóa trải nghiệm Self-service cho toàn thể Cán bộ Nhân viên BVBank.