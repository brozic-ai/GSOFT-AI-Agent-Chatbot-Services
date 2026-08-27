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
        # Import models để SQLAlchemy Base nhận diện tất cả ORM models
        import app.modules.document.model  # noqa: F401
        import app.modules.chat.model  # noqa: F401
        import app.modules.faq_knowledge.model  # noqa: F401
        Base.metadata.create_all(bind=engine)
        _ensure_chat_conversation_columns()
        _ensure_chat_message_columns()
    except Exception as ex:
        logger.error(
            "[FAIL] Failed to initialize database connection: %s", ex, exc_info=True
        )
        raise ex


def _ensure_chat_conversation_columns() -> None:
    """Add conversation-management columns for databases created by older releases."""
    statements = [
        """
        IF COL_LENGTH('dbo.Conversations', 'IsPinned') IS NULL
        ALTER TABLE dbo.Conversations ADD IsPinned BIT NOT NULL
            CONSTRAINT DF_Conversations_IsPinned DEFAULT 0
        """,
        """
        IF COL_LENGTH('dbo.Conversations', 'PinnedAt') IS NULL
        ALTER TABLE dbo.Conversations ADD PinnedAt DATETIME2 NULL
        """,
        """
        IF COL_LENGTH('dbo.Conversations', 'TitleSource') IS NULL
        ALTER TABLE dbo.Conversations ADD TitleSource NVARCHAR(20) NOT NULL
            CONSTRAINT DF_Conversations_TitleSource DEFAULT 'default'
        """,
        """
        IF COL_LENGTH('dbo.Conversations', 'CreatedAt') IS NULL
        ALTER TABLE dbo.Conversations ADD CreatedAt DATETIME2 NULL
        """,
        """
        IF COL_LENGTH('dbo.Conversations', 'UpdatedAt') IS NULL
        ALTER TABLE dbo.Conversations ADD UpdatedAt DATETIME2 NULL
        """,
        """
        IF COL_LENGTH('dbo.Conversations', 'CreationTime') IS NOT NULL
        ALTER TABLE dbo.Conversations ALTER COLUMN CreationTime DATETIME2 NULL
        """,
        """
        IF COL_LENGTH('dbo.Conversations', 'UpdatedTime') IS NOT NULL
        ALTER TABLE dbo.Conversations ALTER COLUMN UpdatedTime DATETIME2 NULL
        """,
        """
        IF COL_LENGTH('dbo.Conversations', 'UpdatedTime') IS NOT NULL AND COL_LENGTH('dbo.Conversations', 'UpdatedAt') IS NOT NULL
        EXEC('UPDATE dbo.Conversations SET UpdatedAt = UpdatedTime WHERE UpdatedAt IS NULL')
        """,
        """
        IF COL_LENGTH('dbo.Conversations', 'CreationTime') IS NOT NULL AND COL_LENGTH('dbo.Conversations', 'CreatedAt') IS NOT NULL
        EXEC('UPDATE dbo.Conversations SET CreatedAt = CreationTime WHERE CreatedAt IS NULL')
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'IX_Conversations_User_Pinned_Updated'
              AND object_id = OBJECT_ID('dbo.Conversations')
        )
        CREATE INDEX IX_Conversations_User_Pinned_Updated
            ON dbo.Conversations(UserId, IsPinned, UpdatedAt)
        """,
    ]
    try:
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
        logger.info("[OK] Conversation schema is up to date.")
    except Exception as ex:
        logger.error("[FAIL] Failed to migrate conversation schema: %s", ex, exc_info=True)
        raise


def _ensure_chat_message_columns() -> None:
    """Ensure ChatMessages table columns are compatible with both old and new schema."""
    statements = [
        """
        IF COL_LENGTH('dbo.ChatMessages', 'CreationTime') IS NOT NULL
        ALTER TABLE dbo.ChatMessages ALTER COLUMN CreationTime DATETIME2 NULL
        """,
        """
        IF COL_LENGTH('dbo.ChatMessages', 'CreatedAt') IS NULL
        ALTER TABLE dbo.ChatMessages ADD CreatedAt DATETIME2 NULL
        """,
        """
        IF COL_LENGTH('dbo.ChatMessages', 'CreationTime') IS NOT NULL
          AND COL_LENGTH('dbo.ChatMessages', 'CreatedAt') IS NOT NULL
        EXEC('UPDATE dbo.ChatMessages SET CreatedAt = CreationTime WHERE CreatedAt IS NULL')
        """,
        """
        IF COL_LENGTH('dbo.ChatMessages', 'TraceId') IS NULL
        ALTER TABLE dbo.ChatMessages ADD TraceId NVARCHAR(100) NULL
        """,
        """
        IF COL_LENGTH('dbo.ChatMessages', 'FeedbackScore') IS NULL
        ALTER TABLE dbo.ChatMessages ADD FeedbackScore INT NULL
        """,
        """
        IF COL_LENGTH('dbo.ChatMessages', 'FeedbackReason') IS NULL
        ALTER TABLE dbo.ChatMessages ADD FeedbackReason NVARCHAR(255) NULL
        """,
        """
        IF COL_LENGTH('dbo.ChatMessages', 'FeedbackComment') IS NULL
        ALTER TABLE dbo.ChatMessages ADD FeedbackComment NVARCHAR(MAX) NULL
        """,
        """
        IF COL_LENGTH('dbo.ChatMessages', 'FeedbackAt') IS NULL
        ALTER TABLE dbo.ChatMessages ADD FeedbackAt DATETIME2 NULL
        """,
    ]
    try:
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
        logger.info("[OK] ChatMessages schema is up to date.")
    except Exception as ex:
        logger.error("[FAIL] Failed to migrate ChatMessages schema: %s", ex, exc_info=True)
        raise


def close_db() -> None:
    """
    Giải phóng SQLAlchemy engine connection pool khi ứng dụng shutdown.
    """
    engine.dispose()
    logger.info("[DONE] Database engine connections closed.")
