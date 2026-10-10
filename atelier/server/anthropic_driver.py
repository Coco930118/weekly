"""Anthropic Messages API boundary. Mirrors openai_driver.py's public shape
(execute/review_vp, connected, name, _provider meta keys) so ai_runtime.py can
treat either driver uniformly through role-based provider selection.

Live calls require both:
- ATELIER_ANTHROPIC_LIVE=1
- ANTHROPIC_API_KEY

The media canon itself is never rewritten here or sent as anything other than
its own text (`canon_preamble` / `stage_prompt`). This driver only executes
the stage it is given; it does not publish, send x_06/E567, or call any tool
other than the single structured-output tool used to force the response shape.

Anthropic's Messages API has no "json_schema strict" response format like
OpenAI's Responses API. The equivalent here is a single-tool definition whose
`input_schema` is the same schema `openai_driver.py` uses, so both drivers
return an identical shape. `tool_choice` is left at "auto" (not forced to
`{"type": "tool", ...}` / `{"type": "any"}`) because the live model rejects
forced tool_choice: `HTTP 400 tool_choice: type "tool" and "any" are not
supported for this model` (confirmed 2026-10-10 via interview-live-probe
run #1). The tool's `description` instead instructs the model to always
call it; a missing tool_use block is treated as a retryable technical error
(same retry budget as an HTTP/connection error: `max_retries` attempts in
`_call`, then surfaced as a technical error for `ai_runtime.py` to log and
re-raise — it never becomes a false 停止/manager escalation).

`reasoning_effort="low"` (the default) keeps `thinking` unset (see
`_thinking_block`). 2026-10-10: considered disabling thinking specifically
for structured-output stages to avoid any tool_choice/thinking conflict, but
that is unnecessary now — Anthropic's extended-thinking requirement is that
`tool_choice` be "auto" when thinking is enabled, which is already the only
mode this driver uses. So thinking stays controllable via
`ANTHROPIC_REASONING_EFFORT` with no separate carve-out for these stages.
Anthropic also has no separate "incomplete" status or reasoning-token count:
`stop_reason == "max_tokens"` is treated as the incomplete case, and
`reasoning_tokens` is left as None (Anthropic's usage object does not break
reasoning/thinking tokens out from output_tokens).
"""
import json
import os
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from .openai_driver import ProviderUnavailable, ProviderError, stage_output_schema, vp_output_schema

STAGE_TOOL_NAME = "coco_atelier_stage"
VP_TOOL_NAME = "coco_atelier_vp_gate"
INTERVIEW_TOOL_NAME = "coco_atelier_interview"


class AnthropicDriver:
    name = "anthropic"
    endpoint = "https://api.anthropic.com/v1/messages"
    api_version = "2023-06-01"
    max_retries = 2

    def __init__(self, model_env=None):
        # 役ごとに違うモデルを設定で切り替えられるようにする（例：ANTHROPIC_MODEL_MATERIAL／
        # ANTHROPIC_MODEL_POST_OWNER）。役専用の変数が無ければ共通の ANTHROPIC_MODEL、
        # それも無ければ既定モデルを使う。正典（interview.md等）はprovider・モデルで変えない。
        self.model_env = model_env

    @property
    def connected(self):
        return os.environ.get("ATELIER_ANTHROPIC_LIVE") == "1" and bool(os.environ.get("ANTHROPIC_API_KEY"))

    @property
    def model(self):
        if self.model_env and os.environ.get(self.model_env):
            return os.environ[self.model_env]
        return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    @property
    def max_output_tokens(self):
        return int(os.environ.get("ANTHROPIC_MAX_OUTPUT_TOKENS", "8000"))

    @property
    def reasoning_effort(self):
        return os.environ.get("ANTHROPIC_REASONING_EFFORT", "low")

    def _thinking_block(self):
        if self.reasoning_effort == "low":
            return None
        budget = {"medium": 4000, "high": 10000}.get(self.reasoning_effort, 4000)
        return {"type": "enabled", "budget_tokens": budget}

    @staticmethod
    def _extract_tool_input(payload, tool_name):
        for block in payload.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == tool_name:
                return block.get("input", {})
        raise ProviderError(f"Anthropic response did not contain a {tool_name} tool_use block")

    def _response_meta(self, payload, attempt):
        usage = payload.get("usage") or {}
        stop_reason = payload.get("stop_reason")
        return {
            "attempt": attempt,
            "status": stop_reason,
            "incomplete_reason": stop_reason if stop_reason == "max_tokens" else None,
            "output_tokens": usage.get("output_tokens"),
            # Anthropic's usage object does not separate reasoning/thinking tokens
            # from output_tokens the way OpenAI's output_tokens_details does.
            "reasoning_tokens": None,
            "max_output_tokens": self.max_output_tokens,
        }

    def _call(self, system_prompt, user_content, tool_name, schema, user_agent):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        body = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
            "tools": [{
                "name": tool_name,
                "description": (
                    f"Return {tool_name} output. You must call this tool exactly once with your "
                    "complete answer; do not reply with plain text instead of calling it."
                ),
                "input_schema": schema,
            }],
            "tool_choice": {"type": "auto"},
        }
        thinking = self._thinking_block()
        if thinking:
            body["thinking"] = thinking

        attempts = []
        total_attempts = 1 + self.max_retries
        for attempt in range(1, total_attempts + 1):
            req = urlrequest.Request(
                self.endpoint,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": self.api_version,
                    "content-type": "application/json",
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
                if payload.get("stop_reason") == "refusal":
                    raise ProviderError("Anthropic response was refused", technical=False)
                if payload.get("stop_reason") == "max_tokens":
                    attempts.append({**meta, "error_type": "incomplete"})
                    if attempt < total_attempts:
                        continue
                    raise ProviderError("Anthropic response remained incomplete after retries", attempts=attempts)
                result = self._extract_tool_input(payload, tool_name)
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
                    raise ProviderError(f"Anthropic HTTP {exc.code}: {detail[:500]}", attempts=attempts) from exc
            except URLError as exc:
                attempts.append({
                    "attempt": attempt, "status": "connection_error", "incomplete_reason": None,
                    "output_tokens": None, "reasoning_tokens": None,
                    "max_output_tokens": self.max_output_tokens, "error_type": "connection_error",
                })
                if attempt >= total_attempts:
                    raise ProviderError(f"Anthropic connection error: {exc}", attempts=attempts) from exc
            except json.JSONDecodeError as exc:
                meta = self._response_meta(payload or {}, attempt)
                attempts.append({**meta, "error_type": "parse_error"})
                if attempt >= total_attempts:
                    raise ProviderError("Anthropic response could not be parsed after retries", attempts=attempts) from exc
            except ProviderError as exc:
                if not exc.technical:
                    raise
                meta = self._response_meta(payload or {}, attempt)
                attempts.append({**meta, "error_type": "provider_error"})
                if attempt >= total_attempts:
                    raise ProviderError(str(exc), attempts=attempts) from exc
        raise ProviderError("Anthropic technical error", attempts=attempts)

    def execute(self, request):
        if not self.connected:
            raise ProviderUnavailable("Anthropic未接続：ATELIER_ANTHROPIC_LIVE=1 と ANTHROPIC_API_KEY が必要です")
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
        return self._call(
            effective_system_prompt,
            json.dumps(user_input, ensure_ascii=False),
            STAGE_TOOL_NAME,
            stage_output_schema(),
            "coco-atelier/1.0",
        )

    def review_vp(self, material, completed_post, criteria):
        """Independent VP gate. API input is source + final post + three criteria only."""
        if not self.connected:
            raise ProviderUnavailable("Anthropic未接続：副社長レビューを実行できません")
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
        user_content = json.dumps({"素材原文": material, "完成投稿": completed_post, "3点基準": criteria}, ensure_ascii=False)
        return self._call(system_prompt, user_content, VP_TOOL_NAME, vp_output_schema(), "coco-atelier-vp/1.0")

    def run_interview_stage(self, canon_text, stage_instruction, raw_material, context, schema):
        """取材社員（atelier/canon/interview.md）の工程を1つ実行する。canon_textは
        interview.mdの全文をそのまま指示文として渡す（原文の加工・要約はしない）。"""
        if not self.connected:
            raise ProviderUnavailable("Anthropic未接続：取材社員を実行できません")
        if not isinstance(raw_material, str) or not raw_material.strip():
            raise ProviderError("interview raw_material is required", technical=False)
        system_prompt = canon_text + "\n\n【今回実行する工程】\n" + stage_instruction
        user_content = json.dumps({"原文": raw_material, **(context or {})}, ensure_ascii=False)
        return self._call(system_prompt, user_content, INTERVIEW_TOOL_NAME, schema, "coco-atelier-interview/1.0")
