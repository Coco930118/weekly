"""OpenAI Responses API boundary for the first X01-only live probe.

Default remains OFF. Live calls require both:
- ATELIER_OPENAI_LIVE=1
- OPENAI_API_KEY

The driver only accepts employee X01 / platform X / mode x01_initial_probe.
It never publishes, sends x_06/E567, or calls any tool.
"""
import json
import os
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError


class ProviderUnavailable(Exception):
    pass


class ProviderError(Exception):
    pass


class OpenAIDriver:
    name = "openai"
    endpoint = "https://api.openai.com/v1/responses"

    @property
    def connected(self):
        return os.environ.get("ATELIER_OPENAI_LIVE") == "1" and bool(os.environ.get("OPENAI_API_KEY"))

    @property
    def model(self):
        return os.environ.get("OPENAI_MODEL", "gpt-5.6")

    @staticmethod
    def _schema():
        return {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["complete", "stop"]},
                "stop_reason": {"type": "string", "enum": ["none", "素材不足", "事実不明", "指示外"]},
                "stop_stage": {"type": "string"},
                "missing_or_unknown": {"type": "string"},
                "confirmed_facts": {"type": "string"},
                "question_for_coco": {"type": "string"},
                "content": {"type": "string"},
                "quote": {"type": "string"},
                "facts_used": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": [
                "decision", "stop_reason", "stop_stage", "missing_or_unknown",
                "confirmed_facts", "question_for_coco", "content", "quote", "facts_used"
            ],
            "additionalProperties": False
        }

    @staticmethod
    def _extract_output_text(payload):
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    return part["text"]
                if part.get("type") == "refusal":
                    raise ProviderError("OpenAI response was refused")
        raise ProviderError("OpenAI response did not contain output_text")

    def execute(self, request):
        if not self.connected:
            raise ProviderUnavailable("OpenAI未接続：ATELIER_OPENAI_LIVE=1 と OPENAI_API_KEY が必要です")
        if request.get("employee") != "X01" or request.get("platform") != "X":
            raise ProviderUnavailable("初回接続はX01のX投稿だけに限定されています")
        if request.get("mode") != "x01_initial_probe":
            raise ProviderUnavailable("初回接続で許可されていない実行モードです")

        api_key = os.environ.get("OPENAI_API_KEY", "")
        system_prompt = request.get("system_prompt", "")
        material = request.get("material", "")
        required_facts = request.get("required_facts", [])
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ProviderError("system_prompt is required")
        if not isinstance(material, str) or not material.strip():
            raise ProviderError("material is required")
        if not isinstance(required_facts, list) or not all(isinstance(x, str) for x in required_facts):
            raise ProviderError("required_facts must be a string list")

        user_input = {
            "task": "X01の1投稿を、正典と素材の範囲だけで処理する",
            "required_facts_for_this_case": required_facts,
            "material": material,
            "output_contract": {
                "complete": "必要事実がすべて素材にあり、素材外の事実を足さずに書ける場合だけ",
                "stop": "必要事実が不足・矛盾・指示外なら推測せず停止",
                "facts_used": "完成時に使った事実を、素材中の表現から抜き出して列挙する"
            }
        }
        body = {
            "model": self.model,
            "store": False,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_input, ensure_ascii=False)}
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "coco_atelier_x01_probe",
                    "strict": True,
                    "schema": self._schema()
                }
            },
            "max_output_tokens": 3000
        }
        req = urlrequest.Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "coco-atelier-x01-probe/1.0"
            },
            method="POST"
        )
        try:
            with urlrequest.urlopen(req, timeout=90) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ProviderError(f"OpenAI HTTP {exc.code}: {detail[:500]}") from exc
        except URLError as exc:
            raise ProviderError(f"OpenAI connection error: {exc}") from exc

        try:
            payload = json.loads(raw)
            output_text = self._extract_output_text(payload)
            result = json.loads(output_text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ProviderError("OpenAI structured output could not be parsed") from exc

        result["_provider"] = {
            "response_id": payload.get("id"),
            "model": payload.get("model", self.model)
        }
        return result
