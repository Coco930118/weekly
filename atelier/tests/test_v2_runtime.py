import unittest
from unittest.mock import patch
from atelier.server.ai_runtime import AIRuntime

class V2RuntimeTests(unittest.TestCase):
    def test_public_source_type_off_and_wording_return(self):
        runtime = AIRuntime.__new__(AIRuntime)
        runtime.workspace = object()
        logs, requests = [], []
        runtime._log_stage = lambda *args: logs.append(args)
        runtime.save_result = lambda *args: args[-1]
        bad = "相談を受けた。\n\n映画を観た。\n\n連絡が来た。\n\n予定は決めなくていい。\n\n映画を観てみて。\n\n感情はある。依存はしない。"
        good = bad.replace("予定は決めなくていい。", "予定の有無と相手の気持ちの有無は、別のこと。")
        alternative = good.replace("映画を観てみて。", "予定を入れる前に映画を観てみて。")
        class Provider:
            def execute(self, request):
                requests.append(request)
                stage = request["stage_name"]
                result = {"decision":"complete","content":"問題ありません","quote":"予定と連絡。",
                          "facts_used":[],"checklist":[],"public_material":"","source_map":[],
                          "candidates":[],"audit_tags":[]}
                if stage == "一般化":
                    result.update(public_material="公開用素材",source_map=["原素材 => 公開用素材"],content="監査原文")
                if stage == "④":
                    result["audit_tags"] = ["型外し（Threads・④💗）"]
                if stage == "④'":
                    result["candidates"] = [bad,alternative]
                if stage == "⑤":
                    result["candidates"] = [good,alternative] if request.get("completion_feedback") else [bad,alternative]
                    result["audit_tags"] = ["型外し（Threads・④💗）"]
                if stage == "⑦":
                    result["candidates"] = [good]
                return result
        runtime.provider = Provider()
        prepared = {"canon_version":"v2","platform":"Threads","material":"原素材","canon_common":"共通条件",
                    "canon_preamble":"正典","stages":[(s,s) for s,_ in AIRuntime.STAGES_V2]}
        snapshot = {"theme":"テーマ","axis":"軸","revision":0,"candidate_revision":0}
        with patch("atelier.server.routing.RoutingEngine") as routing:
            result = runtime._execute_v2("case","A","T01",prepared,snapshot)
            self.assertEqual(routing.return_value.record_exception.call_count,1)
        self.assertEqual(result["kind"],"complete")
        self.assertEqual(result["state"]["fields"]["content"],good)
        self.assertNotIn("最終確認",[r["stage_name"] for r in requests])
        self.assertEqual(sum(r["stage_name"]=="⑤" for r in requests),2)
        for request in requests[1:]:
            self.assertEqual(request["material"],"公開用素材")
            self.assertNotIn("監査原文",str(request["prior_stage_outputs"]))
