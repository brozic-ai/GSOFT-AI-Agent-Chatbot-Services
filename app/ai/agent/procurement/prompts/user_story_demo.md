# 📖 User Story & Demo Script — Procurement Agent (gAMSPro Chatbot BVBank)

> **Nhân vật chính:** Anh **Trương Quang Bảo** (Cán bộ Phòng Hỗ trợ — Hội sở BVBank)  
> **Mục tiêu:** Theo dõi toàn bộ hành trình Tờ trình mua sắm ➔ Kế hoạch ngân sách ➔ Đơn hàng PO của đơn vị mình.  
> **Định vị:** Trợ lý AI Enterprise hỗ trợ self-service 24/7, liên thông dữ liệu chuẩn xác 100% từ Core gAMSPro.

---

## 🎯 5 ĐIỂM BVBANK CHÚ TRỌNG NHẤT (GIÁ TRỊ CỐT LÕI)

1. **Kiểm soát Ngân sách & Tuân thủ Hạn mức (Budget Compliance):**
   - Đảm bảo Tờ trình mua sắm không vượt hạn mức Kế hoạch đã duyệt. AI tự động đối soát số tiền đề xuất với số dư ngân sách khả dụng.
2. **Truy vết Liên thông End-to-End (Cross-module Traceability):**
   - Xâu chuỗi 3 phân hệ: `Tờ trình Nghiệp vụ` ➔ `Kế hoạch Mua sắm` ➔ `Đơn đặt hàng PO`. CBNV không cần chuyển đổi nhiều màn hình thủ công hay tra cứu phân tán.
3. **Tuyệt đối Không Ảo giác (Zero Hallucination):**
   - Mọi dữ liệu (mã tờ trình, số tiền, ngày duyệt, hạn mức ngân sách, tiến độ PO) 100% truy vấn trực tiếp từ API gAMSPro thông qua Tool Calls theo thời gian thực.
4. **Tư vấn Hướng hành động (Actionable AI / Next-Best-Action):**
   - AI không chỉ trả lời dữ liệu tĩnh mà chủ động phân tích trạng thái và hướng dẫn cụ thể các bước tiếp theo để hoàn thành quy trình phê duyệt.
5. **Tối ưu SLA & Trải nghiệm Cán bộ (Self-service Operations):**
   - Bắt đứt các điểm nghẽn giao tiếp giữa các đơn vị, giảm 70% cuộc gọi/email hỏi tiến độ mua sắm giữa các phòng ban, phản hồi tức thì trong < 2 giây.

---

## 🎬 KỊCH BẢN DEMO CHI TIẾT (DEMO SCRIPT)

### PHẦN 1: TRUY VẤN TỜ TRÌNH NGHIỆP VỤ (PROCUREMENT PROPOSAL)

**Người dùng (Anh Bảo):**  
"Cho tôi xem danh sách các Tờ trình mua sắm tôi đã lập gần đây."

**Chatbot** *(Gọi tool: `search_request_docs(user_id="BAOTQ", limit=5)`)*:  
"Xin chào anh Bảo! Tôi đã tra cứu trên hệ thống gAMSPro. Anh hiện có **19 Tờ trình** trên hệ thống. Dưới đây là các tờ trình gần đây nhất của anh:

1. 📄 **PUR/2026/000052** — Trạng thái: ⚠️ **Lưu Nháp** (Chờ gửi phê duyệt) — **7,000,000 VND**
2. 📄 **PUR/2026/000065** — Trạng thái: ⚠️ **Lưu Nháp** (Chờ gửi phê duyệt) — **7,000,000 VND**
3. 📄 **PUR/2026/000021** — Trạng thái: ✅ **Đã phê duyệt** — **45,000,000 VND**

Anh muốn xem thông tin chi tiết của tờ trình nào?"

---

**Người dùng (Anh Bảo):**  
"Cho tôi xem chi tiết tờ trình PUR/2026/000052 đi."

**Chatbot** *(Gọi tool: `get_request_doc_detail(doc_no="PUR/2026/000052")`)*:  
"Đây là thông tin chi tiết **Tờ trình số PUR/2026/000052**:

| Thông tin chỉ tiêu | Chi tiết dữ liệu từ gAMSPro |
|:---|:---|
| **Mã hệ thống** | `TRRD00000269630` |
| **Người lập** | Trương Quang Bảo (Phòng Hỗ trợ — Hội sở) |
| **Đơn vị chịu chi phí** | Hội sở BVBank — Phòng Hỗ trợ |
| **Tổng tiền đề xuất** | **7,000,000 VND** |
| **Ngày tạo tờ trình** | 22/05/2026 |
| **Trạng thái** | ⚠️ **Lưu Nháp** (Chờ gửi phê duyệt) |
| **Nội dung / Lý do** | Mua sắm vật phẩm trang trí & vật tư Marketing thúc đẩy nhận diện thương hiệu sản phẩm Z. |
| **Kế hoạch liên kết** | 📌 `0030/2026/TTr-0690905` |

Tờ trình này hiện đang ở trạng thái **Lưu Nháp** và chưa gửi lên cấp phê duyệt. Anh có muốn tôi kiểm tra **Hạn mức Ngân sách** của Kế hoạch liên kết `0030/2026/TTr-0690905` không?"

---

### PHẦN 2: KẾ HOẠCH MUA SẮM & ĐỐI SOÁT NGÂN SÁCH (BUDGET COMPLIANCE)

**Người dùng (Anh Bảo):**  
"Kiểm tra luôn giúp tôi."

**Chatbot** *(Gọi tool: `check_plan_budget_detail(plan_no="0030/2026/TTr-0690905")`)*:  
"Tôi đã tra cứu Kế hoạch Ngân sách liên kết **0030/2026/TTr-0690905** trên gAMSPro. Kết quả đối soát như sau:

| Thông tin Kế hoạch | Chi tiết Ngân sách |
|:---|:---|
| **Mã Kế hoạch** | `0030/2026/TTr-0690905` |
| **Tên Kế hoạch** | Kế hoạch mua sắm Trang thiết bị Marketing năm 2026 |
| **Đơn vị quản lý** | Hội sở — Phòng Hỗ trợ |
| **Trạng thái Kế hoạch** | ✅ **Đã phê duyệt** (Ngày duyệt: 15/01/2026) |
| **Tổng hạn mức ngân sách** | **35,000,000 VND** |
| **Ngân sách đã cam kết/dùng** | 18,000,000 VND |
| **Ngân sách còn lại khả dụng**| 🟩 **17,000,000 VND** |

🟢 **ĐÁNH GIÁ TỰ ĐỘNG TUÂN THỦ NGÂN SÁCH:**  
Kế hoạch đã được phê duyệt hợp lệ. Ngân sách còn lại khả dụng (**17,000,000 VND**) hoàn toàn đủ để cover khoản đề xuất **7,000,000 VND** của Tờ trình `PUR/2026/000052`.

Anh có muốn kiểm tra tiến độ các Đơn đặt hàng PO đã phát hành thuộc đơn vị mình không?"

---

### PHẦN 3: THEO DÕI ĐƠN ĐẶT HÀNG PO (PURCHASE ORDER)

**Người dùng (Anh Bảo):**  
"Có PO nào được tạo từ tờ trình này chưa?"

**Chatbot** *(Gọi tool: `get_po_master_status(doc_no="PUR/2026/000052")`)*:  
"Hiện tại **chưa có Đơn đặt hàng PO nào** được khởi tạo từ Tờ trình `PUR/2026/000052` vì tờ trình vẫn đang ở trạng thái **Lưu Nháp** và chưa hoàn tất luồng phê duyệt.

🚚 **Tuy nhiên, dưới đây là các Đơn hàng PO khác đang triển khai tại Phòng Hỗ trợ:**

1. 🔹 **PO-2026-008** — Nhà cung cấp: FPT Telecom — **28,000,000 VND**  
   - Nội dung: Đường truyền kết nối dữ liệu dự phòng  
   - Trạng thái: ✅ **Đã ký duyệt PO** | Hạn giao hàng: **20/08/2026**

2. 🔹 **PO-2026-003** — Nhà cung cấp: Công ty TNHH Truyền thông ABC — **12,500,000 VND**  
   - Nội dung: Ấn phẩm quảng bá dịch vụ mới  
   - Trạng thái: 🚚 **Chờ giao hàng** | Hạn giao hàng: **30/08/2026**"

---

### PHẦN 4: TƯ VẤN TỰ ĐỘNG HƯỚNG HÀNH ĐỘNG (NEXT-BEST-ACTION)

**Người dùng (Anh Bảo):**  
"Bây giờ tôi cần làm gì để Tờ trình PUR/2026/000052 được duyệt?"

**Chatbot** *(Tư vấn nghiệp vụ AI — Luồng quy trình gAMSPro)*:  
"Để Tờ trình **PUR/2026/000052** sớm được phê duyệt và chuyển sang giai đoạn tạo đơn hàng PO, anh Bảo thực hiện theo **3 bước chuẩn** sau:

1️⃣ **Bước 1 — Hoàn thiện chi tiết Tờ trình trên gAMSPro:**  
Anh truy cập phân hệ **Quản lý Mua sắm ➔ Phiếu yêu cầu mua sắm** trên giao diện gAMSPro, chọn mã `PUR/2026/000052` để bổ sung danh mục hàng hóa, chủng loại và đơn giá thực tế.

2️⃣ **Bước 2 — Trình duyệt Tờ trình:**  
Nhấn nút **'Gửi phê duyệt'** ở góc trên màn hình. Hệ thống sẽ tự động chuyển Tờ trình đến Trưởng phòng Hỗ trợ và Đơn vị Chuyên môn (Phòng Hành chính / Khối QLVH) để ký duyệt số.

3️⃣ **Bước 3 — Theo dõi tiến độ phê duyệt qua AI Chatbot:**  
Bất kỳ lúc nào, anh chỉ cần nhắn cho tôi: *"Tờ trình PUR/2026/000052 đến cấp nào rồi?"* — Tôi sẽ tra cứu nhật ký xử lý (Workflow Audit Log) và báo cáo ngay cấp đang giữ hồ sơ.

> 💡 **Lưu ý nghiệp vụ:** Ngay khi Tờ trình hoàn tất phê duyệt, Đơn vị Mua sắm (ĐMMS) sẽ chọn Nhà cung cấp, lập Biên bản xét giá và phát hành Đơn đặt hàng PO. Lúc đó anh tiếp tục hỏi tôi để cập nhật tiến độ giao hàng nhé!"

---

**Người dùng (Anh Bảo):**  
"Cảm ơn bạn nhé!"

**Chatbot:**  
"Rất hân hạnh được hỗ trợ anh Bảo! Khi nào cần hỗ trợ tra cứu Tờ trình, Kế hoạch Ngân sách hay Hợp đồng PO trên gAMSPro, anh cứ nhắn cho tôi. Chúc anh một ngày làm việc hiệu quả tại BVBank!"

---

## 📊 TỔNG KẾT LUỒNG HỘI THOẠI & KĨ THUẬT TOOL CALL

| # | Câu hỏi của người dùng | Tool Call tương ứng | Dữ liệu gAMSPro trả về | Điểm nhấn Demo |
|:---:|:---|:---|:---|:---|
| **1** | *"Xem danh sách Tờ trình gần đây?"* | `search_request_docs` | Danh sách 19 tờ trình, lấy 3 tờ trình mới nhất | Phân loại trạng thái (Lưu Nháp / Đã duyệt) |
| **2** | *"Xem chi tiết PUR/2026/000052?"* | `get_request_doc_detail` | Thông tin người lập, số tiền, mã Kế hoạch liên kết | Phát hiện tờ trình chưa gửi, chủ động gợi ý check Ngân sách |
| **3** | *"Kiểm tra Kế hoạch liên kết?"* | `check_plan_budget_detail` | Hạn mức 35M, đã dùng 18M, còn dư 17M | Tự động đối soát tính sẵn có của Ngân sách (Budget Check) |
| **4** | *"Có PO nào chưa?"* | `get_po_master_status` | Trạng thái PO của Tờ trình & PO khác của đơn vị | Xâu chuỗi liên thông sang phân hệ Mua sắm & Giao hàng |
| **5** | *"Cần làm gì tiếp theo?"* | *(AI Knowledge / Guidance)* | Quy trình 3 bước hoàn tất Tờ trình gAMSPro | AI đóng vai trò Chuyên gia hướng dẫn hành động (Next-Best-Action) |

---

## 🚀 THÔNG ĐIỆP PITCHING CHỐT HẠ CHO BAN LÃNH ĐẠO (CLOSING PITCH)

* **Về Tốc độ Xử lý:** Tối ưu hóa thời gian tra cứu dữ liệu liên phân hệ từ **15 phút thao tác thủ công xuống dưới 2 giây**.
* **Về Độ Chính xác:** Loại bỏ 100% rủi ro ảo giác (Zero Hallucination) nhờ kết nối dữ liệu trực tiếp qua gAMSPro RESTful API.
* **Về An toàn Tài chính:** Tự động hóa khâu đối soát tuân thủ hạn mức ngân sách (Budget Compliance) ngay từ khi tạo Tờ trình.
* **Về Trải nghiệm Vận hành:** Chuyển đổi mô hình tra cứu thụ động thành Trợ lý Số chủ động hướng dẫn quy trình, chuẩn hóa trải nghiệm Self-service cho toàn thể Cán bộ Nhân viên BVBank.