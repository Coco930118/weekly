"""Provider adapter boundary.

Drives the current (single-system) Atelier canon's own section headings in
order, one stage per provider call, passing each stage's output forward to
the next stage for the same employee. The canon text itself is never
rewritten here — this module only calls it, in the order `atelier/canon/
x_post.md` / `threads_post.md` §0 already specify, and defers all rule
content (banned words, structural checks, the 4-line/6-段 type, etc.) to the
canon text and to the existing 副社長3点関所 / brand_check gates. It does not
duplicate those rules in Python.

Which provider runs a role is config, not instruction content (`atelier/
canon/*.md` is identical regardless of provider; `docs/coco_atelier_company_
spec.md`「プロバイダの役割分担」records which provider ran which stage).
"""
import json
import os

from .anthropic_driver import AnthropicDriver
from .openai_driver import OpenAIDriver, ProviderUnavailable, ProviderError

# role (employee `kind`) -> provider name. None = no model (監査委員会・秘書・design).
ROLE_PROVIDERS = {
    "material_interview": "anthropic",
    "post_owner": "anthropic",
    "management": "openai",       # 課長・副社長
    "board": "openai",            # 取締役会
    "audit": None,                # 監査委員会
    "secretary": None,            # 社長Coco秘書
    "design": None,               # TOP OF 敏腕空間デザイナー
}

# (stage name, canon section header prefixes). Both canon files use the same
# non-platform-specific heading text for 一般化/④'/⑧; ①②③④・ひとこと選びの見出しは
# 媒体ごとに絵文字が違うので両方を候補にする。
CANON_STAGES = [
    ("一般化", ("## 2. 一般化工程",)),
    ("①", ("## ①🧳ひとこと", "## ①💗ひとこと")),
    ("ひとこと選び", ("## ひとこと選び🧳", "## ひとこと選び💗")),
    ("②", ("## ②🧳", "## ②💗")),
    ("④", ("## ④🧳", "## ④💗")),
    ("③", ("## ③🧳", "## ③💗")),
    ("④'", ("## ④' モヤっと確認",)),
    ("⑧", ("## ⑧ 橋の確認",)),
]


class AIRuntime:
    def __init__(self, workspace):
        self.workspace = workspace
        self.providers = {"anthropic": AnthropicDriver(), "openai": OpenAIDriver()}

    def _provider_for(self, employee):
        person = self.workspace.employee(employee)
        provider_name = ROLE_PROVIDERS.get(person["kind"])
        return self.providers.get(provider_name) if provider_name else None

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
            if lines[i].startswith("## ") and i != start:
                end = i
                break
        return "\n".join(lines[start:end]).strip()

    def _canon_stages(self, prompt):
        return [(name, self._section(prompt, starts)) for name, starts in CANON_STAGES]

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
                "instruction": "\n".join(f"{i+1}. {item}" for i, item in enumerate(instructions)),
                "instructions": instructions,
            }
        if proceed:
            detail = json.loads(proceed["detail"])
            return {"action": "proceed_without_missing_fact", "missing_or_unknown": detail.get("不足・不明点", "")}
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

    @staticmethod
    def _material_from_source(source):
        for key in ("material", "source_material", "raw_material"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _material_from_interview(db, key):
        """取材社員の公開用素材（atelier/canon/interview.md）。あれば素材ファイルより優先する
        （素材ファイル経由はやめる、の実装）。呼び出し元が開いたトランザクションのdbを使う——
        ここで新しいtransaction()を開くとSQLiteの排他ロックで自己デッドロックする。"""
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='material_interviews'"
        ).fetchone()
        if not exists:
            return None
        row = db.execute(
            "SELECT public_material,status FROM material_interviews WHERE case_id=? AND status='完了'", (key,)
        ).fetchone()
        if not row or not row["public_material"]:
            return None
        fields = json.loads(row["public_material"])
        return "\n".join(f"{k}：{v}" for k, v in fields.items())

    def _prepare_request(self, key, state, person, db):
        source_row = self.workspace.source(key)
        source = source_row["source"]
        prompt_path = self.workspace.root / person["prompt_ref"]
        full_canon = prompt_path.read_text()
        material = self._material_from_interview(db, key) or self._material_from_source(source)
        if material is None:
            from .server import WorkspaceError
            raise WorkspaceError("MATERIAL_REQUIRED", "providerへ送る素材フィールドが明示されていません")
        return {
            "employee": person["id"],
            "platform": state["platform"],
            "material": material,
            "canon_preamble": (
                "以下はCoco確定正典の工程を、原文のまま順番に実行する。"
                "各呼び出しでは指定された1工程だけを実行し、その工程で得た成果物を返す。"
                "『本文には進まない』等の記述は、その呼び出し内で次工程を実行しないという意味であり、"
                "投稿全体の終了を意味しない。素材不足・事実不明・指示外は正典どおり停止する。"
            ),
            "stages": self._canon_stages(full_canon),
        }

    def _record_technical_error(self, key, employee, candidate, exc, provider_name):
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
                    "provider": provider_name,
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
                    (key, employee, action, stage_name, json.dumps(detail or {}, ensure_ascii=False)),
                )

    def execute(self, key, candidate, employee, expected_revision, expected_candidate_revision):
        error = None
        provider = None
        provider_name = None
        prepared = None
        state_snapshot = None
        with self.workspace.transaction() as db:
            try:
                state = self.workspace._load(db, key)
                self.workspace.check_revision(state, expected_revision)
                self.workspace.check_candidate_revision(state, candidate, expected_candidate_revision)
                person = self.workspace.employee(employee)
                if person["media"] and state["platform"] not in person["media"]:
                    from .server import WorkspaceError
                    raise WorkspaceError("PERMISSION", "担当媒体の権限がありません")
                provider = self._provider_for(employee)
                provider_name = ROLE_PROVIDERS.get(person["kind"])
                if provider is None or not provider.connected:
                    self.workspace.log(db, key, employee, "blocked", "AI_DISABLED", candidate)
                    provider = None
                else:
                    prepared = self._prepare_request(key, state, person, db)
                    state_snapshot = {
                        "theme": state["theme"],
                        "axis": state["axis"],
                        "revision": state["revision"],
                        "candidate_revision": state["candidates"][candidate]["revision"],
                    }
                    self.workspace.log(db, key, employee, "started", f"{provider_name.upper()}_ORCHESTRATED", candidate)
            except Exception as exc:
                from .server import WorkspaceError
                if not isinstance(exc, WorkspaceError):
                    raise
                error = exc
                self.workspace.log(db, key, employee, "blocked", exc.code, candidate)
        if error:
            raise error
        if provider is None:
            raise ProviderUnavailable("AI未接続：この社員のproviderは有効化されていません")

        history = []
        provider_runs = []
        facts_used = []
        candidates = []
        quote = ""
        final_content = ""
        public_material = ""
        source_map = []

        for stage_index, (stage_name, stage_prompt) in enumerate(prepared["stages"], start=1):
            stage_request = {
                **{k: v for k, v in prepared.items() if k != "stages"},
                "material": public_material or prepared["material"],
                "stage_name": stage_name,
                "stage_index": stage_index,
                "stage_count": len(prepared["stages"]),
                "stage_prompt": stage_prompt,
                "prior_stage_outputs": history,
                "coco_resolution": self._coco_resolution(key, None),
                "vp_return_feedback": self._vp_return_feedback(key),
            }
            self._log_stage(key, employee, "工程開始", stage_name, {"index": stage_index, "provider": provider_name})
            try:
                result = provider.execute(stage_request)
            except ProviderUnavailable:
                with self.workspace.transaction() as db:
                    self.workspace.log(db, key, employee, "failed", "PROVIDER_UNAVAILABLE", candidate)
                raise
            except ProviderError as exc:
                if getattr(exc, "technical", True):
                    self._record_technical_error(key, employee, candidate, exc, provider_name)
                else:
                    with self.workspace.transaction() as db:
                        self.workspace.log(db, key, employee, "failed", "PROVIDER_ERROR", candidate)
                raise

            provider_meta = result.pop("_provider", {})
            provider_runs.append({"stage": stage_name, "provider": provider_name, **provider_meta})

            if result.get("decision") == "stop":
                self._log_stage(key, employee, "工程停止", stage_name,
                                 {"reason": result.get("stop_reason"), "missing": result.get("missing_or_unknown")})
                with self.workspace.transaction() as db:
                    self.workspace.log(db, key, employee, "stopped", result.get("stop_reason", "PROVIDER_STOP"), candidate)
                return {
                    "kind": "stop",
                    "stop_reason": result.get("stop_reason"),
                    "stop_stage": stage_name,
                    "missing_or_unknown": result.get("missing_or_unknown"),
                    "confirmed_facts": result.get("confirmed_facts"),
                    "question_for_coco": result.get("question_for_coco"),
                    "material_suggestions": result.get("material_suggestions"),
                    "provider": provider_meta,
                    "provider_runs": provider_runs,
                }
            if result.get("decision") != "complete":
                with self.workspace.transaction() as db:
                    self.workspace.log(db, key, employee, "failed", "PROVIDER_DECISION", candidate)
                raise ProviderError(f"{provider_name} decision was neither complete nor stop")

            history.append({"stage": stage_name, **result})
            if stage_name == "一般化":
                public_material = (result.get("public_material") or "").strip()
                source_map = result.get("source_map") or []
                if not public_material or not source_map:
                    return {"kind": "incomplete", "continue_stage": "一般化",
                            "format_failures": ["公開用素材・対応表が未記録"], "stage_outputs": history,
                            "provider_runs": provider_runs}
                self._log_stage(key, employee, "一般化記録", stage_name,
                                 {"public_material": public_material, "source_map": source_map})
            if result.get("quote"):
                quote = result["quote"]
            if result.get("facts_used"):
                facts_used = result["facts_used"]
            if result.get("candidates"):
                candidates = result["candidates"]
            if stage_name in ("④", "④'") and candidates:
                final_content = candidates[0]
            self._log_stage(key, employee, "工程完了", stage_name, {"index": stage_index})

        if not final_content.strip():
            return {"kind": "incomplete", "continue_stage": "④", "format_failures": ["本文候補が未記録"],
                    "stage_outputs": history, "provider_runs": provider_runs}

        save_payload = {
            "theme": state_snapshot["theme"], "axis": state_snapshot["axis"],
            "status": "OK", "findings": [],
            "fields": {"content": final_content, "quote": quote},
        }
        saved = self.save_result(key, candidate, employee, state_snapshot["revision"],
                                  state_snapshot["candidate_revision"], save_payload)
        return {
            "kind": "complete", "state": saved, "facts_used": facts_used,
            "public_material": public_material, "source_map": source_map,
            "candidates": candidates, "stage_outputs": history,
            "provider": provider_runs[-1] if provider_runs else {}, "provider_runs": provider_runs,
        }

    def review_vp(self, key, candidate):
        """Run the independent VP gate from source + completed post only."""
        source_row = self.workspace.source(key)
        material = self._material_from_source(source_row["source"])
        state = self.workspace.get(key)
        with self.workspace.transaction() as db:
            row = db.execute(
                "SELECT detail FROM workflow_events WHERE case_id=? AND action='一般化記録' ORDER BY id DESC LIMIT 1",
                (key,),
            ).fetchone() if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_events'"
            ).fetchone() else None
        if row:
            material = json.loads(row["detail"])["public_material"]
        if not isinstance(material, str) or not material.strip():
            raise ProviderError("VP material is required", technical=False)

        completed_post = state["candidates"][candidate]["fields"].get("content", "")
        if not isinstance(completed_post, str) or not completed_post.strip():
            raise ProviderError("VP completed post is required", technical=False)

        provider = self._provider_for("VP")
        provider_name = ROLE_PROVIDERS.get(self.workspace.employee("VP")["kind"])
        if provider is None:
            raise ProviderUnavailable("AI未接続：副社長のproviderは有効化されていません")

        voice_rule = (
            "完成投稿が凛とした軍師Cocoの声として明らかに混線している場合。"
            if state["platform"] == "X" else
            "完成投稿が慈愛に満ちた哲学者Cocoの声として明らかに混線している場合。"
        )
        fact_rule = (
            "公開用素材を基準に核の事実3点が曲がった場合、または公開用素材にない出来事を足した場合だけ戻す。"
            "4行目の一手（X）／5段目の一手（Threads）は読者への提案であり事実ではない。"
            "提案形なら素材にない出来事の追加に当たらない。"
            "Coco自身の行動・予定・決意として読める場合は事実が曲がったとして戻す。"
        )
        criteria = {
            "事実が曲がった": fact_rule,
            "声が混ざった": voice_rule,
            "工程に戻っていない": (
                "完成投稿そのものに、直すべき不整合が残ったまま完成扱いになった痕跡が明確にある場合。"
                "途中工程や社員の推論は見えないため、完成投稿から確認できる範囲だけで判定する。"
            ),
        }

        try:
            result = provider.review_vp(material, completed_post, criteria)
        except ProviderError as exc:
            if getattr(exc, "technical", True):
                attempts = getattr(exc, "attempts", []) or [{}]
                last = attempts[-1]
                self._log_stage(key, "副社長", "技術エラー", "副社長確認", {
                    "発生工程": "副社長確認", "provider": provider_name,
                    "attempt番号": last.get("attempt"), "API完了状態": last.get("status"),
                    "incomplete理由": last.get("incomplete_reason"), "output token数": last.get("output_tokens"),
                    "reasoning token数": last.get("reasoning_tokens"), "上限値": last.get("max_output_tokens"),
                    "エラー種別": last.get("error_type") or type(exc).__name__, "attempts": attempts,
                })
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
            source_quote, post_quote = "", ""

        self._log_stage(key, "副社長", "3点レビュー", "副社長確認", {
            "decision": decision, "finding": finding,
            "source_quote": source_quote, "post_quote": post_quote, "provider": provider_name,
        })
        return {
            "decision": decision, "finding": None if finding == "none" else finding,
            "source_quote": source_quote, "post_quote": post_quote, "provider": provider_meta,
        }

    def save_result(self, key, candidate, employee, expected_revision,
                    expected_candidate_revision, result):
        return self.workspace.save_ai_result(key, candidate, employee,
                    expected_revision, expected_candidate_revision, result)
