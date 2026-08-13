# 📖 User Story Demo — Procurement Agent (gAMSPro Chatbot BVBank)

> **Nhân vật:** Anh **Trương Quang Bảo** (Cán bộ Phòng Hỗ trợ — Hội sở BVBank)  
> **Mục tiêu:** Theo dõi toàn bộ hành trình Tờ trình mua sắm - Kế hoạch - Đơn hàng PO của đơn vị mình.

---

## PHẦN 1: TỜ TRÌNH NGHIỆP VỤ

---

**Người dùng:**  
"Cho tôi xem danh sách các Tờ trình mua sắm tôi đã lập gần đây."

**Chatbot** *(Gọi: search_request_docs)*:  
"Xin chào anh Bảo! Tôi đã tra cứu xong. Anh hiện có **19 Tờ trình** trên hệ thống gAMSPro. Dưới đây là các tờ trình gần nhất:

1. **PUR/2025/000052** — Trạng thái: Lưu Nháp (Chờ gửi phê duyệt) — 7,000,000 VND
2. **PUR/2026/000065** — Trạng thái: Lưu Nháp (Chờ gửi phê duyệt) — 7,000,000 VND
3. **PUR/2026/000021** — Trạng thái: Da phê duyệt — 45,000,000 VND

Anh muốn xem chi tiết tờ trình nào không?"

---

**Người dùng:**  
"Cho tôi xem chi tiết tờ trình PUR/2025/000052 đi."

**Chatbot** *(Gọi: get_request_doc_detail)*:  
"Đây là thông tin chi tiết **Tờ trình số PUR/2025/000052**:

| Thông tin | Nội dung |
|:---|:---|
| **Mã hệ thống** | TRRD00000269630 |
| **Người lập** | Trương Quang Bảo — Phòng Hỗ trợ |
| **Đơn vị** | Hội sở |
| **Tổng tiền đề xuất** | 7,000,000 VND |
| **Ngày lập** | 22/12/2025 |
| **Trạng thái** | Lưu Nháp (Chờ gửi phê duyệt) |
| **Lý do đề xuất** | Tăng nhận diện thương hiệu và thu hút khách hàng cho sản phẩm Z. |
| **Kế hoạch liên kết** | 0030/2025/TTr-0690905 |

Tờ trình này hiện **chưa được gửi đi phê duyệt**. Anh có muốn kiểm tra Kế hoạch liên kết `0030/2025/TTr-0690905` không?"

---

**Người dùng:**  
"Kiểm tra luôn đi."

---

## PHẦN 2: KẾ HOẠCH MUA SẮM

---

**Chatbot** *(Gọi: check_plan_budget_detail)*:  
"Tôi đã tra cứu **Tờ trình Kế hoạch số 0030/2025/TTr-0690905**. Kết quả:

| Thông tin | Nội dung |
|:---|:---|
| **Mã Kế hoạch** | 0030/2025/TTr-0690905 |
| **Tên Kế hoạch** | Kế hoạch mua sắm Trang thiết bị Marketing Q4/2025 |
| **Đơn vị lập** | Hội sở — Phòng Hỗ trợ |
| **Trạng thái** | Da phê duyệt |
| **Tổng hạn mức ngân sách** | 35,000,000 VND |
| **Ngày phê duyệt** | 15/12/2025 |

**Kết luận:** Kế hoạch đã được duyệt và hạn mức 35 triệu VND hoàn toàn đủ điều kiện để trình duyệt tờ trình 7 triệu này. Anh có muốn tra cứu thêm các Đơn hàng PO đã được tạo chưa?"

---

**Người dùng:**  
"Có PO nào được tạo ra chưa không?"

---

## PHẦN 3: ĐƠN ĐẶT HÀNG PO (Purchase Order)

---

**Chatbot** *(Gọi: get_po_master_status)*:  
"Hiện tại **chưa có Đơn đặt hàng PO nào** từ Tờ trình `PUR/2025/000052` vì tờ trình vẫn đang **Lưu Nháp** và chưa hoàn tất chu trình phê duyệt.

Tuy nhiên, các PO đang hoạt động tại Hội sở:

1. **PO-2026-008** — FPT Telecom — 28,000,000 VND  
   - Trạng thái: Da ký duyệt | Hạn giao: **20/08/2026**

2. **PO-2026-003** — Công ty TNHH ABC — 12,500,000 VND  
   - Trạng thái: Chờ giao hàng | Hạn giao: **30/08/2026**"

---

**Người dùng:**  
"Bây giờ tôi cần làm gì để Tờ trình được duyệt?"

---

## PHẦN 4: TƯ VẤN HÀNH ĐỘNG TIẾP THEO

---

**Chatbot** *(Tư vấn nghiệp vụ — không cần gọi tool)*:  
"Để Tờ trình **PUR/2025/000052** hoàn tất phê duyệt, anh cần **3 bước**:

**Bước 1 — Hoàn thiện nội dung Tờ trình:**  
Vào menu **Tờ trình Nghiệp vụ** trên gAMSPro → Tìm `PUR/2025/000052` → Bổ sung đầy đủ danh sách hàng hóa mua sắm vào bảng chi tiết.

**Bước 2 — Gửi Tờ trình lên cấp duyệt:**  
Nhấn nút **'Gửi phê duyệt'** → Hệ thống tự động thông báo đến Trưởng phòng Hỗ trợ để ký duyệt.

**Bước 3 — Theo dõi tiến độ phê duyệt:**  
Anh hỏi tôi: *'Tờ trình PUR/2025/000052 đến cấp nào rồi?'* — Tôi sẽ tra cứu và báo cáo ngay.

> Lưu ý: Khi Tờ trình duyệt xong, bộ phận DVMS sẽ lập Phương án chọn Nhà cung cấp và tạo Đơn đặt hàng PO. Lúc đó anh tiếp tục hỏi tôi để theo dõi tiến độ giao hàng!"

---

**Người dùng:**  
"Cảm ơn bạn nhé!"

**Chatbot:**  
"Không có gì anh Bảo! Khi nào có thắc mắc về Tờ trình, Kế hoạch hay Đơn hàng trên gAMSPro, anh cứ hỏi tôi nhé. Chúc anh làm việc hiệu quả!"

---

## TỔNG KẾT LUỒNG HỘI THOẠI

| # | Câu hỏi của người dùng | Tool được gọi | Kết quả trả về |
|:---:|:---|:---|:---|
| 1 | "Danh sách Tờ trình gần đây?" | `search_request_docs` | Danh sách 19 tờ trình với trạng thái |
| 2 | "Chi tiết PUR/2025/000052?" | `get_request_doc_detail` | Nội dung, số tiền, kế hoạch liên kết |
| 3 | "Kiểm tra Kế hoạch liên kết?" | `check_plan_budget_detail` | Đã duyệt, hạn mức 35 triệu |
| 4 | "Có PO nào chưa?" | `get_po_master_status` | Danh sách PO đang hoạt động |
| 5 | "Làm gì tiếp theo?" | *(Tư vấn nghiệp vụ — không tool)* | Hướng dẫn 3 bước trình duyệt |

**Tổng cộng:** 4 tool calls — Phủ trọn 3 phân hệ: Tờ trình -> Kế hoạch -> Mua sắm (PO)
