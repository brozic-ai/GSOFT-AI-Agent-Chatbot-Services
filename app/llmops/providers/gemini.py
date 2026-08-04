import json
import re

from google import genai
from google.genai import types

from ..base import BaseLLMProvider

class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-3.5-flash-lite"):
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name
    
    def generate(self, system_prompt: str, user_prompt: str, **kwargs,) -> str:
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                **kwargs,
            )
        )

        return response.text or "No answer"
    
    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict | None = None,) -> json:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json"
        )

        if schema is not None:
            config.response_schema = schema
        
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=user_prompt,
            config=config,
        )

        raw = response.text
        if not raw:
            raise ValueError("Gemini does not return content")

        cleaned = re.sub(r"^```json\s*|\s*```$", "", raw.strip())
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"Gemini trả JSON không hợp lệ: {e}\nRaw: {raw}")
            