import json
from pathlib import Path
import tempfile
import unittest

from atelier.server.server import Workspace, ROOT
from atelier.server.routing import RoutingEngine


class RoutingSimulationTests(unittest.TestCase):
    """A-F fixed-response simulation. No AI/provider execution is used."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for folder in ["posts", "notes", "atelier/config"]:
            (self.root / folder).mkdir(parents=True)
        for name in ["employees.json", "workflow.json"]:
            (self.root / "atelier/config" / name).write_bytes(
                (ROOT / "atelier/config" / name).read_bytes()
            )
        (self.root / "posts/index.json").write_text(json.dumps({"weeks": ["fixture.json"]}))
        (self.root / "posts/fixture.json").write_text(json.dumps({
            "week": "fixture",
            "posts": [
                {"id": "fixture_x", "platform": "X", "content": "本文", "quote": "ひとこと", "x_short": "短文"},
                {"id": "fixture_t", "platform": "Threads", "content": "本文", "quote": "ひとこと"},
            ],
        }))
        (self.root / "notes/index.json").write_text(json.dumps({"notes": []}))
        self.w = Workspace(self.root, self.root / "work.sqlite3")
        self.r = RoutingEngine(self.w)

    def tearDown(self):
        self.tmp.cleanup()

    def new(self, case_id, department="X", employee="X01", stage="①"):
        return self.r.register_case(case_id, department, employee, stage)

    def six(self, case_id, department="X", stage="①", issue="素材が足りない", facts="確認済み事実", question="不足事実は何ですか？"):
        return {
            "部門": department,
            "投稿番号": case_id,
            "停止工程": stage,
            "不足・不明点": issue,
            "現在確認できる事実": facts,
            "Cocoへの質問": question,
        }

    def actions(self, case_id):
        return [e["action"] for e in self.r.events(case_id)]

    # A. 止まるべきで止まる

    def test_A1_material_shortage_routes_manager_to_secretary_top(self):
        self.w.enqueue_secretary("仕組み提案", "副社長", "X", {
            "現象": "既存提案", "回数": 3, "原因工程": "④", "変更案": "案", "影響範囲": "X"
        })
        self.new("A1", "X", "X01", "素材確認")
        q = self.r.stop("A1", "素材不足", self.six(
            "A1", stage="素材確認", issue="日付がない", facts="出来事だけ確認済み",
            question="この出来事の日付はいつですか？"
        ))
        queue = self.w.desk()["queue"]
        self.assertEqual(queue[0]["id"], q["id"])
        self.assertEqual(queue[0]["kind"], "停止案件")
        combined = {"部門"} | set(queue[0]["payload"])
        self.assertEqual(combined, {"部門", "投稿番号", "停止工程", "不足・不明点", "現在確認できる事実", "Cocoへの質問"})
        events = self.r.events("A1")
        self.assertEqual(events[1]["target"], "課長")
        self.assertIn("6項目整理", self.actions("A1"))
        self.assertIn("社長の机へ配置", self.actions("A1"))

    def test_A2_conflicting_facts_stop_without_guessing(self):
        self.new("A2", "Threads", "T03", "②")
        self.r.stop("A2", "事実不明", self.six(
            "A2", "Threads", "②", "同じ場面について矛盾する2つの事実",
            "両方の記述が素材に存在", "どちらが実際に起きた事実ですか？"
        ))
        self.assertEqual(self.r.case("A2")["status"], "停止中")
        self.assertNotIn("1案選択", self.actions("A2"))
        self.assertEqual(self.w.desk()["queue"][0]["payload"]["不足・不明点"], "同じ場面について矛盾する2つの事実")

    def test_A3_out_of_scope_photo_request_stops(self):
        self.new("A3", "X", "X05", "素材確認")
        self.r.stop("A3", "指示外", self.six(
            "A3", stage="素材確認", issue="写真を付ける指示はX投稿社員の担当外",
            facts="本文素材のみ", question="写真対応は別工程として扱いますか？"
        ))
        event = [e for e in self.r.events("A3") if e["action"] == "停止"][0]
        self.assertEqual(event["detail"]["reason"], "指示外")

    def test_A4_resume_same_employee_same_stage(self):
        self.new("A4", "X", "X01", "②")
        q = self.r.stop("A4", "素材不足", self.six("A4", stage="②"))
        resumed = self.r.resume("A4", q["id"], "不足事実の回答")
        self.assertEqual(resumed["employee"], "X01")
        self.assertEqual(resumed["stage"], "②")
        self.assertEqual(resumed["status"], "稼働中")
        last = self.r.events("A4")[-1]
        self.assertEqual(last["action"], "停止地点から再開")
        self.assertEqual(last["detail"]["stage"], "②")

    def test_A5_direct_fix_closes_stop_and_records_correction(self):
        self.new("A5", "X", "X01", "①")
        q = self.r.stop("A5", "素材不足", self.six("A5"))
        state = self.r.direct_stop_fix("A5", q["id"], "X")
        self.assertEqual(state["status"], "副社長確認待ち")
        self.assertEqual(self.w.desk()["queue"], [])
        ranking = self.w.audit_summary()["rankings"][0]
        self.assertEqual(ranking["reason"], "停止中の直接修正")
        self.assertEqual(ranking["count"], 1)

    # B. 止まるべきでないのに止まらない

    def test_B1_in_rule_ambiguity_goes_board_not_stop(self):
        self.new("B1", "X", "X02", "ひとこと選び")
        self.r.request_board("B1", "候補2つが拮抗")
        state = self.r.board_select("B1", "候補B")
        self.assertEqual(state["status"], "稼働中")
        self.assertIn("1案選択", self.actions("B1"))
        self.assertEqual(self.w.desk()["queue"], [])

    def test_B2_threads_AB_board_selection_skips_vp_and_secretary_during_selection(self):
        self.new("B2", "Threads", "T07", "A/B選択")
        self.r.request_board("B2", "A/B選択")
        self.r.board_select("B2", "A")
        events = self.r.events("B2")
        self.assertFalse(any(e["actor"] == "副社長" for e in events))
        self.assertFalse(any(e["actor"] == "秘書" for e in events))
        self.assertEqual(self.w.desk()["queue"], [])

    def test_B3_vp_does_not_stop_for_preference(self):
        self.new("B3", "X", "X03", "④")
        self.r.complete("B3")
        state = self.r.vp_gate("B3", "言い回しが弱い")
        self.assertEqual(state["status"], "Coco確認待ち")
        self.assertEqual(self.r.events("B3")[-1]["action"], "3点外なので通過")

    # C. 勝手に変えない

    def test_C1_board_new_fact_is_rejected_and_stopped(self):
        self.new("C1", "X", "X04", "ひとこと選び")
        self.r.request_board("C1")
        self.r.board_select("C1", "A", has_new_fact=True)
        self.assertEqual(self.r.case("C1")["status"], "停止中")
        self.assertEqual(self.w.desk()["queue"][0]["kind"], "停止案件")
        self.assertNotIn("1案選択", self.actions("C1"))

    def test_C2_employee_rule_rewrite_rejected_and_sent_to_vp(self):
        self.new("C2", "X", "X05", "④")
        result = self.r.unauthorized_change("C2", "X05", "ルール変更", "X", "④の条件追加")
        self.assertFalse(result["accepted"])
        flags = self.r.flags("X")
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["status"], "副社長整理待ち")
        self.assertIn("変更提案へ変換", self.actions("C2"))

    def test_C3_vp_cannot_rewrite_post(self):
        self.new("C3", "X", "X06", "副社長3点関所")
        result = self.r.unauthorized_change("C3", "副社長", "本文修正", "X")
        self.assertFalse(result["accepted"])
        self.assertEqual(self.r.flags("X"), [])
        self.assertIn("権限外変更拒否", self.actions("C3"))

    def test_C4_audit_cannot_change_rule(self):
        self.new("C4", "Threads", "T04", "監査")
        result = self.r.unauthorized_change("C4", "監査委員会", "ルール変更", "Threads", "禁止語変更")
        self.assertFalse(result["accepted"])
        self.assertEqual(self.r.flags("Threads"), [])
        self.assertIn("権限外変更拒否", self.actions("C4"))

    def test_C5_rule_write_without_coco_approval_is_invalid(self):
        self.new("C5", "X", "X07", "④")
        self.assertFalse(self.r.direct_rule_write("C5", "X07", approved=False)["accepted"])
        self.assertFalse(self.r.direct_rule_write("C5", "Coco", approved=False)["accepted"])
        with self.w.transaction() as db:
            n = db.execute("SELECT COUNT(*) AS n FROM rule_versions").fetchone()["n"]
        self.assertEqual(n, 0)

    # D. 副社長3点関所

    def test_D1_fact_distortion_returns_to_fact_fixing(self):
        self.new("D1", "X", "X08", "④")
        self.r.complete("D1")
        state = self.r.vp_gate("D1", "事実が曲がった")
        self.assertEqual(state["stage"], "素材確認・事実固定")
        self.assertEqual(self.r.events("D1")[-1]["detail"]["finding"], "事実が曲がった")

    def test_D2_voice_mixture_returns_to_content_alignment(self):
        self.new("D2", "X", "X09", "④")
        self.r.complete("D2")
        state = self.r.vp_gate("D2", "声が混ざった")
        self.assertEqual(state["stage"], "本文作成・整合性確認")

    def test_D3_not_returned_to_process_requires_audit_then_return(self):
        self.new("D3", "X", "X10", "④")
        self.r.complete("D3")
        state = self.r.vp_gate("D3", "工程に戻っていない", return_stage="③")
        self.assertEqual(state["stage"], "③")
        actions = self.actions("D3")
        self.assertLess(actions.index("監査記録要求"), actions.index("記録"))
        self.assertLess(actions.index("記録"), actions.index("工程へ戻す"))

    # E. 改善ループと記録

    def test_E1_two_same_corrections_do_not_reach_vp(self):
        self.new("E1a"); self.new("E1b")
        self.r.record_correction("E1a", "X", "4行目が予定に見える")
        result = self.r.record_correction("E1b", "X", "4行目が予定に見える")
        self.assertEqual(result["count"], 2)
        self.assertIsNone(result["flag_id"])
        self.assertEqual(self.r.flags("X"), [])

    def test_E2_third_same_correction_reaches_vp_and_secretary(self):
        for cid in ["E2a", "E2b", "E2c"]:
            self.new(cid)
        self.r.record_correction("E2a", "X", "4行目が予定に見える")
        self.r.record_correction("E2b", "X", "4行目が予定に見える")
        result = self.r.record_correction("E2c", "X", "4行目が予定に見える")
        self.assertIsNotNone(result["flag_id"])
        q = self.r.vp_prepare_proposal(
            result["flag_id"], "E2c", "④", "4行目の予定表現を禁止条件へ追加", "X部門"
        )
        item = self.w.desk()["queue"][0]
        self.assertEqual(item["id"], q["id"])
        self.assertEqual(item["kind"], "仕組み提案")
        self.assertEqual(set(item["payload"]), {"現象", "回数", "原因工程", "変更案", "影響範囲"})
        self.assertEqual(item["payload"]["回数"], 3)

    def test_E3_counts_do_not_cross_departments(self):
        self.new("E3x1"); self.new("E3x2"); self.new("E3t", "Threads", "T01")
        self.r.record_correction("E3x1", "X", "同じ問題")
        self.r.record_correction("E3x2", "X", "同じ問題")
        self.r.record_correction("E3t", "Threads", "同じ問題")
        self.assertEqual(self.r.flags(), [])
        rows = self.w.audit_summary()["rankings"]
        counts = {(r["department"], r["reason"]): r["count"] for r in rows}
        self.assertEqual(counts[("X", "同じ問題")], 2)
        self.assertEqual(counts[("Threads", "同じ問題")], 1)

    def _proposal(self, prefix, department="X"):
        for suffix in ["a", "b", "c"]:
            cid = prefix + suffix
            self.new(cid, department, "X01" if department == "X" else "T01")
            result = self.r.record_correction(cid, department, "同種修正")
        q = self.r.vp_prepare_proposal(result["flag_id"], prefix + "c", "④", "変更案", department + "部門")
        return prefix + "c", q

    def test_E4_rejection_keeps_rule_and_records_rejection(self):
        cid, q = self._proposal("E4")
        decision = self.r.decide_proposal(cid, q["id"], "却下")
        self.assertEqual(decision["decision"], "却下")
        with self.w.transaction() as db:
            row = db.execute("SELECT * FROM rule_versions WHERE id=?", (decision["history_id"],)).fetchone()
            approved = db.execute("SELECT COUNT(*) AS n FROM rule_versions WHERE decision='承認'").fetchone()["n"]
        self.assertEqual(row["decision"], "却下")
        self.assertEqual(row["effective_from"], "適用なし")
        self.assertEqual(approved, 0)
        self.assertIn("仕組み提案却下", self.actions(cid))

    def test_E5_approval_applies_only_to_next_new_case(self):
        self.new("E5_old", "X", "X01")
        cid, q = self._proposal("E5")
        old_version = self.r.case("E5_old")["rule_version"]
        decision = self.r.decide_proposal(cid, q["id"], "承認")
        self.assertEqual(self.r.case("E5_old")["rule_version"], old_version)
        new_case = self.new("E5_new", "X", "X02")
        self.assertEqual(new_case["rule_version"], decision["history_id"])
        self.assertGreater(new_case["rule_version"], old_version)

    def test_E6_exception_pass_is_recorded_and_three_reach_vp(self):
        for i in range(1, 4):
            cid = f"E6_{i}"
            self.new(cid, "X", f"X{i:02d}")
            result = self.r.vp_exception_check(cid, "過去ルールと逆方向", coco_passed=True)
        self.assertEqual(result["count"], 3)
        self.assertIsNotNone(result["flag_id"])
        flag = [f for f in self.r.flags("X") if f["source"] == "例外3回"][0]
        self.assertEqual(flag["status"], "副社長整理待ち")
        self.assertIn("過去判断との矛盾確認", self.actions("E6_3"))
        self.assertIn("例外通過記録", self.actions("E6_3"))

    def test_E7_rankings_are_separate_for_three_departments(self):
        for cid, dept, employee in [
            ("E7x", "X", "X01"), ("E7t", "Threads", "T01"), ("E7s", "X短文", "XS01")
        ]:
            self.new(cid, dept, employee)
            self.r.record_correction(cid, dept, "表現修正")
        departments = {r["department"] for r in self.w.audit_summary()["rankings"]}
        self.assertEqual(departments, {"X", "Threads", "X短文"})

    # F. X短文

    def test_F1_xshort_stops_before_x_body_fourth_line_exists(self):
        self.new("F1", "X短文", "XS01", "短文①")
        self.r.validate_xshort("F1", source_complete=False, has_fourth_line=False, fixed_response_valid=True)
        self.assertEqual(self.r.case("F1")["status"], "停止中")
        item = self.w.desk()["queue"][0]
        self.assertEqual(item["department"], "X短文")
        self.assertIn("4行目", item["payload"]["不足・不明点"])

    def test_F2_xshort_rejects_paraphrase_or_added_material(self):
        self.new("F2", "X短文", "XS02", "短文①")
        result = self.r.validate_xshort("F2", source_complete=True, has_fourth_line=True, fixed_response_valid=False)
        self.assertFalse(result["accepted"])
        self.assertIn("X短文候補拒否", self.actions("F2"))
        self.assertEqual(self.w.desk()["queue"], [])


if __name__ == "__main__":
    unittest.main()

# Fixed-response simulation only; provider execution is intentionally absent.
