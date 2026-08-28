from pathlib import Path
from langfuse import Langfuse
import pandas as pd

# Đường dẫn thư mục data/langfuse (tự động tạo nếu chưa có)
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "langfuse"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = DATA_DIR / "scores_export.csv"

langfuse = Langfuse(
    public_key="pk-lf-096410ce-6fd7-4b75-a825-0d3c1a3f86e1",
    secret_key="sk-lf-c5257d45-24cd-471d-8177-7ca18feb4838",
    host="http://localhost:3000"
)

# Lấy danh sách scores qua API v3 kèm các trường bổ sung: comment, metadata, traceId, subject
response = langfuse.api.scores_v3.get_many_v3(
    limit=100,
    fields="details,subject,annotation"
)

rows = []
for s in response.data:
    row = {
        "id": s.id,
        "name": s.name,
        "value": s.value,
        "dataType": s.data_type,
        "source": getattr(s.source, "value", str(s.source)) if s.source else None,
        "comment": s.comment,
        "createdAt": str(s.created_at),
        "environment": s.environment,
        "authorUserId": s.author_user_id,
        "subjectKind": s.subject.kind if s.subject else None,
        "subjectId": s.subject.id if s.subject else None,
        "traceId": getattr(s.subject, "trace_id", None) if s.subject else (s.subject.id if s.subject and s.subject.kind == "trace" else None),
    }
    rows.append(row)

df = pd.DataFrame(rows)
df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
print(f"✅ Đã xuất thành công {len(df)} dòng sang: {OUTPUT_FILE}")
