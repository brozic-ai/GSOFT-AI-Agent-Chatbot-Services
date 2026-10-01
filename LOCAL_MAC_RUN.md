# Chạy toàn bộ BVBank trên Mac bằng tay

Hướng dẫn này áp dụng cho ba repo trong `/Users/lenhat/Developer/BVBank` trên máy Mac hiện tại. Bạn tự chạy từng lệnh; Codex không tự khởi động dịch vụ. Quy trình chính dùng các container và database **đã chuẩn bị**. Mục cuối hướng dẫn dựng lại khi thiếu container.

## 1. Các thành phần và địa chỉ

| Thành phần | Nơi chạy | Địa chỉ trên Mac |
| --- | --- | --- |
| SQL Server cho ASP.NET, database `BVBLocal` | Colima `bvbank-chatbot` | `127.0.0.1:14333` |
| Chatbot FastAPI | Terminal trên Mac | `http://127.0.0.1:18080` |
| Backend ASP.NET Core 2.2 | Container `bvbank-local-backend` | `http://127.0.0.1:15000` |
| Frontend Angular 7 | Container `bvbank-local-angular` | `http://127.0.0.1:4200` |
| SQL, LLM, embedding, reranker, OCR và Langfuse của chatbot | Máy hạ tầng `172.20.0.59` | Theo `.env` chatbot |

**Quan trọng:** file `.env` chatbot hiện dùng SQL `172.20.0.59:1433` (database `gAMSPro_BVB_AI_V1_LIVE_04082026_1`), model API `172.20.0.59:8080` và Langfuse `172.20.0.59:3000`. SQL container trên Mac chỉ phục vụ backend ASP.NET. Các model trong `ollama list` của Mac **không được cấu hình để chạy chatbot**. Vì vậy đây là quy trình chạy đầy đủ giao diện → backend → chatbot theo hạ tầng hiện tại, nhưng chưa phải hệ thống offline hoàn toàn trên Mac. Repo này không có lệnh khởi động những model từ xa.

Không đưa mật khẩu/API key trong `.env` hoặc `appsettings.json` vào Git hay ảnh chụp. Không chạy `down --volumes`, `docker volume rm`, `colima delete` hoặc khôi phục đè database hiện có.

## 2. Kiểm tra trước khi khởi động

Mở Terminal thứ nhất:

```bash
cd /Users/lenhat/Developer/BVBank
command -v colima docker uv
test -f BVB.bak && echo 'Có BVB.bak'
test -f GSOFT-AI-Agent-Chatbot-Services/.env && echo 'Có .env chatbot'
test -f dev_asp.net/src/GSOFTcore.gAMSPro.Web.Host/appsettings.json && echo 'Có appsettings backend'
test -d dev_angular/node_modules && echo 'Có node_modules Angular'
colima list
```

Profile `bvbank-chatbot` hiện được cấp 8 GiB RAM. Angular 7 phải chạy bằng Node 12 trong container, không dùng Node mới trên Mac. Chỉ chạy một tiến trình Angular tại một thời điểm; build song song từng làm Colima hết RAM và dừng frontend với mã 137.

## 3. Kiểm tra các dịch vụ model và dữ liệu chatbot từ xa

Mac cần truy cập được máy `172.20.0.59` qua mạng/VPN phù hợp. Các lệnh sau chỉ kiểm tra:

```bash
curl -f --max-time 5 http://172.20.0.59:8080/v1/models
curl -f -o /dev/null -w 'Langfuse HTTP %{http_code}\n' --max-time 5 http://172.20.0.59:3000/
nc -vz -G 3 172.20.0.59 1433
```

`.env` hiện chọn `LLM_MODEL=Qwen3.5-4B-M-TS-Q4_K_M`; model server cũng công bố `bge-m3` và `bge-reranker-v2-m3`. HTTP 200 từ `/v1/models` chỉ chứng minh server đáp ứng, chưa chứng minh chatbot trả lời được. Nếu một dịch vụ từ xa tắt, phải chạy lại **trên máy hạ tầng theo quy trình của máy đó** trước khi tiếp tục.

## 4. Chạy Colima và SQL local

Luôn ghi rõ Docker context để tránh dùng nhầm Docker Desktop hoặc Colima `default`:

```bash
colima start --profile bvbank-chatbot
docker --context colima-bvbank-chatbot ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Nếu `bvbank-chatbot-local-sql-1` đang `Exited/Stopped`, chạy:

```bash
docker --context colima-bvbank-chatbot start bvbank-chatbot-local-sql-1
```

Nếu container đã `Up`, bỏ qua lệnh `start`. Chờ SQL sẵn sàng và kiểm tra database:

```bash
docker --context colima-bvbank-chatbot exec bvbank-chatbot-local-sql-1 sh -lc \
  '/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -h -1 -W -Q "SET NOCOUNT ON; SELECT name, state_desc FROM sys.databases WHERE name = N'\''BVBLocal'\''"'
```

Cần thấy `BVBLocal ONLINE`. Mật khẩu được đọc trong container, không in ra Terminal. Nếu thiếu container hoặc database, xem mục 10.

## 5. Chạy chatbot ở Terminal thứ hai

Nếu `lsof -nP -iTCP:18080 -sTCP:LISTEN` đã hiện một tiến trình, chatbot có thể đang chạy; kiểm tra health thay vì mở thêm tiến trình. Nếu chưa có, chạy:

```bash
cd /Users/lenhat/Developer/BVBank/GSOFT-AI-Agent-Chatbot-Services
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 18080
```

Giữ Terminal này mở. Mở một Terminal khác để kiểm tra:

```bash
curl -f http://127.0.0.1:18080/api/v1/health
```

Health HTTP 200 xác nhận API chạy, chưa xác nhận model hoặc SQL từ xa.

## 6. Chạy backend ở Terminal thứ ba

Kiểm tra khóa nội bộ giữa backend và chatbot **mà không in khóa**, đồng thời xác nhận background jobs local đã tắt:

```bash
cd /Users/lenhat/Developer/BVBank/GSOFT-AI-Agent-Chatbot-Services
uv run python - <<'PY'
import json
from pathlib import Path
from dotenv import dotenv_values

root = Path('/Users/lenhat/Developer/BVBank')
ai_key = dotenv_values(root / 'GSOFT-AI-Agent-Chatbot-Services/.env').get('REQUIRED_API_KEY')
backend = json.loads((root / 'dev_asp.net/src/GSOFTcore.gAMSPro.Web.Host/appsettings.json').read_text())
assert ai_key and ai_key == backend['AiApi']['InternalApiKey'], 'Hai API key không khớp'
assert str(backend['App']['DisableBackgroundJobs']).lower() == 'true', 'Chưa tắt background jobs local'
print('API key khớp; background jobs local đã tắt')
PY
```

Nếu `bvbank-local-backend` đã `Up`, bỏ qua lệnh sau. Nếu đang `Exited/Stopped`, chạy để vừa khởi động vừa xem log:

```bash
docker --context colima-bvbank-chatbot start -a bvbank-local-backend
```

Ở Terminal khác, kiểm tra:

```bash
curl -sS -o /dev/null -w 'Backend HTTP %{http_code}\n' --max-time 5 http://127.0.0.1:15000/
```

HTTP `302` ở `/` là phản hồi hiện tại và có thể chấp nhận. Nếu backend chưa có container hoặc code C# vừa đổi, xem cách publish ở mục 10.

## 7. Chạy frontend ở Terminal thứ tư

`dev_angular/src/environments/environment.ts` hiện trỏ backend tới `127.0.0.1:15000`. Nếu `bvbank-local-angular` đã `Up`, đừng mở thêm Angular. Nếu đang `Exited/Stopped`:

```bash
docker --context colima-bvbank-chatbot start -a bvbank-local-angular
```

Chờ log `Compiled successfully`, sau đó kiểm tra từ Terminal khác:

```bash
curl -sS -o /dev/null -w 'Frontend HTTP %{http_code}\n' --max-time 10 http://127.0.0.1:4200/
```

Cần HTTP `200`. Dòng `Angular Live Development Server is listening` chưa chứng minh bundle đã build xong. Nếu container thoát với mã 137, kiểm tra `docker --context colima-bvbank-chatbot inspect bvbank-local-angular --format '{{.State.OOMKilled}}'`; giải phóng RAM trước khi thử lại, không chạy `ng build` song song. Nếu chưa có container, xem mục 10.

### 7.1. Đã sửa code nhưng trình duyệt vẫn dùng bản cũ

Thư mục nguồn trên Mac được chia sẻ vào Colima/container. Angular có thể không nhận được thông báo file đã thay đổi, nên vẫn phục vụ JavaScript cũ dù source trong container đã đúng. Reload hoặc xóa cache trình duyệt không giúp nếu server vẫn trả bundle cũ. Chạy Angular với `--poll 2000` để kiểm tra file mỗi 2 giây.

Nếu container hiện có được tạo trước khi thêm `--poll 2000`, thực hiện **một lần** các lệnh sau. `docker start` hoặc `restart` không thay đổi lệnh khởi động đã lưu của container. Các lệnh chỉ thay container frontend; source và `node_modules` ở thư mục bind mount trên Mac được giữ lại.

```bash
docker --context colima-bvbank-chatbot stop bvbank-local-angular
docker --context colima-bvbank-chatbot rm bvbank-local-angular
docker --context colima-bvbank-chatbot run --name bvbank-local-angular \
  --network bvbank-chatbot-local_default -p 127.0.0.1:4200:4200 \
  -v /Users/lenhat/Developer/BVBank/dev_angular:/workspace \
  -w /workspace node:12-buster \
  node --max_old_space_size=6144 ./node_modules/@angular/cli/bin/ng serve \
  --host 0.0.0.0 --port 4200 --source-map=false --poll 2000
```

Giữ Terminal này mở và chờ `Compiled successfully`. Từ Terminal khác, kiểm tra **bundle thực tế** đang được phục vụ:

```bash
python3 - <<'PY'
from urllib.request import urlopen

url = 'http://127.0.0.1:4200/app-admin-admin-module.js'
with urlopen(url, timeout=60) as response:
    bundle = response.read().decode('utf-8')
old = '/api/v1/documents/upload'
new = '/api/v1/ai/documents/upload'
if old in bundle or new not in bundle:
    raise SystemExit('CHUA DAT: server van phuc vu bundle cu hoac bundle khong dung.')
print('DAT: bundle dang phuc vu da dung URL upload qua backend gateway.')
PY
```

Khi kiểm tra đạt, tải lại trang bằng `Cmd+Shift+R`, upload một file nhỏ và xem Network: request phải là `POST http://127.0.0.1:15000/api/v1/ai/documents/upload`. Sau phản hồi thành công, kiểm tra trạng thái xử lý trong danh sách tài liệu; nhận file thành công chưa xác nhận bước lập chỉ mục đã hoàn tất. Nếu C# vừa được sửa mà chưa publish, làm mục 10.2 trước. Những lần chạy sau dùng `start -a` như mục 7; container mới đã lưu tùy chọn polling.

## 8. Kiểm tra toàn bộ luồng trên trình duyệt

1. Mở `http://127.0.0.1:4200/account/login`, đăng nhập bằng tài khoản local đã dùng trước đó.
2. Để dashboard khoảng một phút, tải lại trang và kiểm tra vẫn đăng nhập.
3. Mở chatbot trên giao diện, gửi một câu hỏi, chờ câu trả lời hoàn chỉnh. Đây là phép thử frontend → backend `15000` → chatbot `18080` → SQL/model `172.20.0.59`.
4. Nếu cần xem trace, mở `http://172.20.0.59:3000` bằng tài khoản Langfuse của bạn.

Lưu ý: `scripts/chat_local.py --history` hiện **không gửi** `X-Internal-Api-Key`, nên với `REQUIRED_API_KEY` đang bật sẽ nhận **401**. Đây là giới hạn của script local sau khi code được hoàn tác; không dùng nó để kết luận dịch vụ hỏng. Có thể kiểm tra API được bảo vệ mà không tạo dữ liệu:

```bash
cd /Users/lenhat/Developer/BVBank/GSOFT-AI-Agent-Chatbot-Services
uv run python - <<'PY'
from dotenv import dotenv_values
import requests

key = dotenv_values('.env').get('REQUIRED_API_KEY')
assert key, 'Thiếu REQUIRED_API_KEY trong .env'
r = requests.get('http://127.0.0.1:18080/api/v1/chat/conversations',
                 headers={'X-User-Id': 'local-tester', 'X-Internal-Api-Key': key}, timeout=10)
print('Chatbot conversations HTTP', r.status_code)
r.raise_for_status()
PY
```

HTTP 200 ở đây chỉ xác nhận xác thực API; vẫn cần hỏi đáp trên giao diện để xác nhận luồng hoàn chỉnh.

## 9. Dừng dự án bằng tay

Nhấn `Ctrl-C` tại Terminal FastAPI. Nếu đang xem log bằng `docker start -a`, dùng Terminal khác để dừng container (Ctrl-C ở cửa sổ xem log không thay thế bước này):

```bash
docker --context colima-bvbank-chatbot stop bvbank-local-angular
docker --context colima-bvbank-chatbot stop bvbank-local-backend
docker --context colima-bvbank-chatbot stop bvbank-chatbot-local-sql-1
```

Chỉ khi không còn tác vụ khác dùng profile này:

```bash
colima stop --profile bvbank-chatbot
```

`stop` giữ nguyên container, volume và database. Quy trình này không tắt dịch vụ trên máy `172.20.0.59`.

## 10. Khi thiếu container hoặc cần build lại

Phần này dành cho lần dựng mới hoặc sau khi đổi code. Nếu ba container đã có, chỉ cần mục 4–9. Chạy build tuần tự khi frontend chưa chạy để tránh hết RAM.

### 10.1. SQL local mới

Nếu container SQL chưa tồn tại, thêm `MSSQL_SA_PASSWORD` vào `.env` chatbot (không ghi mật khẩu vào lệnh). Cần có `/Users/lenhat/Developer/BVBank/BVB.bak`. Sau đó:

```bash
cd /Users/lenhat/Developer/BVBank/GSOFT-AI-Agent-Chatbot-Services
docker --context colima-bvbank-chatbot compose --env-file .env \
  -f infra/docker/compose.local-chatbot.yml up -d sql
```

Chỉ khi đây là **volume mới và chưa có `BVBLocal`**, kiểm tra logical file names của backup:

```bash
docker --context colima-bvbank-chatbot exec bvbank-chatbot-local-sql-1 sh -lc \
  '/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -Q "RESTORE FILELISTONLY FROM DISK = N'\''/var/opt/mssql/backup/BVB.bak'\''"'
```

Backup hiện tại có logical data `gAMSPro_BVB_V4_LIVE_10032026_2` và log `gAMSPro_BVB_V4_LIVE_10032026_2_log`. Sau khi chắc chắn `BVBLocal` chưa tồn tại, restore:

```bash
cat > /tmp/bvbank-restore-local.sql <<'SQL'
RESTORE DATABASE [BVBLocal]
FROM DISK = N'/var/opt/mssql/backup/BVB.bak'
WITH MOVE N'gAMSPro_BVB_V4_LIVE_10032026_2' TO N'/var/opt/mssql/data/BVBLocal.mdf',
     MOVE N'gAMSPro_BVB_V4_LIVE_10032026_2_log' TO N'/var/opt/mssql/data/BVBLocal_log.ldf',
     STATS = 10;
GO
SQL
docker --context colima-bvbank-chatbot cp /tmp/bvbank-restore-local.sql \
  bvbank-chatbot-local-sql-1:/tmp/bvbank-restore-local.sql
docker --context colima-bvbank-chatbot exec bvbank-chatbot-local-sql-1 sh -lc \
  '/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -b -i /tmp/bvbank-restore-local.sql'
```

Không dùng `WITH REPLACE` hay chạy lại restore nếu database đã tồn tại. `.env` chatbot vẫn trỏ SQL **từ xa**; restore này chỉ tạo database cho backend.

### 10.2. Publish và tạo backend

Nếu backend đang chạy, trước tiên dừng bằng `docker --context colima-bvbank-chatbot stop bvbank-local-backend` để tránh lỗi ghi file vào cùng volume. Sau đó publish bằng .NET 2.2 trong container, không dùng .NET mới trên Mac:

```bash
docker --context colima-bvbank-chatbot volume create bvbank-local-nuget
docker --context colima-bvbank-chatbot volume create bvbank-local-backend-publish
docker --context colima-bvbank-chatbot run --rm \
  -v bvbank-local-nuget:/root/.nuget/packages \
  -v /Users/lenhat/Developer/BVBank/dev_asp.net:/src \
  -v bvbank-local-backend-publish:/out \
  -w /src mcr.microsoft.com/dotnet/core/sdk:2.2 \
  bash -lc 'dotnet publish src/GSOFTcore.gAMSPro.Web.Host/GSOFTcore.gAMSPro.Web.Host.csproj -c Release -o /out /p:BuildProjectReferences=true'
```

Nếu container backend đã tồn tại, dùng `start` ở mục 6. **Chỉ khi chưa có** `bvbank-local-backend`, tạo container bằng:

```bash
docker --context colima-bvbank-chatbot run --name bvbank-local-backend \
  --network bvbank-chatbot-local_default -p 127.0.0.1:15000:5000 \
  -v bvbank-local-backend-publish:/app \
  -v /Users/lenhat/Developer/BVBank/dev_asp.net/src/GSOFTcore.gAMSPro.Web.Host/appsettings.json:/app/appsettings.json:ro \
  -w /app -e ASPNETCORE_ENVIRONMENT=Development \
  -e ASPNETCORE_URLS=http://0.0.0.0:5000 \
  mcr.microsoft.com/dotnet/core/sdk:2.2 dotnet GSOFTcore.gAMSPro.Web.Host.dll
```

Lệnh `run` hiển thị log ở Terminal hiện tại. Dừng bằng `docker --context colima-bvbank-chatbot stop bvbank-local-backend` từ Terminal khác.

### 10.3. Cài thư viện và tạo frontend

Nếu thiếu `dev_angular/node_modules`, cài bằng Node 12 trong container:

```bash
docker --context colima-bvbank-chatbot run --rm \
  -v /Users/lenhat/Developer/BVBank/dev_angular:/workspace \
  -w /workspace node:12-buster npm ci
```

Lần cập nhật tài liệu này chưa chạy lại `npm ci`. Dự án Angular cũ có `node-sass`; nếu cài lỗi, đọc lỗi đầu tiên, không thêm `--force`. Nếu container frontend đã có, dùng `start` ở mục 7. **Chỉ khi chưa có** `bvbank-local-angular`, tạo bằng:

```bash
docker --context colima-bvbank-chatbot run --name bvbank-local-angular \
  --network bvbank-chatbot-local_default -p 127.0.0.1:4200:4200 \
  -v /Users/lenhat/Developer/BVBank/dev_angular:/workspace \
  -w /workspace node:12-buster \
  node --max_old_space_size=6144 ./node_modules/@angular/cli/bin/ng serve \
  --host 0.0.0.0 --port 4200 --source-map=false --poll 2000
```

Chờ `Compiled successfully`, rồi kiểm tra theo mục 8. Không mở thêm một lệnh Angular khác cùng lúc.

## 11. Xử lý các lỗi thường gặp

| Triệu chứng | Kiểm tra đầu tiên |
| --- | --- |
| Docker Desktop không thấy image/container | Đang dùng Colima context riêng; chạy `docker --context colima-bvbank-chatbot ps -a` và `docker --context colima-bvbank-chatbot images`. |
| `chat_local.py --history` trả 401 | Script thiếu `X-Internal-Api-Key` như mục 8. Kiểm tra API bằng đoạn lệnh có header trong mục đó. |
| Giao diện chat trả 401 | Đối chiếu `AiApi:InternalApiKey` với `REQUIRED_API_KEY` bằng bước đầu mục 6; không in khóa ra log. |
| Giao diện chat trả 503 hoặc báo lỗi kết nối | Kiểm tra chatbot health ở mục 5, sau đó máy model/SQL từ xa ở mục 3. Xem log backend bằng lệnh bên dưới. |
| Angular không mở được hoặc container `Exited (137)` | Xem mục 7; kiểm tra RAM của Colima, không chạy hai build Angular cùng lúc. |
| Upload vẫn gọi `/api/v1/documents/upload` và trả 404 sau khi sửa source | Bundle Angular đang cũ. Làm mục 7.1 để bật polling và kiểm tra bundle thực tế trước khi reload trình duyệt. |
| Đăng nhập xong quay lại trang login | Kiểm tra `App:IdleLoginTimeout` trong `appsettings.json` backend và log backend; cấu hình local hiện là `1800000` ms. |

Xem log container mà không khởi động thêm dịch vụ:

```bash
docker --context colima-bvbank-chatbot logs --tail 100 bvbank-local-backend
docker --context colima-bvbank-chatbot logs --tail 100 bvbank-local-angular
docker --context colima-bvbank-chatbot logs --tail 100 bvbank-chatbot-local-sql-1
```

Lưu ý các log ứng dụng có thể chứa dữ liệu nghiệp vụ; xem tại máy, không dán nguyên log công khai khi có thông tin nhạy cảm.
