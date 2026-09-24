"""
Service xử lý Speech-to-Text (STT) sử dụng Google Gemini Multimodal Audio API.
Chuyển đổi âm thanh ghi từ trình duyệt (.webm, .wav, .mp3, .mp4, .ogg) thành văn bản tiếng Việt chính xác.
"""

import base64
import logging
from typing import Optional
import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class TranscribeService:
    """Service chuyển đổi âm thanh thành văn bản qua Gemini API."""

    def __init__(self, api_key: Optional[str] = None):
        self.settings = get_settings()
        self.api_key = api_key or self.settings.GEMINI_API_KEY

    async def transcribe(self, audio_bytes: bytes, content_type: str = "audio/webm") -> str:
        """
        Gửi audio bytes lên Gemini Multimodal Audio API để trích xuất văn bản tiếng Việt.
        """
        if not self.api_key:
            logger.error("[STT] GEMINI_API_KEY is not configured in settings.")
            raise ValueError("GEMINI_API_KEY chưa được cấu hình trong hệ thống.")

        if not audio_bytes or len(audio_bytes) < 100:
            logger.warning("[STT] Audio bytes too small or empty (len=%d)", len(audio_bytes) if audio_bytes else 0)
            return ""

        # Chuẩn hóa MimeType tương thích với Gemini
        mime_type = "audio/webm"
        if "wav" in content_type.lower():
            mime_type = "audio/wav"
        elif "mp4" in content_type.lower() or "m4a" in content_type.lower() or "aac" in content_type.lower():
            mime_type = "audio/mp4"
        elif "mp3" in content_type.lower() or "mpeg" in content_type.lower():
            mime_type = "audio/mp3"
        elif "ogg" in content_type.lower():
            mime_type = "audio/ogg"
        elif "webm" in content_type.lower():
            mime_type = "audio/webm"

        base64_audio = base64.b64encode(audio_bytes).decode("utf-8")

        prompt = (
            "Bạn là hệ thống chuyển đổi giọng nói tiếng Việt thành văn bản (Speech-to-Text).\n"
            "NHIỆM VỤ: Lắng nghe đoạn âm thanh được cung cấp và phiên âm chính xác thành văn bản tiếng Việt.\n"
            "QUY TẮC BẮT BUỘC:\n"
            "1. Nếu đoạn âm thanh là khoảng lặng, im lặng, chỉ có tiếng thở, tiếng rè microphone, tạp âm môi trường hoặc KHÔNG CÓ TIẾNG NGƯỜI NÓI RÕ RÀNG: BẮT BUỘC chỉ trả về duy nhất từ khóa: [NO_SPEECH]. Tuyệt đối không suy đoán, không bịa từ, không lặp lại bất kỳ từ ngữ nào trong hướng dẫn này.\n"
            "2. Nếu có tiếng người nói thực sự: Hãy phiên âm trung thực, chuẩn chính tả tiếng Việt. Nếu người nói nhắc đến các thuật ngữ chuyên ngành (như gAMSPro, tờ trình, PO, hợp đồng, ngân sách, phân bổ, khấu hao...) thì viết đúng thuật ngữ đó.\n"
            "3. Chỉ trả về nội dung phiên âm (hoặc [NO_SPEECH]), không thêm lời chào, không giải thích, không kèm dấu ngoặc kép hay ghi chú thừa."
        )

        configured_model = getattr(self.settings, "GEMINI_MODEL", "gemini-3.5-flash-lite") or "gemini-3.5-flash-lite"
        models_to_try = [
            "gemini-3.5-flash-lite",
            "gemini-3.5-transcribe",
            "gemini-3.1-flash-lite",
            configured_model,
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
        ]
        # Loại bỏ các model trùng lặp nhưng giữ nguyên thứ tự ưu tiên
        models_to_try = list(dict.fromkeys(models_to_try))

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64_audio,
                            }
                        },
                        {
                            "text": prompt,
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 2048,
            },
        }

        last_error = None
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        # Danh sách token biểu thị im lặng / không có tiếng nói
        silence_tokens = {
            "", "[no_speech]", "no_speech", "<noise>", "[blank_audio]",
            "none", "n/a", "...", "null", "[silence]", "silence",
            "im lặng", "không có tiếng nói", "không nghe rõ"
        }

        async with httpx.AsyncClient(timeout=35.0) as client:
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                try:
                    logger.info("[STT] Calling Gemini model '%s' (audio size: %d bytes, mime: %s)", model_name, len(audio_bytes), mime_type)
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            text_result = "".join(p.get("text", "") for p in parts).strip()

                            # Làm sạch dấu ngoặc kép hoặc ký tự bao quanh nếu có
                            if text_result.startswith(('"', "'", "`")) and text_result.endswith(('"', "'", "`")) and len(text_result) > 2:
                                text_result = text_result[1:-1].strip()

                            cleaned_lower = text_result.lower().strip()

                            # 1. Phát hiện im lặng / không có giọng nói -> Dừng ngay, KHÔNG fallback sang model khác
                            if cleaned_lower in silence_tokens:
                                logger.info("[STT] Model '%s' detected silence / no speech in audio.", model_name)
                                return ""

                            # 2. Chống ảo giác rò rỉ từ khóa ví dụ trong prompt:
                            # Nếu kết quả chỉ có độc nhất từ 'gamspro' mà không có ngữ cảnh đi kèm, đây là ảo giác trên audio im lặng
                            if cleaned_lower in ["gamspro", "gamspro.", "gamspro!", "gamspro?", "g ams pro"]:
                                logger.warning("[STT] Model '%s' produced isolated prompt keyword '%s' on silent/low-energy audio. Suppressing.", model_name, text_result)
                                return ""

                            if text_result:
                                logger.info("[STT] Transcribe success with '%s': '%s'", model_name, text_result[:100])
                                return text_result
                            else:
                                logger.info("[STT] Model '%s' returned empty text, stopping STT as silence.", model_name)
                                return ""
                        else:
                            logger.info("[STT] Model '%s' returned no candidates, trying next fallback model...", model_name)
                    else:
                        logger.warning("[STT] Gemini model '%s' failed (%s): %s", model_name, response.status_code, response.text[:200])
                        last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                except Exception as ex:
                    logger.warning("[STT] Error invoking model '%s': %s", model_name, ex)
                    last_error = str(ex)

        if last_error:
            logger.error("[STT] All Gemini models failed for transcription. Last error: %s", last_error)
            raise RuntimeError(f"Không thể phiên âm giọng nói qua Gemini: {last_error}")
        return ""
