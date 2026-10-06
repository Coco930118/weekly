"""Provider adapter boundary.

Live provider use is OFF by default. The first live scope is intentionally narrow:
X01 / X / one candidate execution only. Other employees remain blocked.
"""
from .openai_driver import OpenAIDriver, ProviderUnavailable, ProviderError


class AIRuntime:
    def __init__(self, workspace):
        self.workspace = workspace
        self.provider = OpenAIDriver()

    def _prepare_x01_request(self, key, state, person, db=None):
        source_row = self.workspace.source(key)
        source = source_row["source"]
        prompt_path = self.workspace.root / person["prompt_ref"]
        system_prompt = prompt_path.read_text()
        material = source.get("material")
        if not isinstance(material, str) or not material.strip():
            material = source.get("source_material")
        if not isinstance(material, str) or not material.strip():
            material = source.get("raw_material")
        if not isinstance(material, str) or not material.strip():
            # Never silently send the whole source object. Live input must be explicit.
            from .server import WorkspaceError
            raise WorkspaceError("MATERIAL_REQUIRED", "OpenAIへ送る素材フィールドが明示されていません")
        required_facts = source.get("_probe_required_facts", [])
        coco_resolution = None
        if db is not None:
            has_events = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_events'").fetchone()
            if has_events:
                row = db.execute(
                    "SELECT detail FROM workflow_events WHERE case_id=? AND action='このまま進める' ORDER BY id DESC LIMIT 1",
                    (key,),
                ).fetchone()
                if row:
                    import json
                    detail = json.loads(row["detail"])
                    coco_resolution = {
                        "action": "proceed_without_missing_fact",
                        "missing_or_unknown": detail.get("不足・不明点", ""),
                    }
        return {
            "mode": "x01_initial_probe",
            "employee": person["id"],
            "platform": state["platform"],
            "system_prompt": system_prompt,
            "material": material,
            "required_facts": required_facts,
            "coco_resolution": coco_resolution,
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
                import json
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
                elif str(person["id"]) != "X01" or state["platform"] != "X":
                    self.workspace.log(db, key, employee, "blocked", "AI_SCOPE", candidate)
                    provider_block = "初回OpenAI接続はX01のX投稿だけです"
                else:
                    prepared = self._prepare_x01_request(key, state, person, db)
                    state_snapshot = {
                        "theme": state["theme"],
                        "axis": state["axis"],
                        "revision": state["revision"],
                        "candidate_revision": state["candidates"][candidate]["revision"],
                    }
                    self.workspace.log(db, key, employee, "started", "OPENAI_X01", candidate)
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

        try:
            result = self.provider.execute(prepared)
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
        if result.get("decision") == "stop":
            with self.workspace.transaction() as db:
                self.workspace.log(db, key, employee, "stopped", result.get("stop_reason", "OPENAI_STOP"), candidate)
            return {
                "kind": "stop",
                "stop_reason": result["stop_reason"],
                "stop_stage": result["stop_stage"],
                "missing_or_unknown": result["missing_or_unknown"],
                "confirmed_facts": result["confirmed_facts"],
                "question_for_coco": result["question_for_coco"],
                "provider": provider_meta,
            }

        if result.get("decision") != "complete":
            with self.workspace.transaction() as db:
                self.workspace.log(db, key, employee, "failed", "OPENAI_DECISION", candidate)
            raise ProviderError("OpenAI decision was neither complete nor stop")

        save_payload = {
            "theme": state_snapshot["theme"],
            "axis": state_snapshot["axis"],
            "status": "OK",
            "findings": [],
            "fields": {
                "content": result["content"],
                "quote": result["quote"],
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
            "facts_used": result.get("facts_used", []),
            "provider": provider_meta,
        }

    def save_result(self, key, candidate, employee, expected_revision,
                    expected_candidate_revision, result):
        return self.workspace.save_ai_result(
            key, candidate, employee, expected_revision,
            expected_candidate_revision, result
        )
