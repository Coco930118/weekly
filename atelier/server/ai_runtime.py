"""Provider adapter boundary.

Live provider use is OFF by default. The first live scope is intentionally narrow:
X01 / X / one candidate execution only. Other employees remain blocked.
"""
from .openai_driver import OpenAIDriver, ProviderUnavailable, ProviderError


class AIRuntime:
    def __init__(self, workspace):
        self.workspace = workspace
        self.provider = OpenAIDriver()

    def _prepare_x01_request(self, key, state, person):
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
        return {
            "mode": "x01_initial_probe",
            "employee": person["id"],
            "platform": state["platform"],
            "system_prompt": system_prompt,
            "material": material,
            "required_facts": required_facts,
        }

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
                    prepared = self._prepare_x01_request(key, state, person)
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
        except (ProviderUnavailable, ProviderError):
            with self.workspace.transaction() as db:
                self.workspace.log(db, key, employee, "failed", "OPENAI_ERROR", candidate)
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
