"""OpenAI Responses API boundary.

Live calls require both:
- ATELIER_OPENAI_LIVE=1
- OPENAI_API_KEY

The media canon itself is never rewritten here or sent as anything other than
its own text (`canon_preamble` / `stage_prompt`). This driver only executes
the stage it is given; it does not publish, send x_06/E567, or call any tool.
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


def stage_output_schema():
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
            "facts_used": {"type": "array", "items": {"type": "string"}},
            "checklist": {"type": "array", "items": {"type": "string"}},
            "public_material": {"type": "string"},
            "source_map": {"type": "array", "items": {"type": "string"}},
            "candidates": {"type": "array", "items": {"type": "string"}},
            "selection": {"type": "string"},
            "audit_tags": {"type": "array", "items": {"type": "string"}},
            "material_suggestions": {"type": "array", "items": {"type": "string"}},
            "final_check_round": {"type": "integer", "minimum": 0, "maximum": 2},
        },
        "required": [
            "decision", "stop_reason", "stop_stage", "missing_or_unknown",
            "confirmed_facts", "question_for_coco", "content", "quote", "facts_used", "checklist",
            "public_material", "source_map", "candidates", "selection", "audit_tags",
            "material_suggestions", "final_check_round",
        ],
        "additionalProperties": False,
    }


def interview_output_schema(points_keys, draft_required_fields, draft_optional_field, gate_fields, gate_list_fields):
    """取材社員（atelier/canon/interview.md）の工程2・3・5共通の構造化出力。
    キー名だけをパラメータで受け取る——条文の内容はここに複製しない。
    """
    draft_fields = list(draft_required_fields) + [draft_optional_field]
    return {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["continue", "stop"]},
            "stop_reason": {"type": "string"},
            "points": {
                "type": "object",
                "properties": {k: {"type": "string"} for k in points_keys},
                "required": list(points_keys),
                "additionalProperties": False,
            },
            "missing": {"type": "array", "items": {"type": "string"}},
            "drafts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {f: {"type": "string"} for f in draft_fields},
                    "required": draft_fields,
                    "additionalProperties": False,
                },
            },
            "public_material": {
                "type": "object",
                "properties": {
                    f: ({"type": "array", "items": {"type": "string"}} if f in gate_list_fields else {"type": "string"})
                    for f in gate_fields
                },
                "required": list(gate_fields),
                "additionalProperties": False,
            },
            "smell_flags": {
                "type": "object",
                "properties": {f: {"type": "array", "items": {"type": "string"}} for f in gate_fields},
                "required": list(gate_fields),
                "additionalProperties": False,
            },
        },
        "required": ["decision", "stop_reason", "points", "missing", "drafts", "public_material", "smell_flags"],
        "additionalProperties": False,
    }


def vp_output_schema():
    return {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["通す", "戻す"]},
            "finding": {"type": "string", "enum": ["none", "事実が曲がった", "声が混ざった", "工程に戻っていない"]},
            "source_quote": {"type": "string"},
            "post_quote": {"type": "string"},
        },
        "required": ["decision", "finding", "source_quote", "post_quote"],
        "additionalProperties": False,
    }


class OpenAIDriver:
    name = "openai"
    endpoint = "https://api.openai.com/v1/responses"
    max_retries = 2

    def __init__(self, model_env=None):
        # 役ごとに違うモデルを設定で切り替えられるようにする（anthropic_driver.pyと同じ仕組み）。
        self.model_env = model_env

    @property
    def connected(self):
        return os.environ.get("ATELIER_OPENAI_LIVE") == "1" and bool(os.environ.get("OPENAI_API_KEY"))

    @property
    def model(self):
        if self.model_env and os.environ.get(self.model_env):
            return os.environ[self.model_env]
        return os.environ.get("OPENAI_MODEL", "gpt-5.6")

    @property
    def max_output_tokens(self):
        return int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "8000"))

    @property
    def reasoning_effort(self):
        return os.environ.get("OPENAI_REASONING_EFFORT", "low")

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

    def _call(self, body, user_agent):
        api_key = os.environ.get("OPENAI_API_KEY", "")
        attempts = []
        total_attempts = 1 + self.max_retries
        for attempt in range(1, total_attempts + 1):
            req = urlrequest.Request(
                self.endpoint,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": user_agent,
                },
                method="POST",
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
                    raise ProviderError("OpenAI response remained incomplete after retries", attempts=attempts)
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
                    "attempt": attempt, "status": "http_error", "incomplete_reason": None,
                    "output_tokens": None, "reasoning_tokens": None,
                    "max_output_tokens": self.max_output_tokens, "error_type": f"HTTP_{exc.code}",
                })
                if attempt >= total_attempts:
                    raise ProviderError(f"OpenAI HTTP {exc.code}: {detail[:500]}", attempts=attempts) from exc
            except URLError as exc:
                attempts.append({
                    "attempt": attempt, "status": "connection_error", "incomplete_reason": None,
                    "output_tokens": None, "reasoning_tokens": None,
                    "max_output_tokens": self.max_output_tokens, "error_type": "connection_error",
                })
                if attempt >= total_attempts:
                    raise ProviderError(f"OpenAI connection error: {exc}", attempts=attempts) from exc
            except json.JSONDecodeError as exc:
                meta = self._response_meta(payload or {}, attempt)
                attempts.append({**meta, "error_type": "parse_error"})
                if attempt >= total_attempts:
                    raise ProviderError("OpenAI structured output could not be parsed after retries", attempts=attempts) from exc
        raise ProviderError("OpenAI technical error", attempts=attempts)

    def execute(self, request):
        if not self.connected:
            raise ProviderUnavailable("OpenAI未接続：ATELIER_OPENAI_LIVE=1 と OPENAI_API_KEY が必要です")
        material = request.get("material", "")
        if not isinstance(material, str) or not material.strip():
            raise ProviderError("material is required", technical=False)
        stage_prompt = request.get("stage_prompt", "")
        if not isinstance(stage_prompt, str) or not stage_prompt.strip():
            raise ProviderError("stage_prompt is required", technical=False)

        effective_system_prompt = request.get("canon_preamble", "") + "\n\n【今回実行する正典工程】\n" + stage_prompt
        vp_return_feedback = request.get("vp_return_feedback")
        if isinstance(vp_return_feedback, dict) and vp_return_feedback.get("finding"):
            effective_system_prompt += (
                "\n\n【この案件だけの副社長戻し】\n"
                f"戻し理由: {vp_return_feedback.get('finding')}\n"
                f"戻し工程: {vp_return_feedback.get('stage')}\n"
                f"素材原文の引用: {vp_return_feedback.get('source_quote','')}\n"
                f"完成投稿の引用: {vp_return_feedback.get('post_quote','')}\n"
                "この戻しだけを解消して同じ案件をやり直す。正典は変更しない。"
                "素材原文の事実・主語・時系列・引用語を変えず、素材にない事実や行動を足さない。"
                "前回の完成文を正当化せず、正典に従って作り直す。"
            )
        coco_resolution = request.get("coco_resolution")
        if isinstance(coco_resolution, dict) and coco_resolution.get("action") == "case_instruction":
            effective_system_prompt += (
                "\n\n【この案件だけのCoco回答】\n" + str(coco_resolution.get("instruction", "")).strip() +
                "\nこれはこの案件だけのCoco判断であり、正典やルールの変更ではない。"
                "素材にない事実を足さず、この回答の範囲で同じ社員が停止地点から再開する。"
            )
        if isinstance(coco_resolution, dict) and coco_resolution.get("action") == "proceed_without_missing_fact":
            effective_system_prompt += (
                "\n\n【この案件だけのCoco判断】\n"
                "Cocoが「このまま進める」を選択した。これは正典やルールの変更ではない。"
                "この案件では、停止時に不足していた事実を推測・補完・創作せず、使わない形で進める。"
                "その不足だけを理由に再停止しない。他の不足・矛盾・指示外があれば通常どおり停止する。"
                f"\n停止時の不足内容: {coco_resolution.get('missing_or_unknown','')}"
            )

        user_input = {
            "task": f"{request.get('employee')}の{request.get('platform')}工程「{request.get('stage_name')}」だけを実行する",
            "stage_index": request.get("stage_index"),
            "stage_count": request.get("stage_count"),
            "material": material,
            "prior_stage_outputs": request.get("prior_stage_outputs", []),
            "coco_resolution": coco_resolution,
            "vp_return_feedback": vp_return_feedback,
            "completion_feedback": request.get("completion_feedback"),
        }
        body = {
            "model": self.model,
            "store": False,
            "input": [
                {"role": "system", "content": effective_system_prompt},
                {"role": "user", "content": json.dumps(user_input, ensure_ascii=False)},
            ],
            "reasoning": {"effort": self.reasoning_effort},
            "text": {"format": {"type": "json_schema", "name": "coco_atelier_stage", "strict": True, "schema": stage_output_schema()}},
            "max_output_tokens": self.max_output_tokens,
        }
        return self._call(body, "coco-atelier/1.0")

    def review_vp(self, material, completed_post, criteria):
        """Independent VP gate. API input is source + final post + three criteria only."""
        if not self.connected:
            raise ProviderUnavailable("OpenAI未接続：副社長レビューを実行できません")
        if not isinstance(material, str) or not material.strip():
            raise ProviderError("VP material is required", technical=False)
        if not isinstance(completed_post, str) or not completed_post.strip():
            raise ProviderError("VP completed_post is required", technical=False)
        if not isinstance(criteria, dict) or set(criteria) != {"事実が曲がった", "声が混ざった", "工程に戻っていない"}:
            raise ProviderError("VP three-point criteria are required", technical=False)

        system_prompt = (
            "あなたはCoco Atelierの副社長。完成投稿をCoco確認前に3点だけで検査する。"
            "本文を書き直してはいけない。好みや完成度では止めない。"
            "入力は素材原文・完成投稿・3点基準だけであり、見えていない途中工程を推測しない。"
            "問題がなければdecision=通す,finding=none,source_quoteとpost_quoteは空文字。"
            "問題があればdecision=戻すとし、findingは3分類のどれか1つ。"
            "source_quoteには素材原文から関連箇所をそのまま引用し、post_quoteには完成投稿の問題箇所をそのまま引用する。"
            "引用は要約・言い換えせず、それぞれ必ず対応する入力本文に実在する文字列を使う。"
        )
        body = {
            "model": self.model,
            "store": False,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps({"素材原文": material, "完成投稿": completed_post, "3点基準": criteria}, ensure_ascii=False)},
            ],
            "reasoning": {"effort": self.reasoning_effort},
            "text": {"format": {"type": "json_schema", "name": "coco_atelier_vp_gate", "strict": True, "schema": vp_output_schema()}},
            "max_output_tokens": self.max_output_tokens,
        }
        return self._call(body, "coco-atelier-vp/1.0")
