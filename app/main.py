import os
from fastapi import FastAPI
from app.routers.router import api_router

project_name = os.getenv("PROJECT_NAME", "Chatbot BVBank AI Service")

app = FastAPI(
    title=project_name,
    version="0.1.0",
    description="Dịch vụ Backend AI Agent xử lý LLM, Agentic RAG và Multi-Agent.",
)

# Đăng ký Router tổng chuẩn hóa theo phiên bản API v1
app.include_router(api_router, prefix="/api/v1")

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint trả về thông tin tổng quan và trang API Docs."""
    return {
        "message": f"Welcome to {project_name}",
        "status": "online",
        "docs_url": "/docs",
        "health_check": "/api/v1/health",
    }

@app.on_event("startup")
async def startup_event():
    print(f"🚀 Application '{project_name}' started successfully.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
