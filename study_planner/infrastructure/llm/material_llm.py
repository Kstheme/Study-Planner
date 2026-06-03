from __future__ import annotations

import json
import urllib.error
import urllib.request

from study_planner.infrastructure.settings import AppSettings


class DeepSeekMaterialLLM:
    def __init__(self, api_key: str, base_url: str, model: str):
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required when USE_REAL_LLM=true.")
        if not model:
            raise ValueError("DEEPSEEK_MODEL is required when USE_REAL_LLM=true.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "DeepSeekMaterialLLM":
        return cls(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )

    def generate(self, prompt: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API request failed: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DeepSeek API network error: {exc}") from exc

        return payload["choices"][0]["message"]["content"]
