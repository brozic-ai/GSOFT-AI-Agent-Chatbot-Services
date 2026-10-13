# Chống trùng file khi import tài liệu RAG

SHA-256 so sánh bytes của file trong cùng tenant. Tên, danh mục và phòng ban không làm thay đổi khóa chống trùng. Host dùng scope `host`, tenant dùng `tenant:<id>`; scope và danh tính được gateway lấy từ phiên ABP, không từ frontend.

## Hành vi

Modal import giữ nguyên các dòng được chọn. Bấm **Kiểm tra tài liệu trùng**, xem các trạng thái Mới / Trùng trong danh sách / Đã có / Đang xử lý / Có thể retry / Kiểm tra lỗi, rồi **Import các file mới**. SHA-256 được đọc theo từng phần 1 MB, hỗ trợ HTTP nội bộ. File 0 byte hoặc lớn hơn 50 MB không được nhận.

Gateway đăng ký metadata, roles và fingerprint trong một transaction Python/SQL Server trước khi chuyển file staging sang nơi lưu chính thức. HTTP 409 trả mã `DUPLICATE`, `IN_PROGRESS`, `RETRY_AVAILABLE`; các trường documentId và documentName chỉ có khi người gọi có quyền xem. Bản sao không tạo thêm ingestion.

Response upload giữ `{status, documentId}` và thêm `ingestStatus: Pending`; đây là đã tiếp nhận. UI poll mỗi 3 giây đến Completed/Failed. Mất kết nối không chứng minh xử lý thất bại.

Retry chỉ nhận Failed và dùng file nguồn đã lưu, kiểm tra hash, giữ cùng documentId/metadata/roles. Mất nguồn trả SOURCE_MISSING; nguồn khác bytes trả SOURCE_CHANGED. Database đổi trạng thái Failed → Pending có điều kiện và cấp attemptId mới. Mỗi documentId/attemptId chỉ có một IngestionTask. Mọi callback và thay bộ chunks kiểm tra attempt hiện hành; chunks được thay trong transaction theo documentId, không theo tên file.

Tác vụ nền vẫn ở trong bộ nhớ. Sau restart hoặc kết quả gửi tác vụ không xác định, quản trị viên phải xác minh worker cũ đã dừng và không có tác vụ còn chạy trước khi chuyển tài liệu kẹt sang Failed rồi retry. Không tự thu hồi attempt dựa trên timeout.

## Triển khai và backfill

1. Tạm dừng import/retry trong thời gian cập nhật gateway và Python để tránh dùng hai phiên bản contract khác nhau.
2. Chạy `infra/docker/document-fingerprints.sql`, hoặc để `init_db()` áp dụng migration khi Python khởi động. Script có thể chạy lại; bổ sung cột trên bảng cũ, không chỉ `create_all()`.
3. Triển khai gateway, Python và frontend cùng phiên bản. Gateway giữ yêu cầu đăng nhập hiện có; Python kiểm tra tenant và quyền từng tài liệu bằng ngữ cảnh tin cậy từ gateway. MVP không yêu cầu cấp thêm quyền ABP cho vai trò đang sử dụng màn hình. Backfill yêu cầu vai trò Admin đã được hệ thống xác định.
4. Với phiên đăng nhập quản trị viên trong tenant cần xử lý, gọi `POST /api/v1/ai/documents/fingerprints/backfill` với `{ "cursor": 0, "dryRun": true }`. Đọc báo cáo rồi gọi với `dryRun: false`.
5. Tiếp tục dùng `nextCursor` khi `hasMore: true`. Mỗi lô tối đa 100 tài liệu. Dry-run trả hash để tổng hợp nhóm trùng qua các lô; không ghi hash hoặc metadata. Lượt ghi trả canonicalDocumentId/copies. Báo cáo coverage cho biết tổng số tài liệu, có hash và chưa có hash.
6. Giữ nguyên các bản sao cũ. Đại diện ưu tiên Completed, sau đó Pending/Processing, rồi Failed; ID nhỏ nhất thắng trong cùng mức. Khi xóa đại diện, khóa chuyển sang bản sao còn lại trong transaction. File nguồn dùng chung được giữ khi bản ghi khác còn tham chiếu cùng đường dẫn.
7. File thiếu hoặc không đọc được được báo SOURCE_MISSING/UNREADABLE_SOURCE. Những tài liệu này chưa được bảo vệ bằng hash cho đến khi phục hồi nguồn và chạy lại backfill. File upload qua gateway được đọc tại gateway; đường dẫn tuyệt đối do script đăng ký được đọc trên host Python qua API nội bộ. Retry cũng sử dụng đúng host lưu nguồn; không nhận đường dẫn từ browser.
8. Giữ `RAG_REQUIRE_FILE_SHA256=true` (mặc định) trước khi mở lại import. `false` chỉ nới hợp đồng đăng ký metadata cho giai đoạn chuyển đổi; ingestion vẫn bắt buộc đăng ký documentId/attemptId và xác minh hash, nên không mở import với caller cũ.

Backfill báo cáo theo tenant, không tự xóa bản sao, không tự sửa quyền và không chạy OCR/embedding. Dọn staging chỉ xóa file do request tạo; Roxy giữ nguyên file tạm nguồn. Hỗ trợ Roxy giới hạn thư mục tạm của người dùng hiện hành, kể cả kiểm tra đường dẫn sau chuẩn hóa.

Giám sát bằng log có cấu trúc: đếm `event=import_conflict` với mã DUPLICATE/IN_PROGRESS/RETRY_AVAILABLE để theo dõi số lần chặn; đối chiếu `retry_accepted` với `ingestion_completed`/`ingestion_failed` bằng tenant, document và attempt để theo dõi retry; đếm `backfill_error` theo mã lỗi. Trace ID được gateway truyền tới pipeline. Coverage trong báo cáo backfill thể hiện độ phủ dữ liệu cũ trước khi mở import.

## API và công cụ

- `POST /api/v1/ai/documents/duplicate-check`: `{files:[{fileId,sha256,fileSize}]}`, tối đa 100 phần tử, trả `{results:[...]}`.
- `/upload`: multipart hoặc JSON Roxy như trước. Endpoint tạo metadata công khai của gateway yêu cầu dùng `/upload` để hash được tính từ file thật.
- `GET /{id}/ingestion-status`: chỉ trả trạng thái, tiến độ và lỗi. Người tạo upload được theo dõi ngay cả khi chọn vai trò mà họ không thuộc về; không cấp thêm quyền xem nội dung hoặc metadata.
- `POST /{id}/retry`: không nhận file hoặc thay đổi metadata từ client.
- API Python nội bộ bổ sung `file_sha256`, trả `attemptId`; `/upload` kiểm tra documentId/attemptId và hash bytes trước khi xếp ingestion. Header X-Internal-Api-Key tiếp tục bắt buộc theo cấu hình triển khai; các endpoint nội bộ không được mở trực tiếp cho browser.
- Script: `rtk proxy uv run python scripts/upload_documents.py --folder my_documents --tenant 1`. Bỏ `--tenant` để dùng host. `--force` được giữ cho tương thích nhưng không tạo bản sao; retry tài liệu Failed từ UI bằng file đã lưu. Script không ingest sau lỗi đăng ký metadata và phân biệt Accepted/Processing với Completed.

## Kiểm thử đã bổ sung

Python/API và SQL Server thật (tự tạo rồi xóa schema `test_fingerprint_*`, không sửa dbo):

```sh
rtk proxy env BV_RUN_SQLSERVER_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_document_fingerprints.py -v
```

Gateway (SDK .NET 10 dùng cho harness; link trực tiếp service/client/identity production, upstream giả lập và file trong thư mục tạm):

```sh
rtk proxy dotnet run --project tests/DocumentImport/DocumentImport.csproj
```

Angular (TypeScript/component thật, shim framework và FileReader; không cần Karma cũ):

```sh
rtk proxy npm run test:document-import
rtk proxy ./node_modules/.bin/tsc --noEmit -p src/tsconfig.json
```

Build bundle Angular JIT đã chạy thành công với Node 16.20.2, không đổi runtime hệ thống:

```sh
rtk proxy npm exec --yes --package=node@16.20.2 -- node --max_old_space_size=8192 ./node_modules/@angular/cli/bin/ng build --aot=false --build-optimizer=false --source-map=false --progress=false --output-path=/tmp/bvbank-angular-dist
```

Kiểm thử concurrency dùng connection SQL Server độc lập; schema thử được dọn sau test. Build host .NET vẫn target netcoreapp2.2 hiện có và đã qua với warning từ project cũ. Node 25 của máy hiện tại không chạy được webpack/CLI Angular 7; full AOT đã vượt giới hạn heap trong lần kiểm tra riêng. Bundle JIT và template parsing đã được kiểm tra; build production/AOT và UAT qua browser với hệ thống đăng nhập thật cần tiếp tục trong môi trường triển khai. Migration và backfill dữ liệu thật chưa được chạy bởi các kiểm thử này.
