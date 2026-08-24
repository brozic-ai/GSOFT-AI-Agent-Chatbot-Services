"""
Module Guardrails & An toàn cho Hệ thống Multi-Agent AI (Enterprise Guardrails).

Cung cấp 2 tầng bảo vệ:
1. Input Guardrail: Phát hiện Prompt Injection, Jailbreak, tấn công SQLi, và câu hỏi thù địch/ngoài phạm vi.
2. Output Guardrail: Kiểm duyệt nội dung phản hồi, ngăn chặn rò rỉ API Keys, Passwords, Connection Strings.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Câu phản hồi an toàn chuẩn doanh nghiệp khi vi phạm Guardrail
SAFE_FALLBACK_MESSAGE = (
    "Xin lỗi, tôi là trợ lý AI chuyên trách của hệ thống BVBank và gAMSPro. "
    "Tôi chỉ có thể hỗ trợ các thông tin liên quan đến quy trình, quy chế ngân hàng "
    "và các nghiệp vụ mua sắm, hành chính nội bộ. Vui lòng đặt câu hỏi phù hợp với phạm vi hỗ trợ."
)

# ── 1. CÁC MẪU INPUT GUARDRAIL (Prompt Injection, Jailbreak, Tấn công) ──

_JAILBREAK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # A. Bỏ qua hướng dẫn / Lệnh hệ thống (English & Tiếng Việt)
    (
        re.compile(r"ignore\s+(all\s+)?(previous|prior|system)\s+instructions?", re.IGNORECASE),
        "prompt_injection_ignore_instructions",
    ),
    (
        re.compile(r"bỏ\s+qua\s+(toàn\s+bộ\s+|hết\s+)?(hướng\s+dẫn|chỉ\s+dẫn|quy\s+tắc|câu\s+lệnh)\s+(trước|cũ|ban\s+đầu)", re.IGNORECASE),
        "prompt_injection_ignore_instructions_vi",
    ),
    (
        re.compile(r"quên\s+(hết|toàn\s+bộ)\s+(các\s+)?(hướng\s+dẫn|quy\s+tắc|lệnh)\s+(trước|cũ)", re.IGNORECASE),
        "prompt_injection_forget_instructions_vi",
    ),

    # B. Yêu cầu tiết lộ System Prompt
    (
        re.compile(r"(reveal|print|show|dump|output)\s+(your\s+|the\s+)?(system\s+prompt|initial\s+instructions?|hidden\s+prompt)", re.IGNORECASE),
        "system_prompt_leakage_en",
    ),
    (
        re.compile(r"(tiết\s+lộ|in\s+ra|hiển\s+thị|cho\s+tôi\s+xem)\s+(system\s+prompt|lệnh\s+hệ\s+thống|hướng\s+dẫn\s+ban\s+đầu|prompt\s+ẩn)", re.IGNORECASE),
        "system_prompt_leakage_vi",
    ),

    # C. Chế độ bẻ khóa DAN / Developer Mode / Unrestricted
    (
        re.compile(r"(dan\s+mode|developer\s+mode|unrestricted\s+ai|jailbreak)", re.IGNORECASE),
        "jailbreak_dan_mode",
    ),
    (
        re.compile(r"từ\s+giờ\s+bạn\s+là\s+(một\s+ai\s+không\s+giới\s+hạn|hacker|nhân\s+vật\s+phản\s+diện)", re.IGNORECASE),
        "jailbreak_persona_vi",
    ),
    (
        re.compile(r"bạn\s+không\s+còn\s+bị\s+(giới\s+hạn|ràng\s+buộc|kiểm\s+soát)", re.IGNORECASE),
        "jailbreak_unrestricted_vi",
    ),
    (
        re.compile(r"hãy\s+đóng\s+vai\s+(một\s+)?(hacker|ai\s+vượt\s+rào|kẻ\s+gian)", re.IGNORECASE),
        "jailbreak_roleplay_attack_vi",
    ),

    # D. Tấn công SQL Injection vào Chatbot
    (
        re.compile(r"(UNION\s+SELECT|DROP\s+TABLE|DELETE\s+FROM|INSERT\s+INTO|1=1\s*--|OR\s+'1'='1')", re.IGNORECASE),
        "sqli_attempt",
    ),

    # E. Yêu cầu nội dung nguy hại / Tấn công bảo mật hệ thống
    (
        re.compile(r"(cách\s+tấn\s+công|hack\s+vào|xâm\s+nhập|phá\s+hoại)\s+(hệ\s+thống|máy\s+chủ|server|database|gAMSPro|BVBank)", re.IGNORECASE),
        "malicious_infrastructure_attack",
    ),
]

_SENSITIVE_OUTPUT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # A. API Keys (OpenAI, Gemini, Anthropic, HuggingFace)
    (re.compile(r"(sk-[a-zA-Z0-9_-]{20,})"), "openai_api_key"),
    (re.compile(r"(AIzaSy[a-zA-Z0-9_-]{30,40})"), "google_gemini_api_key"),
    (re.compile(r"(sk-ant-[a-zA-Z0-9_-]{20,})"), "anthropic_api_key"),
    (re.compile(r"(hf_[a-zA-Z0-9]{30,})"), "huggingface_token"),


    # B. Private Keys
    (re.compile(r"-----BEGIN\s+(RSA\s+|OPENSSH\s+|EC\s+)?PRIVATE\s+KEY-----"), "private_key_leak"),

    # C. Database Connection Strings (SQL Server, Oracle, PostgreSQL, MySQL, MongoDB, Redis)
    (
        re.compile(
            r"(Server|Data Source|Host|Database|Initial Catalog)\s*=\s*[^;]+;.*?(Password|Pwd)\s*=\s*[^;\s]+",
            re.IGNORECASE | re.DOTALL,
        ),
        "db_connection_string_leak",
    ),
    (
        re.compile(
            r"(Password|Pwd)\s*=\s*[^;\s]+;.*?(Server|Data Source|Host|Database|Initial Catalog)\s*=\s*[^;]+",
            re.IGNORECASE | re.DOTALL,
        ),
        "db_connection_string_leak",
    ),
    (
        re.compile(
            r"(mongodb(\+srv)?|postgresql|postgres|mysql|redis)://[^\s:]+:[^\s@]+@[^\s/]+",
            re.IGNORECASE,
        ),
        "db_uri_leak",
    ),

    # D. Mật khẩu dạng Plain Text (hỗ trợ cả có ngoặc và không ngoặc)
    (
        re.compile(r"(password|mật\s+khẩu|mat_khau|pwd)\s*[:=]\s*['\"]?[^\s'\";]{4,}['\"]?", re.IGNORECASE),
        "plaintext_password_leak",
    ),
]


@dataclass
class GuardrailResult:
    """Kết quả kiểm tra Guardrail."""
    is_safe: bool
    violation_type: Optional[str] = None
    fallback_message: Optional[str] = None
    sanitized_text: Optional[str] = None


class InputGuardrail:
    """Kiểm tra độ an toàn của câu hỏi đầu vào (Lớp 1 - Input Protection)."""

    @classmethod
    def validate(cls, query: str) -> GuardrailResult:
        """
        Kiểm tra câu hỏi người dùng trước khi gửi vào Supervisor Orchestrator.
        """
        if not query or not query.strip():
            return GuardrailResult(is_safe=True)

        normalized_query = query.strip()

        for pattern, violation_type in _JAILBREAK_PATTERNS:
            if pattern.search(normalized_query):
                logger.warning(
                    "[INPUT GUARDRAIL BLOCKED] Vi phạm '%s' trong câu hỏi: '%s'",
                    violation_type,
                    query[:100],
                )
                return GuardrailResult(
                    is_safe=False,
                    violation_type=violation_type,
                    fallback_message=SAFE_FALLBACK_MESSAGE,
                )

        return GuardrailResult(is_safe=True)


class OutputGuardrail:
    """Kiểm duyệt nội dung phản hồi trước khi gửi về người dùng (Lớp 2 - Output Protection)."""

    @classmethod
    def sanitize(cls, response_text: str) -> GuardrailResult:
        """
        Kiểm tra và ngăn chặn các nội dung rò rỉ thông tin nhạy cảm của hệ thống.
        """
        if not response_text or not response_text.strip():
            return GuardrailResult(is_safe=True, sanitized_text=response_text)

        for pattern, violation_type in _SENSITIVE_OUTPUT_PATTERNS:
            if pattern.search(response_text):
                logger.error(
                    "[OUTPUT GUARDRAIL BLOCKED] Phát hiện rò rỉ '%s' trong kết quả sinh ra của LLM!",
                    violation_type,
                )
                return GuardrailResult(
                    is_safe=False,
                    violation_type=violation_type,
                    fallback_message=SAFE_FALLBACK_MESSAGE,
                    sanitized_text=SAFE_FALLBACK_MESSAGE,
                )

        return GuardrailResult(is_safe=True, sanitized_text=response_text)
