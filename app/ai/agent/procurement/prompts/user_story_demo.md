# 📖 User Story & Demo Script — Procurement Agent (gAMSPro Chatbot BVBank)

> **Nhân vật:** Anh **Trương Quang Bảo** (Cán bộ Phòng Hỗ trợ — Hội sở BVBank)  
> **Mục tiêu:** Theo dõi toàn bộ hành trình Tờ trình mua sắm ➔ Kế hoạch ngân sách ➔ Đơn hàng PO của đơn vị mình.  
> **Định vị:** Trợ lý AI Enterprise hỗ trợ self-service 24/7, liên thông dữ liệu chuẩn xác 100% từ Core gAMSPro.

---

## 🎯 5 ĐIỂM BVBANK CHÚ TRỌNG NHẤT (GIÁ TRỊ CỐT LÕI)

1. **Kiểm soát Ngân sách & Tuân thủ Hạn mức (Budget Compliance):**
   - Đảm bảo Tờ trình mua sắm không vượt hạn mức Kế hoạch đã duyệt. AI tự động đối soát số tiền đề xuất với số dư ngân sách.
2. **Truy vết Liên thông End-to-End (Cross-module Traceability):**
   - Xâu chuỗi 3 phân hệ: `Tờ trình` ➔ `Kế hoạch Mua sắm` ➔ `Đơn hàng PO`. CBNV không cần chuyển nhiều màn hình thủ công.
3. **Tuyệt đối Không Ảo giác (Zero Hallucination):**
   - Mọi dữ liệu (mã tờ trình, số tiền, ngày duyệt, tiến độ PO) 100% truy vấn trực tiếp từ API gAMSPro thông qua Tool Calls.
4. **Tư vấn Hướng hành động (Actionable AI / Next-Best-Action):**
   - AI không chỉ trả lời dữ liệu tĩnh mà hướng dẫn cụ thể các bước tiếp theo để hoàn thành quy trình phê duyệt.
5. **Tối ưu SLA & Trải nghiệm Cán bộ (Self-service Operations):**
   - Giảm 70% cuộc gọi hỏi tiến độ giữa các phòng ban, trả lời tức thì trong < 2 giây.

---

## PHẦN 1: TỜ TRÌNH NGHIỆP VỤ (PROCUREMENT PROPOSAL)

**Người dùng:**  
"Cho tôi xem danh sách các Tờ trình mua sắm tôi đã lập gần đây."

**Chatbot** *(Gọi tool: `search_request_docs`)*:  
"Xin chào anh Bảo! Tôi đã tra cứu trên hệ thống gAMSPro. Anh hiện có **19 Tờ trình**. Dưới đây là các tờ trình gần nhất:

1. **PUR/2025/000052** — Trạng thái: **Lưu Nháp** (Chờ gửi phê duyệt) — **7,000,000 VND**
2. **PUR/2026/000065** — Trạng thái: **Lưu Nháp** (Chờ gửi phê duyệt) — **7,000,000 VND**
3. **PUR/2026/000021** — Trạng thái: **Đã phê duyệt** — **45,000,000 VND**

Anh muốn xem chi tiết tờ trình nào không?"

---

**Người dùng:**  
"Cho tôi xem chi tiết tờ trình PUR/2025/000052 đi."

**Chatbot** *(Gọi tool: `get_request_doc_detail`)*:  
"Đây là thông tin chi tiết **Tờ trình số PUR/2025/000052**:

| Thông tin | Nội dung |
|:---|:---|
| **Mã hệ thống** | TRRD00000269630 |
| **Người lập** | Trương Quang Bảo — Phòng Hỗ trợ |
| **Đơn vị** | Hội sở BVBank |
| **Tổng tiền đề xuất** | **7,000,000 VND** |
| **Ngày lập** | 22/12/2025 |
| **Trạng thái** | ⚠️ **Lưu Nháp** (Chờ gửi phê duyệt) |
| **Lý do đề xuất** | Tăng nhận diện thương hiệu và thu hút khách hàng cho sản phẩm Z. |
| **Kế hoạch liên kết** | 📌 `0030/2025/TTr-0690905` |

Tờ trình này hiện **chưa được gửi đi phê duyệt**. Anh có muốn kiểm tra Hạn mức Ngân sách của Kế hoạch liên kết `0030/2025/TTr-0690905` không?"

---

## PHẦN 2: KẾ HOẠCH MUA SẮM & ĐỐI SOÁT NGÂN SÁCH

**Người dùng:**  
"Kiểm tra luôn đi."

**Chatbot** *(Gọi tool: `check_plan_budget_detail`)*:  
"Tôi đã tra cứu **Tờ trình Kế hoạch số 0030/2025/TTr-0690905**. Kết quả:

| Thông tin | Nội dung |
|:---|:---|
| **Mã Kế hoạch** | `0030/2025/TTr-0690905` |
| **Tên Kế hoạch** | Kế hoạch mua sắm Trang thiết bị Marketing Q4/2025 |
| **Đơn vị lập** | Hội sở — Phòng Hỗ trợ |
| **Trạng thái** | ✅ **Đã phê duyệt** |
| **Tổng hạn mức ngân sách** | **35,000,000 VND** |
| **Ngày phê duyệt** | 15/12/2025 |

🟢 **ĐÁNH GIÁ TỰ ĐỘNG:** Kế hoạch đã được duyệt và hạn mức **35,000,000 VND** hoàn toàn đủ điều kiện ngân sách để trình duyệt Tờ trình 7,000,000 VND này.

Anh có muốn tra cứu thêm tiến độ các Đơn hàng PO đã được tạo không?"

---

## PHẦN 3: ĐƠN ĐẶT HÀNG PO (PURCHASE ORDER)

**Người dùng:**  
"Có PO nào được tạo ra chưa không?"

**Chatbot** *(Gọi tool: `get_po_master_status`)*:  
"Hiện tại **chưa có Đơn đặt hàng PO nào** từ Tờ trình `PUR/2025/000052` vì tờ trình vẫn đang ở trạng thái **Lưu Nháp** và chưa hoàn tất chu trình phê duyệt.

🚚 **Tuy nhiên, các Đơn hàng PO khác đang hoạt động tại Hội sở:**

1. 🔹 **PO-2026-008** — FPT Telecom — **28,000,000 VND**  
   - Trạng thái: ✅ Đã ký duyệt | Hạn giao hàng: **20/08/2026**

2. 🔹 **PO-2026-003** — Công ty TNHH ABC — **12,500,000 VND**  
   - Trạng thái: 🚚 Chờ giao hàng | Hạn giao hàng: **30/08/2026**"

---

## PHẦN 4: TƯ VẤN HÀNH ĐỘNG TIẾP THEO (NEXT-BEST-ACTION)

**Người dùng:**  
"Bây giờ tôi cần làm gì để Tờ trình được duyệt?"

**Chatbot** *(Tư vấn nghiệp vụ AI — Không cần gọi tool)*:  
"Để Tờ trình **PUR/2025/000052** hoàn tất phê duyệt và tạo PO, anh Bảo cần thực hiện **3 bước**:

1️⃣ **Bước 1 — Hoàn thiện nội dung Tờ trình:**  
Vào menu **Tờ trình Nghiệp vụ** trên gAMSPro ➔ Tìm `PUR/2025/000052` ➔ Bổ sung đầy đủ danh sách hàng hóa mua sắm vào bảng chi tiết.

2️⃣ **Bước 2 — Gửi Tờ trình lên cấp duyệt:**  
Nhấn nút **'Gửi phê duyệt'** ➔ Hệ thống tự động chuyển thông báo đến Trưởng phòng Hỗ trợ để ký duyệt.

3️⃣ **Bước 3 — Theo dõi tiến độ phê duyệt:**  
Anh hỏi tôi: *'Tờ trình PUR/2025/000052 đến cấp nào rồi?'* — Tôi sẽ tra cứu và báo cáo ngay.

> 💡 **Lưu ý nghiệp vụ:** Khi Tờ trình duyệt xong, bộ phận DVMS sẽ lập Phương án chọn Nhà cung cấp và tạo Đơn đặt hàng PO. Lúc đó anh tiếp tục hỏi tôi để theo dõi tiến độ giao hàng!"

---

**Người dùng:**  
"Cảm ơn bạn nhé!"

**Chatbot:**  
"Không có gì anh Bảo! Khi nào có thắc mắc về Tờ trình, Kế hoạch hay Đơn hàng trên gAMSPro, anh cứ hỏi tôi nhé. Chúc anh làm việc một ngày hiệu quả!"

---

## 📊 TỔNG KẾT LUỒNG HỘI THOẠI & KĨ THUẬT TOOL CALL

| # | Câu hỏi của người dùng | Tool được gọi | Kết quả trả về | Điểm nhấn Demo |
|:---:|:---|:---|:---|:---|
| **1** | *"Danh sách Tờ trình gần đây?"* | `search_request_docs` | 19 tờ trình kèm trạng thái | Phân loại trực quan Lưu Nháp / Đã Duyệt |
| **2** | *"Chi tiết PUR/2025/000052?"* | `get_request_doc_detail` | Nội dung, số tiền, mã Kế hoạch | Tự động phát hiện & gợi ý check Kế hoạch |
| **3** | *"Kiểm tra Kế hoạch liên kết?"* | `check_plan_budget_detail` | Hạn mức 35M VND, đã duyệt | Auto-check tính sẵn có của Ngân sách |
| **4** | *"Có PO nào chưa?"* | `get_po_master_status` | Danh sách PO đang hoạt động | Xâu chuỗi sang phân hệ Mua sắm (PO) |
| **5** | *"Làm gì tiếp theo?"* | *(Tư vấn nghiệp vụ AI)* | Hướng dẫn 3 bước trình duyệt | AI đóng vai Chuyên gia tư vấn quy trình |

**Tổng cộng:** 4 tool calls — Phủ trọn 3 phân hệ liên thông: `Tờ trình` ➔ `Kế hoạch` ➔ `Mua sắm (PO)`

---

## 🚀 THÔNG ĐIỆP PITCHING CHỐT HẠ CHO BAN LÃNH ĐẠO (CLOSING PITCH)

- **Về Tốc độ:** Giảm thời gian tra cứu liên phân hệ từ **15 phút xuống 3 giây**.
- **Về Độ chính xác:** Dữ liệu chuẩn xác 100% từ Core gAMSPro, loại bỏ hoàn toàn rủi ro ảo giác AI.
- **Về An toàn Tài chính:** Tự động kiểm soát hạn mức ngân sách ngay từ khâu Tờ trình.
- **Về Trải nghiệm:** Chuyển đổi mô hình tra cứu thụ động thành Trợ lý Số hướng dẫn hành động thông minh.
