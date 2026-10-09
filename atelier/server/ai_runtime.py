"""Provider adapter boundary.

Live provider use is OFF by default.
Current live scope is intentionally narrow:
- X01 / X
- T01 / Threads

The media canon itself is never rewritten here. For live generation, the runtime
executes the canon's own stage headings in order and passes each stage output to
the next stage for the same employee.
"""
import json
import re

from .openai_driver import OpenAIDriver, ProviderUnavailable, ProviderError


class AIRuntime:
    LIVE_SCOPE = {("X01", "X"), ("T01", "Threads")}
    STAGES = [
        ("①", ("## ①🧳", "## ①💗")),
        ("ひとこと選び", ("## ひとこと選び🧳", "## ひとこと選び💗")),
        ("②", ("## ②🧳", "## ②💗")),
        ("③", ("## ③🧳", "## ③💗")),
        ("④", ("## ④🧳", "## ④💗")),
        ("⑤", ("## ⑤ 最終確認",)),
    ]
    STAGES_V2 = [
        ("一般化", ("## 一般化工程",)),
        ("①", ("## ①🧳", "## ①💗")),
        ("ひとこと選び", ("## ひとこと選び🧳", "## ひとこと選び💗")),
        ("②", ("## ②🧳", "## ②💗")),
        ("③", ("## ③🧳", "## ③💗")),
        ("④", ("## ④🧳", "## ④💗")),
        ("④'", ("## ④'🧳", "## ④'💗")),
        ("⑤", ("## ⑤🧳", "## ⑤💗")),
        ("最終確認", ("## 最終確認🧳", "## 最終確認💗")),
        ("⑦", ("## ⑦🧳", "## ⑦💗")),
    ]

    def __init__(self, workspace):
        self.workspace = workspace
        self.provider = OpenAIDriver()

    @staticmethod
    def _section(prompt, starts):
        lines = prompt.splitlines()
        start = None
        for i, line in enumerate(lines):
            if any(line.startswith(prefix) for prefix in starts):
                start = i
                break
        if start is None:
            raise ProviderError(f"Canon stage not found: {starts}", technical=False)
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].startswith("## "):
                end = i
                break
        return "\n".join(lines[start:end]).strip()

    def _canon_stages(self, prompt, canon_version="v1"):
        stages = self.STAGES_V2 if canon_version == "v2" else self.STAGES
        return [(name, self._section(prompt, starts)) for name, starts in stages]

    def _coco_resolution(self, key, db):
        if db is None:
            return None
        has_events = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_events'"
        ).fetchone()
        if not has_events:
            return None

        proceed = db.execute(
            "SELECT detail FROM workflow_events WHERE case_id=? AND action='このまま進める' ORDER BY id DESC LIMIT 1",
            (key,),
        ).fetchone()
        answers = db.execute(
            "SELECT detail FROM workflow_events WHERE case_id=? AND actor='Coco' AND action='停止案件回答' ORDER BY id",
            (key,),
        ).fetchall()

        instructions = []
        for row in answers:
            detail = json.loads(row["detail"])
            response = str(detail.get("response", "")).strip()
            if response and response != "このまま進める":
                instructions.append(response)

        if instructions:
            return {
                "action": "case_instruction",
                "instruction": "\n".join(
                    f"{i+1}. {item}" for i, item in enumerate(instructions)
                ),
                "instructions": instructions,
            }

        if proceed:
            detail = json.loads(proceed["detail"])
            return {
                "action": "proceed_without_missing_fact",
                "missing_or_unknown": detail.get("不足・不明点", ""),
            }
        return None

    def _vp_return_feedback(self, key, db=None):
        owns_db = db is None
        if owns_db:
            ctx = self.workspace.transaction()
            db = ctx.__enter__()
        try:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_events'"
            ).fetchone()
            if not exists:
                return None
            row = db.execute(
                """SELECT detail FROM workflow_events
                   WHERE case_id=? AND actor='副社長' AND action='工程へ戻す'
                   ORDER BY id DESC LIMIT 1""",
                (key,),
            ).fetchone()
            if not row:
                return None
            detail = json.loads(row["detail"])
            return {
                "finding": detail.get("finding"),
                "stage": detail.get("stage"),
                "source_quote": detail.get("source_quote", ""),
                "post_quote": detail.get("post_quote", ""),
            }
        finally:
            if owns_db:
                ctx.__exit__(None, None, None)

    def _prepare_request(self, key, state, person, db=None):
        source_row = self.workspace.source(key)
        source = source_row["source"]

        canon_version = "v1"
        prompt_ref = person["prompt_ref"]
        if db is not None:
            case = db.execute(
                "SELECT rule_version FROM workflow_cases WHERE case_id=?", (key,)
            ).fetchone()
            if case and int(case["rule_version"] or 0) > 0:
                rule = db.execute(
                    "SELECT rule_key FROM rule_versions WHERE id=?",
                    (int(case["rule_version"]),),
                ).fetchone()
                if rule and rule["rule_key"] == "canon_v2":
                    canon_version = "v2"
                    if state["platform"] == "Threads":
                        prompt_ref = "atelier/canon/threads_post_v2.md"
                    elif state["platform"] == "X":
                        prompt_ref = "atelier/canon/x_post_v2.md"

        prompt_path = self.workspace.root / prompt_ref
        full_canon = prompt_path.read_text()
        material = source.get("material")
        if not isinstance(material, str) or not material.strip():
            material = source.get("source_material")
        if not isinstance(material, str) or not material.strip():
            material = source.get("raw_material")
        if not isinstance(material, str) or not material.strip():
            from .server import WorkspaceError
            raise WorkspaceError("MATERIAL_REQUIRED", "OpenAIへ送る素材フィールドが明示されていません")
        required_facts = source.get("_probe_required_facts", [])
        return {
            "mode": "initial_live_probe",
            "canon_version": canon_version,
            "canon_ref": prompt_ref,
            "canon_common": full_canon if canon_version == "v2" else "",
            "employee": person["id"],
            "platform": state["platform"],
            "material": material,
            "required_facts": required_facts,
            "coco_resolution": self._coco_resolution(key, db),
            "vp_return_feedback": self._vp_return_feedback(key, db),
            "canon_preamble": (
                "以下はCoco確定正典の工程を、原文のまま順番に実行する。"
                "各呼び出しでは指定された1工程だけを実行し、その工程で得た成果物を返す。"
                "『本文には進まない』等の記述は、その呼び出し内で次工程を実行しないという意味であり、"
                "投稿全体の終了を意味しない。素材不足・事実不明・指示外は正典どおり停止する。"
            ),
            "stages": self._canon_stages(full_canon, canon_version),
        }

    def _record_technical_error(self, key, employee, candidate, exc):
        attempts = getattr(exc, "attempts", []) or [{}]
        last = attempts[-1]
        with self.workspace.transaction() as db:
            case = db.execute(
                "SELECT stage FROM workflow_cases WHERE case_id=?", (key,)
            ).fetchone() if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_cases'"
            ).fetchone() else None
            stage = case["stage"] if case else "素材確認・事実固定"
            self.workspace.log(db, key, employee, "failed", "TECHNICAL_ERROR", candidate)
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_events'"
            ).fetchone():
                detail = {
                    "発生工程": stage,
                    "attempt番号": last.get("attempt"),
                    "API完了状態": last.get("status"),
                    "incomplete理由": last.get("incomplete_reason"),
                    "output token数": last.get("output_tokens"),
                    "reasoning token数": last.get("reasoning_tokens"),
                    "上限値": last.get("max_output_tokens"),
                    "エラー種別": last.get("error_type") or type(exc).__name__,
                    "attempts": attempts,
                }
                db.execute(
                    "INSERT INTO workflow_events(case_id,actor,action,target,detail) VALUES (?,?,?,?,?)",
                    (key, employee, "技術エラー", None, json.dumps(detail, ensure_ascii=False)),
                )
            if case:
                db.execute(
                    "UPDATE workflow_cases SET status='未着手',updated_at=CURRENT_TIMESTAMP WHERE case_id=?",
                    (key,),
                )

    def _log_stage(self, key, employee, action, stage_name, detail=None):
        with self.workspace.transaction() as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_events'"
            ).fetchone()
            if exists:
                db.execute(
                    "INSERT INTO workflow_events(case_id,actor,action,target,detail) VALUES (?,?,?,?,?)",
                    (
                        key,
                        employee,
                        action,
                        stage_name,
                        json.dumps(detail or {}, ensure_ascii=False),
                    ),
                )

    @staticmethod
    def _body_only(text):
        """Strip orchestration labels when a stage returns a wrapped body."""
        if not isinstance(text, str):
            return ""
        if "【本文】" in text:
            text = text.split("【本文】", 1)[1]
        return text.strip()

    @staticmethod
    def _nonempty_lines(text):
        return [line for line in text.splitlines() if line.strip()]

    @staticmethod
    def _paragraphs(text):
        return [
            part.strip()
            for part in re.split(r"\n\s*\n", text.strip())
            if part.strip()
        ]

    def _completion_check(self, platform, final_content, history):
        stage2 = next((x for x in history if x.get("stage") == "②"), {})
        stage4 = next((x for x in reversed(history) if x.get("stage") == "④"), {})
        facts = stage2.get("facts_used") or []
        checklist = stage4.get("checklist") or []

        if platform == "X":
            failures = []
            if len(self._nonempty_lines(final_content)) != 4:
                failures.append("本文が4行ではない")
            if len(facts) != 3:
                failures.append("【必ず残す事実】3点が記録されていない")
            return {
                "ok": not failures,
                "failures": failures,
                "continue_stage": "④",
                "facts_count": len(facts),
                "checklist_count": len(checklist),
            }

        if platform == "Threads":
            failures = []
            if len(self._paragraphs(final_content)) != 6:
                failures.append("本文が6段構成ではない")
            if len(checklist) != 14:
                failures.append("14項目チェックが記録されていない")
            return {
                "ok": not failures,
                "failures": failures,
                "continue_stage": "④",
                "facts_count": len(facts),
                "checklist_count": len(checklist),
            }

        # X短文 is not in current live scope, but keep the approved definition
        # here so its gate is explicit when that employee is connected.
        if platform == "X短文":
            failures = []
            sentences = [x for x in re.split(r"[。！？!?]+", final_content.strip()) if x.strip()]
            if len(sentences) != 1:
                failures.append("本文が1文ではない")
            return {
                "ok": not failures,
                "failures": failures,
                "continue_stage": "本文作成",
                "facts_count": len(facts),
                "checklist_count": len(checklist),
            }

        return {
            "ok": False,
            "failures": ["完成形式が未定義の部門"],
            "continue_stage": "④",
            "facts_count": len(facts),
            "checklist_count": len(checklist),
        }

    def _record_process_incomplete(self, key, employee, check):
        self._log_stage(
            key,
            employee,
            "工程未完了",
            check.get("continue_stage") or "④",
            {
                "形式未達": check.get("failures", []),
                "facts_count": check.get("facts_count"),
                "checklist_count": check.get("checklist_count"),
                "business_stop": False,
                "technical_error": False,
            },
        )

    def execute(self, key, candidate, employee, expected_revision, expected_candidate_revision):
        error = None
        provider_block = None
        prepared = None
        state_snapshot = None
        person = None
        with self.workspace.transaction() as db:
            try:
                state = self.workspace._load(db, key)
                self.workspace.check_revision(state, expected_revision)
                self.workspace.check_candidate_revision(state, candidate, expected_candidate_revision)
                person = self.workspace.employee(employee)
                if person["media"] and state["platform"] not in person["media"]:
                    from .server import WorkspaceError
                    raise WorkspaceError("PERMISSION", "担当媒体の権限がありません")
                if not self.provider.connected:
                    self.workspace.log(db, key, employee, "blocked", "AI_DISABLED", candidate)
                    provider_block = "AI未接続：AI実行は有効化されていません"
                elif (str(person["id"]), state["platform"]) not in self.LIVE_SCOPE:
                    self.workspace.log(db, key, employee, "blocked", "AI_SCOPE", candidate)
                    provider_block = "現在のOpenAI接続はX01/XとT01/Threadsだけです"
                else:
                    prepared = self._prepare_request(key, state, person, db)
                    state_snapshot = {
                        "theme": state["theme"],
                        "axis": state["axis"],
                        "revision": state["revision"],
                        "candidate_revision": state["candidates"][candidate]["revision"],
                    }
                    self.workspace.log(db, key, employee, "started", "OPENAI_ORCHESTRATED", candidate)
            except Exception as exc:
                from .server import WorkspaceError
                if not isinstance(exc, WorkspaceError):
                    raise
                error = exc
                self.workspace.log(db, key, employee, "blocked", exc.code, candidate)
        if error:
            raise error
        if provider_block:
            raise ProviderUnavailable(provider_block)

        if prepared["canon_version"] == "v2":
            return self._execute_v2(key, candidate, employee, prepared, state_snapshot)

        history = []
        provider_runs = []
        facts_used = []
        final_content = ""
        final_quote = ""

        for stage_index, (stage_name, stage_prompt) in enumerate(prepared["stages"], start=1):
            stage_request = {
                **{k: v for k, v in prepared.items() if k != "stages"},
                "stage_name": stage_name,
                "stage_index": stage_index,
                "stage_count": len(prepared["stages"]),
                "stage_prompt": stage_prompt,
                "prior_stage_outputs": history,
            }
            self._log_stage(key, employee, "工程開始", stage_name, {"index": stage_index})
            try:
                result = self.provider.execute(stage_request)
            except ProviderUnavailable:
                with self.workspace.transaction() as db:
                    self.workspace.log(db, key, employee, "failed", "OPENAI_UNAVAILABLE", candidate)
                raise
            except ProviderError as exc:
                if getattr(exc, "technical", True):
                    self._record_technical_error(key, employee, candidate, exc)
                else:
                    with self.workspace.transaction() as db:
                        self.workspace.log(db, key, employee, "failed", "OPENAI_PROVIDER_ERROR", candidate)
                raise

            provider_meta = result.pop("_provider", {})
            provider_runs.append({"stage": stage_name, **provider_meta})

            if result.get("decision") == "stop":
                self._log_stage(
                    key, employee, "工程停止", stage_name,
                    {"reason": result.get("stop_reason"), "missing": result.get("missing_or_unknown")},
                )
                with self.workspace.transaction() as db:
                    self.workspace.log(db, key, employee, "stopped", result.get("stop_reason", "OPENAI_STOP"), candidate)
                return {
                    "kind": "stop",
                    "stop_reason": result["stop_reason"],
                    "stop_stage": stage_name,
                    "missing_or_unknown": result["missing_or_unknown"],
                    "confirmed_facts": result["confirmed_facts"],
                    "question_for_coco": result["question_for_coco"],
                    "provider": provider_meta,
                    "provider_runs": provider_runs,
                }

            if result.get("decision") != "complete":
                with self.workspace.transaction() as db:
                    self.workspace.log(db, key, employee, "failed", "OPENAI_DECISION", candidate)
                raise ProviderError("OpenAI decision was neither complete nor stop")

            stage_output = result.get("content", "")
            stage_quote = result.get("quote", "")
            history.append({
                "stage": stage_name,
                "content": stage_output,
                "quote": stage_quote,
                "facts_used": result.get("facts_used", []),
                "checklist": result.get("checklist", []),
            })
            if result.get("facts_used"):
                facts_used = result["facts_used"]
            if stage_quote:
                final_quote = stage_quote
            # ⑤ is a review result. "問題ありません" must not overwrite the
            # completed body produced by ④. Canon text remains untouched.
            if stage_name != "⑤":
                final_content = self._body_only(stage_output) if stage_name == "④" else stage_output
            elif stage_output.strip() != "問題ありません":
                self._log_stage(
                    key, employee, "最終確認指摘", stage_name,
                    {"review_output": stage_output},
                )
            self._log_stage(key, employee, "工程完了", stage_name, {"index": stage_index})

        # If ⑤ found a substantive issue, feed that exact review back to ④ once,
        # then run ⑤ again. This applies the existing canon review instead of
        # saving the pre-review body.
        last_review = next(
            (x for x in reversed(history) if x.get("stage") == "⑤"),
            None,
        )
        if last_review and last_review.get("content", "").strip() != "問題ありません":
            review_feedback = last_review.get("content", "").strip()
            base_history = [x for x in history if x.get("stage") not in {"④", "⑤"}]
            revised_history = list(base_history)
            revised_content = final_content
            revised_quote = final_quote
            for stage_index, (stage_name, stage_prompt) in enumerate(prepared["stages"], start=1):
                if stage_name not in {"④", "⑤"}:
                    continue
                stage_request = {
                    **{k: v for k, v in prepared.items() if k != "stages"},
                    "stage_name": stage_name,
                    "stage_index": stage_index,
                    "stage_count": len(prepared["stages"]),
                    "stage_prompt": stage_prompt,
                    "prior_stage_outputs": revised_history,
                    "completion_feedback": ["⑤指摘: " + review_feedback],
                }
                self._log_stage(
                    key, employee, "最終確認修正", stage_name,
                    {"review_output": review_feedback},
                )
                result = self.provider.execute(stage_request)
                provider_meta = result.pop("_provider", {})
                provider_runs.append({"stage": stage_name, "review_correction": True, **provider_meta})
                if result.get("decision") == "stop":
                    self._log_stage(
                        key, employee, "工程停止", stage_name,
                        {"reason": result.get("stop_reason"), "missing": result.get("missing_or_unknown")},
                    )
                    return {
                        "kind": "stop",
                        "stop_reason": result["stop_reason"],
                        "stop_stage": stage_name,
                        "missing_or_unknown": result["missing_or_unknown"],
                        "confirmed_facts": result["confirmed_facts"],
                        "question_for_coco": result["question_for_coco"],
                        "provider": provider_meta,
                        "provider_runs": provider_runs,
                    }
                if result.get("decision") != "complete":
                    raise ProviderError("OpenAI decision was neither complete nor stop")
                stage_output = result.get("content", "")
                stage_quote = result.get("quote", "")
                revised_history.append({
                    "stage": stage_name,
                    "content": stage_output,
                    "quote": stage_quote,
                    "facts_used": result.get("facts_used", []),
                    "checklist": result.get("checklist", []),
                })
                if stage_quote:
                    revised_quote = stage_quote
                if stage_name == "④":
                    revised_content = self._body_only(stage_output)

            history = revised_history
            final_content = revised_content
            final_quote = revised_quote
            last_review = next(
                (x for x in reversed(history) if x.get("stage") == "⑤"),
                None,
            )
            if last_review and last_review.get("content", "").strip() != "問題ありません":
                self._record_process_incomplete(
                    key, employee,
                    {
                        "ok": False,
                        "failures": ["最終確認指摘が未解消"],
                        "continue_stage": "④",
                        "facts_count": len(facts_used),
                        "checklist_count": len(next(
                            (x.get("checklist") or [] for x in reversed(history) if x.get("stage") == "④"),
                            [],
                        )),
                    },
                )
                return {
                    "kind": "incomplete",
                    "continue_stage": "④",
                    "format_failures": ["最終確認指摘が未解消"],
                    "stage_outputs": history,
                    "provider": provider_runs[-1] if provider_runs else {},
                    "provider_runs": provider_runs,
                }

        completion = self._completion_check(prepared["platform"], final_content, history)
        if not completion["ok"]:
            self._record_process_incomplete(key, employee, completion)

            # Mechanical continuation only: do not involve manager/secretary/VP.
            # Re-run the content-producing stage and final review with the same employee.
            base_history = [x for x in history if x.get("stage") not in {"④", "⑤"}]
            retry_history = list(base_history)
            retry_content = final_content
            retry_quote = final_quote
            for stage_index, (stage_name, stage_prompt) in enumerate(prepared["stages"], start=1):
                if stage_name not in {"④", "⑤"}:
                    continue
                stage_request = {
                    **{k: v for k, v in prepared.items() if k != "stages"},
                    "stage_name": stage_name,
                    "stage_index": stage_index,
                    "stage_count": len(prepared["stages"]),
                    "stage_prompt": stage_prompt,
                    "prior_stage_outputs": retry_history,
                    "completion_feedback": completion["failures"],
                }
                self._log_stage(
                    key, employee, "工程続行", stage_name,
                    {"reason": "工程未完了", "failures": completion["failures"]},
                )
                try:
                    result = self.provider.execute(stage_request)
                except ProviderUnavailable:
                    with self.workspace.transaction() as db:
                        self.workspace.log(db, key, employee, "failed", "OPENAI_UNAVAILABLE", candidate)
                    raise
                except ProviderError as exc:
                    if getattr(exc, "technical", True):
                        self._record_technical_error(key, employee, candidate, exc)
                    else:
                        with self.workspace.transaction() as db:
                            self.workspace.log(db, key, employee, "failed", "OPENAI_PROVIDER_ERROR", candidate)
                    raise

                provider_meta = result.pop("_provider", {})
                provider_runs.append({"stage": stage_name, "continuation": True, **provider_meta})
                if result.get("decision") == "stop":
                    self._log_stage(
                        key, employee, "工程停止", stage_name,
                        {"reason": result.get("stop_reason"), "missing": result.get("missing_or_unknown")},
                    )
                    with self.workspace.transaction() as db:
                        self.workspace.log(db, key, employee, "stopped", result.get("stop_reason", "OPENAI_STOP"), candidate)
                    return {
                        "kind": "stop",
                        "stop_reason": result["stop_reason"],
                        "stop_stage": stage_name,
                        "missing_or_unknown": result["missing_or_unknown"],
                        "confirmed_facts": result["confirmed_facts"],
                        "question_for_coco": result["question_for_coco"],
                        "provider": provider_meta,
                        "provider_runs": provider_runs,
                    }
                if result.get("decision") != "complete":
                    raise ProviderError("OpenAI decision was neither complete nor stop")

                stage_output = result.get("content", "")
                stage_quote = result.get("quote", "")
                retry_history.append({
                    "stage": stage_name,
                    "content": stage_output,
                    "quote": stage_quote,
                    "facts_used": result.get("facts_used", []),
                    "checklist": result.get("checklist", []),
                })
                if stage_quote:
                    retry_quote = stage_quote
                if stage_name == "④":
                    retry_content = self._body_only(stage_output)
                self._log_stage(key, employee, "工程完了", stage_name, {"continuation": True})

            history = retry_history
            final_content = retry_content
            final_quote = retry_quote
            completion = self._completion_check(prepared["platform"], final_content, history)
            if not completion["ok"]:
                self._record_process_incomplete(key, employee, completion)
                return {
                    "kind": "incomplete",
                    "continue_stage": completion["continue_stage"],
                    "format_failures": completion["failures"],
                    "stage_outputs": history,
                    "provider": provider_runs[-1] if provider_runs else {},
                    "provider_runs": provider_runs,
                }

        save_payload = {
            "theme": state_snapshot["theme"],
            "axis": state_snapshot["axis"],
            "status": "OK",
            "findings": [],
            "fields": {
                "content": final_content,
                "quote": final_quote,
            },
        }
        saved = self.save_result(
            key, candidate, employee,
            state_snapshot["revision"], state_snapshot["candidate_revision"],
            save_payload
        )
        return {
            "kind": "complete",
            "state": saved,
            "facts_used": facts_used,
            "stage_outputs": history,
            "provider": provider_runs[-1] if provider_runs else {},
            "provider_runs": provider_runs,
            "completion_check": completion,
        }

    def _execute_v2(self, key, candidate, employee, prepared, snapshot):
        """Keep v2 public source and candidate checks separate from v1 reviews."""
        history, runs, candidates = [], [], []
        quote, facts, public_material, source_map = "", [], "", []
        type_off = False
        recorded_tags = set()
        prompts = dict(prepared["stages"])

        def run(name, feedback=None):
            nonlocal quote, facts, candidates, public_material, source_map, type_off
            request = {**prepared, "stage_name": name, "stage_prompt": prompts[name],
                       "prior_stage_outputs": history, "completion_feedback": feedback,
                       "stage_index": len(history) + 1, "stage_count": len(prompts)}
            request["material"] = public_material or prepared["material"]
            if public_material:
                request["prior_stage_outputs"] = [({"stage": "一般化", "content": public_material, "public_material": public_material} if x["stage"] == "一般化" else x) for x in history]
            request["canon_preamble"] += "\n" + prepared["canon_common"]
            if name == "④":
                request["canon_preamble"] += "\n【v2の型適用条件・④にも優先適用】\n" + prompts["④'"].split("### 3-2")[0]
                request["canon_preamble"] += "\n型に必要な事実がないだけなら④で素材不足として止めず、正典④'の型外しで事実を足さず完成案を出す。型を外したらaudit_tagsに記録する。"
            self._log_stage(key, employee, "工程開始", name, {})
            try:
                result = self.provider.execute(request)
            except ProviderError as exc:
                if exc.technical:
                    self._record_technical_error(key, employee, candidate, exc)
                raise
            if name == "一般化" and result.get("decision") == "complete":
                literal_quotes = re.findall(r"「[^」]+」", prepared["material"])
                for retry in range(2):
                    missing_quotes = [q for q in literal_quotes if q not in result.get("public_material", "")]
                    if not missing_quotes:
                        break
                    runs.append({"stage": name, **result.pop("_provider", {})})
                    request["completion_feedback"] = ["原素材の実際のセリフは変えない。公開用素材にそのまま保持する引用: " + "、".join(missing_quotes) + "。核の事実の行動・時系列は変えず、登場人物と場面だけ一般化する。"]
                    result = self.provider.execute(request)
                if any(q not in result.get("public_material", "") for q in literal_quotes):
                    return {"kind": "incomplete", "continue_stage": "一般化", "format_failures": ["実際のセリフが一般化で失われた"], "stage_outputs": history}
            runs.append({"stage": name, **result.pop("_provider", {})})
            if result.get("decision") == "stop":
                return {"kind": "stop", "stop_stage": name,
                        **{k: result.get(k, "") for k in ("stop_reason", "missing_or_unknown", "confirmed_facts", "question_for_coco", "material_suggestions")},
                        "stage_outputs": history, "provider_runs": runs}
            if result.get("decision") != "complete":
                raise ProviderError("Invalid v2 stage decision")
            output = {"stage": name, **result}
            history.append(output)
            if name == "一般化":
                public_material = result.get("public_material", "").strip()
                source_map = result.get("source_map") or []
                if not public_material or not source_map:
                    return {"kind": "incomplete", "continue_stage": "一般化", "format_failures": ["公開用素材・対応表が未記録"], "stage_outputs": history}
                self._log_stage(key, employee, "一般化記録", name, {"public_material": public_material, "source_map": source_map})
            if result.get("quote"):
                quote = result["quote"]
            if result.get("facts_used"):
                facts = result["facts_used"]
            if result.get("candidates") and name not in {"①", "ひとこと選び"}:
                candidates = result["candidates"]
            if name == "④'" and candidates:
                first_parts = [self._paragraphs(body)[0] for body in candidates if self._paragraphs(body)]
                if first_parts and any("のに" not in first for first in first_parts):
                    result.setdefault("audit_tags", []).append("型外し（" + prepared["platform"] + "・④💗）")
            for tag in result.get("audit_tags") or []:
                if tag.startswith("型外し"):
                    type_off = True
                    tag = "型外し（" + prepared["platform"] + "・冒頭型）"
                    from .routing import RoutingEngine
                    if tag not in recorded_tags:
                        RoutingEngine(self.workspace).record_exception(key, prepared["platform"], tag)
                        recorded_tags.add(tag)
            self._log_stage(key, employee, "工程完了", name, {"output": output})
            return None

        for name in ("一般化", "①", "ひとこと選び", "②", "③", "④", "④'", "⑤"):
            stopped = run(name)
            if stopped:
                return stopped
            if name == "④'" and type_off and len(set(candidates)) < 2:
                stopped = run("④'", ["冒頭の型を外しているため3-3〜3-4に従い異なる本文候補を複数のまま残す。最終確認を通さず、各候補を⑤だけで仕上げる。核の事実3点と使わない言葉の条件は守る。"])
                if stopped:
                    return stopped
                if len(set(candidates)) < 2:
                    return {"kind": "incomplete", "continue_stage": "④'", "format_failures": ["型外し本文候補が複数でない"], "stage_outputs": history}
        if not candidates:
            return {"kind": "incomplete", "continue_stage": "④'", "format_failures": ["本文候補が未記録"], "stage_outputs": history}
        banned = ("あなた", "みんな", "でいい", "でもいい", "てもいい", "んです", "渡す", "確立", "繋がり", "循環", "気づき")
        for correction in range(3):
            failures = [word for word in banned if any(word in body for body in candidates)] if prepared["platform"] == "Threads" else []
            if prepared["platform"] == "Threads":
                for body in candidates:
                    paragraphs = self._paragraphs(body)
                    if len(paragraphs) != 6:
                        failures.append("6段構成")
                    elif "相手" not in paragraphs[3]:
                        failures.append("4段目が相手との関係の仕組みになっていない")
                    if len(paragraphs) == 6 and paragraphs[4].rstrip().endswith("ひとつ。"):
                        failures.append("5段目を『〜してみては』『〜してみること』等の明確な読者への提案形にする。『〜をひとつ。』の言い切りは使わない")
                    if paragraphs and paragraphs[-1] != "感情はある。依存はしない。":
                        failures.append("6段目の定型句を保持する")
            if not failures:
                break
            if correction == 2:
                return {"kind": "incomplete", "continue_stage": "⑤", "format_failures": ["正典の使わない言葉: " + ",".join(failures)], "stage_outputs": history}
            stopped = run("⑤", ["正典の使わない言葉が残っている: " + ",".join(failures) + "。該当段だけ直し、核の事実を保つ。4段目は『相手の』で相手を仕組みの中に置き、出来事の繰り返しや気持ちの決めつけではなく関係の仕組みを言い切る。5段目は比喩を使わず具体的な読者への提案形。型外しでも4段目・5段目・使わない言葉の条件は外さない。6段目は『感情はある。依存はしない。』で固定する。"])
            if stopped:
                return stopped
        if not type_off:
            for round_no in range(3):
                if round_no == 2:
                    stopped = run("⑤", ["最終確認2回目の不備。3-6に従い媒体の声の三者会議で直し、最終確認は再実行しない。"])
                    if stopped:
                        return stopped
                    break
                stopped = run("最終確認")
                if stopped:
                    return stopped
                if history[-1]["content"].strip() == "問題ありません":
                    break
                self._log_stage(key, employee, "最終確認不備", "最終確認", {"round": round_no + 1, "review": history[-1]["content"]})
                if round_no == 0:
                    stopped = run("⑤", ["最終確認1回目の不備。3-6に従いテーマ・軸・核の事実3点を見直し、外れた段だけ直す。"])
                    if stopped:
                        return stopped
        fixed_candidates = list(candidates)
        for round_no in range(3):
            stopped = run("⑦", ["本文候補は固定。通過した完成本文のみcandidatesへ返す。全案が落ちた場合だけ正典どおり停止する。"])
            if stopped:
                return stopped
            if candidates and all(body in fixed_candidates for body in candidates):
                break
            candidates = list(fixed_candidates)
            if round_no == 2:
                return {"kind": "incomplete", "continue_stage": "⑦", "format_failures": ["⑦で固定本文が変更された"], "stage_outputs": history}
            for name in ("①", "ひとこと選び"):
                stopped = run(name, ["⑦の確認により、本文固定でひとことだけ再選定する。"])
                if stopped:
                    return stopped
        body = candidates[0]
        check = {"ok": bool(body.strip() and quote.strip() and public_material and source_map), "canon_version": "v2", "candidate_count": len(candidates)}
        saved = self.save_result(key, candidate, employee, snapshot["revision"], snapshot["candidate_revision"],
            {"theme": snapshot["theme"], "axis": snapshot["axis"], "status": "OK", "findings": [], "fields": {"content": body, "quote": quote}})
        return {"kind": "complete", "state": saved, "stage_outputs": history, "provider_runs": runs,
                "public_material": public_material, "source_map": source_map, "facts_used": facts, "completion_check": check, "candidates": candidates}

    def review_vp(self, key, candidate):
        """Run the independent VP gate from source + completed post only."""
        source_row = self.workspace.source(key)
        source = source_row["source"]
        material = source.get("material")
        if not isinstance(material, str) or not material.strip():
            material = source.get("source_material")
        if not isinstance(material, str) or not material.strip():
            material = source.get("raw_material")
        if not isinstance(material, str) or not material.strip():
            raise ProviderError("VP material is required", technical=False)

        state = self.workspace.get(key)
        completed_post = state["candidates"][candidate]["fields"].get("content", "")
        if not isinstance(completed_post, str) or not completed_post.strip():
            raise ProviderError("VP completed post is required", technical=False)

        voice_rule = (
            "完成投稿が凛とした軍師Cocoの声として明らかに混線している場合。"
            if state["platform"] == "X"
            else "完成投稿が慈愛に満ちた哲学者Cocoの声として明らかに混線している場合。"
        )
        with self.workspace.transaction() as db:
            coco_resolution = self._coco_resolution(key, db)
            has_rules = db.execute("SELECT 1 FROM sqlite_master WHERE name='rule_versions'").fetchone()
            rule = db.execute("SELECT r.rule_key FROM workflow_cases c LEFT JOIN rule_versions r ON r.id=c.rule_version WHERE c.case_id=?", (key,)).fetchone() if has_rules else None
            is_v2 = bool(rule and rule["rule_key"] == "canon_v2")
            if is_v2:
                row = db.execute("SELECT detail FROM workflow_events WHERE case_id=? AND action='一般化記録' ORDER BY id DESC LIMIT 1", (key,)).fetchone()
                if not row:
                    raise ProviderError("v2 VP public material is missing", technical=False)
                material = json.loads(row["detail"])["public_material"]
        case_instruction = ""
        if isinstance(coco_resolution, dict) and coco_resolution.get("action") == "case_instruction":
            case_instruction = str(coco_resolution.get("instruction", "")).strip()

        fact_rule = (
            "素材原文にない事実の追加、素材の意味を変える言い換え、主語・時系列・発言内容の変形が"
            "完成投稿にある場合。単なる語調の好みでは戻さない。"
        )
        if case_instruction:
            fact_rule += (
                " ただし、この案件についてCocoが明示した案件単位の回答は正典変更ではなく、"
                "その案件の判定条件として優先する。Coco回答: " + case_instruction
            )
            if "5段目" in case_instruction and "提案形" in case_instruction:
                fact_rule += (
                    " この案件では5段目が読者への提案として文法上明確な形"
                    "（例：『〜してみる』『〜してみること』『〜してみては』等）なら、"
                    "素材原文に同じ行動がなくても『素材にない出来事』とは判定しない。"
                    "Coco自身がした行動・予定・決意として読める場合だけ事実判定の対象にする。"
                )

        if is_v2:
            fact_rule = ("公開用素材を基準に核の事実3点が曲がった場合、または公開用素材にない出来事を足した場合だけ戻す。"
                         "5段目（Threads）／4行目の一手（X）は読者への提案であり事実ではない。提案形なら素材にない出来事の追加に当たらない。"
                         "Coco自身の行動・予定・決意として読める場合は事実が曲がったとして戻す。")

        criteria = {
            "事実が曲がった": fact_rule,
            "声が混ざった": voice_rule,
            "工程に戻っていない": (
                "完成投稿そのものに、直すべき不整合が残ったまま完成扱いになった痕跡が明確にある場合。"
                "途中工程や社員の推論は見えないため、完成投稿から確認できる範囲だけで判定する。"
            ),
        }

        try:
            result = self.provider.review_vp(material, completed_post, criteria)
        except ProviderError as exc:
            if getattr(exc, "technical", True):
                attempts = getattr(exc, "attempts", []) or [{}]
                last = attempts[-1]
                self._log_stage(
                    key,
                    "副社長",
                    "技術エラー",
                    "副社長確認",
                    {
                        "発生工程": "副社長確認",
                        "attempt番号": last.get("attempt"),
                        "API完了状態": last.get("status"),
                        "incomplete理由": last.get("incomplete_reason"),
                        "output token数": last.get("output_tokens"),
                        "reasoning token数": last.get("reasoning_tokens"),
                        "上限値": last.get("max_output_tokens"),
                        "エラー種別": last.get("error_type") or type(exc).__name__,
                        "attempts": attempts,
                    },
                )
            raise

        provider_meta = result.pop("_provider", {})
        decision = result.get("decision")
        finding = result.get("finding")
        source_quote = result.get("source_quote", "")
        post_quote = result.get("post_quote", "")
        valid_findings = {"none", "事実が曲がった", "声が混ざった", "工程に戻っていない"}
        if decision not in {"通す", "戻す"} or finding not in valid_findings:
            raise ProviderError("VP decision schema was invalid", technical=False)
        if decision == "通す" and finding != "none":
            raise ProviderError("VP pass must use finding=none", technical=False)
        if decision == "戻す" and finding == "none":
            raise ProviderError("VP return requires one of the three findings", technical=False)

        if decision == "戻す":
            if source_quote not in material or post_quote not in completed_post:
                raise ProviderError("VP quote pair was not found verbatim in source/post", technical=False)
        else:
            source_quote = ""
            post_quote = ""

        self._log_stage(
            key,
            "副社長",
            "3点レビュー",
            "副社長確認",
            {
                "decision": decision,
                "finding": finding,
                "source_quote": source_quote,
                "post_quote": post_quote,
            },
        )
        return {
            "decision": decision,
            "finding": None if finding == "none" else finding,
            "source_quote": source_quote,
            "post_quote": post_quote,
            "provider": provider_meta,
        }

    def save_result(self, key, candidate, employee, expected_revision,
                    expected_candidate_revision, result):
        return self.workspace.save_ai_result(
            key, candidate, employee, expected_revision,
            expected_candidate_revision, result
        )
