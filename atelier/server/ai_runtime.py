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

    def _canon_stages(self, prompt):
        return [(name, self._section(prompt, starts)) for name, starts in self.STAGES]

    def _coco_resolution(self, key, db):
        if db is None:
            return None
        has_events = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_events'"
        ).fetchone()
        if not has_events:
            return None
        row = db.execute(
            "SELECT detail FROM workflow_events WHERE case_id=? AND action='このまま進める' ORDER BY id DESC LIMIT 1",
            (key,),
        ).fetchone()
        if not row:
            return None
        detail = json.loads(row["detail"])
        return {
            "action": "proceed_without_missing_fact",
            "missing_or_unknown": detail.get("不足・不明点", ""),
        }

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
        prompt_path = self.workspace.root / person["prompt_ref"]
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
            "stages": self._canon_stages(full_canon),
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
                final_content = stage_output
            elif stage_output.strip() != "問題ありません":
                self._log_stage(
                    key, employee, "最終確認指摘", stage_name,
                    {"review_output": stage_output},
                )
            self._log_stage(key, employee, "工程完了", stage_name, {"index": stage_index})

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
                    retry_content = stage_output
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
        criteria = {
            "事実が曲がった": (
                "素材原文にない事実の追加、素材の意味を変える言い換え、主語・時系列・発言内容の変形が"
                "完成投稿にある場合。単なる語調の好みでは戻さない。"
            ),
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
