"""OpenAI Responses API boundary for the first X01-only live probe.

Default remains OFF. Live calls require both:
- ATELIER_OPENAI_LIVE=1
- OPENAI_API_KEY

The driver only accepts X01/X and T01/Threads live probe pairs.
It never publishes, sends x_06/E567, or calls any tool.
"""
import json
import os
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError


class ProviderUnavailable(Exception):
    pass


class ProviderError(Exception):
    def __init__(self, message, *, technical=True, attempts=None):
        super().__init__(message)
        self.technical = technical
        self.attempts = attempts or []


class OpenAIDriver:
    name = "openai"
    endpoint = "https://api.openai.com/v1/responses"
    max_retries = 2

    @property
    def connected(self):
        return os.environ.get("ATELIER_OPENAI_LIVE") == "1" and bool(os.environ.get("OPENAI_API_KEY"))

    @property
    def model(self):
        return os.environ.get("OPENAI_MODEL", "gpt-5.6")

    @property
    def max_output_tokens(self):
        return int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "8000"))

    @property
    def reasoning_effort(self):
        return os.environ.get("OPENAI_REASONING_EFFORT", "low")

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
                    raise ProviderError("OpenAI response was refused", technical=False)
        raise ProviderError("OpenAI response did not contain output_text")

    def _response_meta(self, payload, attempt):
        usage = payload.get("usage") or {}
        details = usage.get("output_tokens_details") or {}
        incomplete = payload.get("incomplete_details") or {}
        return {
            "attempt": attempt,
            "status": payload.get("status"),
            "incomplete_reason": incomplete.get("reason"),
            "output_tokens": usage.get("output_tokens"),
            "reasoning_tokens": details.get("reasoning_tokens"),
            "max_output_tokens": self.max_output_tokens,
        }

    def execute(self, request):
        if not self.connected:
            raise ProviderUnavailable("OpenAI未接続：ATELIER_OPENAI_LIVE=1 と OPENAI_API_KEY が必要です")
        if (request.get("employee"), request.get("platform")) not in {("X01","X"),("T01","Threads")}:
            raise ProviderUnavailable("現在の接続範囲外の社員・媒体です")
        if request.get("mode") != "initial_live_probe":
            raise ProviderUnavailable("現在の接続で許可されていない実行モードです")

        api_key = os.environ.get("OPENAI_API_KEY", "")
        material = request.get("material", "")
        required_facts = request.get("required_facts", [])
        coco_resolution = request.get("coco_resolution")
        if not isinstance(material, str) or not material.strip():
            raise ProviderError("material is required", technical=False)
        if not isinstance(required_facts, list) or not all(isinstance(x, str) for x in required_facts):
            raise ProviderError("required_facts must be a string list", technical=False)

        stage_name = request.get("stage_name", "")
        stage_prompt = request.get("stage_prompt", "")
        prior_outputs = request.get("prior_stage_outputs", [])
        canon_preamble = request.get("canon_preamble", "")
        if not isinstance(stage_prompt, str) or not stage_prompt.strip():
            raise ProviderError("stage_prompt is required", technical=False)

        effective_system_prompt = (
            canon_preamble
            + "\n\n【今回実行する正典工程】\n"
            + stage_prompt
        )
        if isinstance(coco_resolution, dict) and coco_resolution.get("action") == "proceed_without_missing_fact":
            missing = coco_resolution.get("missing_or_unknown", "")
            effective_system_prompt += (
                "\n\n【この案件だけのCoco判断】\n"
                "Cocoが「このまま進める」を選択した。これは正典やルールの変更ではない。"
                "この案件では、停止時に不足していた事実を推測・補完・創作せず、使わない形で進める。"
                "その不足だけを理由に再停止しない。他の不足・矛盾・指示外があれば通常どおり停止する。"
                f"\n停止時の不足内容: {missing}"
            )

        user_input = {
            "task": f"{request.get('employee')}の{request.get('platform')}投稿の工程「{stage_name}」だけを実行する",
            "stage_index": request.get("stage_index"),
            "stage_count": request.get("stage_count"),
            "required_facts_for_this_case": required_facts,
            "material": material,
            "prior_stage_outputs": prior_outputs,
            "coco_resolution": coco_resolution,
            "stage_output_contract": {
                "content": (
                    "この工程で得た成果物を返す。次工程で使えるよう、候補・選定結果・必ず残す事実・本文等、"
                    "この工程が生成または確認した内容を省略しない。⑤では、問題がなければ④の完成本文をそのまま返し、"
                    "修正が必要なら正典⑤の範囲で直した完成本文全体を返す。"
                ),
                "quote": "ひとことが確定している工程以降は、その確定ひとことを返す。未確定なら空文字。",
                "complete": "この工程が正典どおり完了した場合。投稿全体の完成という意味ではない。",
                "stop": "この工程で素材不足・事実不明・指示外に到達した場合だけ。推測で補わない。",
                "facts_used": "②以降では【必ず残す事実】を素材中の表現から列挙する。未確定なら空配列。"
            }
        }
        body = {
            "model": self.model,
            "store": False,
            "input": [
                {"role": "system", "content": effective_system_prompt},
                {"role": "user", "content": json.dumps(user_input, ensure_ascii=False)}
            ],
            "reasoning": {"effort": self.reasoning_effort},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "coco_atelier_x01_probe",
                    "strict": True,
                    "schema": self._schema()
                }
            },
            "max_output_tokens": self.max_output_tokens
        }

        attempts = []
        total_attempts = 1 + self.max_retries
        for attempt in range(1, total_attempts + 1):
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
            payload = None
            try:
                with urlrequest.urlopen(req, timeout=90) as response:
                    raw = response.read().decode("utf-8")
                payload = json.loads(raw)
                meta = self._response_meta(payload, attempt)

                if payload.get("status") == "incomplete":
                    attempts.append({**meta, "error_type": "incomplete"})
                    if attempt < total_attempts:
                        continue
                    raise ProviderError(
                        "OpenAI response remained incomplete after retries",
                        attempts=attempts,
                    )

                output_text = self._extract_output_text(payload)
                result = json.loads(output_text)
                result["_provider"] = {
                    "response_id": payload.get("id"),
                    "model": payload.get("model", self.model),
                    **meta,
                    "attempts": attempts + [{**meta, "error_type": None}],
                }
                return result

            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                attempts.append({
                    "attempt": attempt,
                    "status": "http_error",
                    "incomplete_reason": None,
                    "output_tokens": None,
                    "reasoning_tokens": None,
                    "max_output_tokens": self.max_output_tokens,
                    "error_type": f"HTTP_{exc.code}",
                })
                if attempt >= total_attempts:
                    raise ProviderError(
                        f"OpenAI HTTP {exc.code}: {detail[:500]}",
                        attempts=attempts,
                    ) from exc
            except URLError as exc:
                attempts.append({
                    "attempt": attempt,
                    "status": "connection_error",
                    "incomplete_reason": None,
                    "output_tokens": None,
                    "reasoning_tokens": None,
                    "max_output_tokens": self.max_output_tokens,
                    "error_type": "connection_error",
                })
                if attempt >= total_attempts:
                    raise ProviderError(
                        f"OpenAI connection error: {exc}",
                        attempts=attempts,
                    ) from exc
            except json.JSONDecodeError as exc:
                meta = self._response_meta(payload or {}, attempt)
                attempts.append({**meta, "error_type": "parse_error"})
                if attempt >= total_attempts:
                    raise ProviderError(
                        "OpenAI structured output could not be parsed after retries",
                        attempts=attempts,
                    ) from exc
            except ProviderError as exc:
                if not exc.technical:
                    raise
                meta = self._response_meta(payload or {}, attempt)
                attempts.append({**meta, "error_type": "provider_error"})
                if attempt >= total_attempts:
                    raise ProviderError(str(exc), attempts=attempts) from exc

        raise ProviderError("OpenAI technical error", attempts=attempts)
