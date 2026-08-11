import logging
import re
from collections.abc import Generator
from urllib.parse import quote_plus

import pyodbc
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


def build_database_url(conn_str: str) -> str:
    """
    Xây dựng SQLAlchemy URL từ ODBC Connection String.
    Tự động kiểm tra và chuyển đổi sang ODBC Driver có sẵn trên hệ thống nếu cần.
    """
    available_drivers = pyodbc.drivers()

    # Danh sách driver ưu tiên theo thứ tự từ mới đến cũ
    preferred_drivers = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "ODBC Driver 13 for SQL Server",
        "SQL Server",
    ]

    # Kiểm tra xem driver hiện tại trong conn_str có trên máy không
    driver_match = re.search(r"Driver=\{([^}]+)\}", conn_str, re.IGNORECASE)
    if driver_match:
        current_driver = driver_match.group(1)
        if current_driver not in available_drivers:
            fallback_driver = next(
                (d for d in preferred_drivers if d in available_drivers), None
            )
            if fallback_driver:
                logger.warning(
                    "[WARN] ODBC Driver '%s' không có sẵn. Tự động chuyển sang '%s'.",
                    current_driver,
                    fallback_driver,
                )
                conn_str = re.sub(
                    r"Driver=\{[^}]+\}",
                    f"Driver={{{fallback_driver}}}",
                    conn_str,
                    flags=re.IGNORECASE,
                )
            else:
                logger.warning(
                    "[WARN] Không tìm thấy ODBC Driver tương thích cho SQL Server trong pyodbc.drivers()."
                )
    else:
        fallback_driver = next(
            (d for d in preferred_drivers if d in available_drivers), None
        )
        if fallback_driver:
            if not conn_str.rstrip().endswith(";"):
                conn_str += ";"
            conn_str = f"Driver={{{fallback_driver}}};{conn_str}"
            logger.info("Tự động thêm ODBC Driver: %s", fallback_driver)

    encoded_params = quote_plus(conn_str)
    return f"mssql+pyodbc:///?odbc_connect={encoded_params}"


SQLALCHEMY_DATABASE_URL = build_database_url(settings.SQLSERVER_CONNECTIONSTRING)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    fast_executemany=True,
)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI Dependency trả về database Session cho từng request.
    Tự động đóng Session sau khi request kết thúc.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Khởi tạo và kiểm tra kết nối CSDL, tạo bảng nếu chưa có.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("[OK] Database connection established successfully.")
        # Import models để SQLAlchemy Base nhận diện tất cả ORM models (RagDocument, RagDocumentRole, IngestionTask, Conversation, ChatMessage)
        import app.modules.document.model  # noqa: F401
        import app.modules.chat.model  # noqa: F401
        Base.metadata.create_all(bind=engine)
    except Exception as ex:
        logger.error(
            "[FAIL] Failed to initialize database connection: %s", ex, exc_info=True
        )
        raise ex



def close_db() -> None:
    """
    Giải phóng SQLAlchemy engine connection pool khi ứng dụng shutdown.
    """
    engine.dispose()
    logger.info("[DONE] Database engine connections closed.")
