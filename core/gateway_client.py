import requests
import json
from typing import Dict, Any, Optional, List
from config import AppConfig

class GatewayClient:
    def __init__(self, config: AppConfig):
        self.config = config

    def query_ai(self, prompt: str, system_prompt: Optional[str] = None, images: Optional[List[str]] = None) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n[TASK AND PROJECT CONTEXT]:\n{prompt}"

        payload = {
            "prompt": full_prompt,
            "model": self.config.model,
            "messages": [{"role": "user", "content": full_prompt}],
            "images": images or [],
            "thinking": self.config.thinking,
            "web_search": self.config.web_search,
            "dual_ai_mode": self.config.dual_ai_mode,
            "evaluator_model": self.config.evaluator_model if self.config.dual_ai_mode else None,
            "max_rounds": 2 if self.config.dual_ai_mode else None,
        }

        try:
            resp = requests.post(self.config.gateway_url, json=payload, headers=headers, timeout=120)
            if resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"Gateway Error {resp.status_code}: {resp.text}"
                }
            data = resp.json()
            return {
                "success": True,
                "response": data.get("response") or data.get("text") or "",
                "model": data.get("model", self.config.model),
                "tokens": data.get("tokens", {}),
                "rounds_count": data.get("rounds_count"),
                "skill_used": data.get("skill_used")
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
