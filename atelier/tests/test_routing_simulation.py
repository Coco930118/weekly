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

    # G. 素材取材（atelier/canon/interview.md）

    def full_points(self, **overrides):
        points = {k: f"{k}の回答" for k in self.r.MATERIAL_POINTS}
        points.update(overrides)
        return points

    def test_G1_all_points_present_has_no_follow_up(self):
        result = self.r.material_start("G1", "X", "MATERIAL", "原文テキスト", self.full_points())
        self.assertEqual(result["missing"], [])
        self.assertNotIn("聞き返し", self.actions("G1"))
        summary = self.r.material_summary("G1")
        self.assertEqual(summary["follow_up_count"], 0)

    def test_G2_missing_points_trigger_follow_up_then_resolve(self):
        points = self.full_points(**{"何回あったか": "", "数字（人数・時間・金額など、原文にあるものだけ）": ""})
        result = self.r.material_start("G2", "Threads", "MATERIAL", "原文テキスト", points)
        self.assertEqual(set(result["missing"]), {"何回あったか", "数字（人数・時間・金額など、原文にあるものだけ）"})
        self.assertIn("聞き返し", self.actions("G2"))
        answered = self.r.material_answer("G2", {"何回あったか": "3回", "数字（人数・時間・金額など、原文にあるものだけ）": "なし"})
        self.assertEqual(answered["missing"], [])
        summary = self.r.material_summary("G2")
        self.assertEqual(summary["follow_up_count"], 1)

    def test_G2b_asking_batch_is_capped_at_three(self):
        # 一度に聞くのは3問まで。4,5,7,8,9が欠けていても、見せる・ログに残すのは先頭3件だけ。
        points = self.full_points(**{k: "" for k in [
            "わたしが何をしなかったか", "その前に何があったか", "何回あったか",
            "数字（人数・時間・金額など、原文にあるものだけ）", "まだ決まっていないこと",
        ]})
        result = self.r.material_start("G2b", "X", "MATERIAL", "原文テキスト", points)
        self.assertEqual(len(result["missing"]), 3)
        logged = [e["detail"]["missing"] for e in self.r.events("G2b") if e["action"] == "聞き返し"][0]
        self.assertEqual(len(logged), 3)
        self.assertEqual(self.r.material_summary("G2b")["missing_points"], [
            "わたしが何をしなかったか", "その前に何があったか", "何回あったか",
            "数字（人数・時間・金額など、原文にあるものだけ）", "まだ決まっていないこと",
        ])

    def test_G2c_two_rounds_unresolved_on_1_3_6_escalates_to_manager(self):
        # 2回聞いても 1・3・6（実際に何が起きたか／わたしが何をしたか／そのあと何が変わったか）が
        # 埋まらなければ、課長へ（素材不足）。
        points = self.full_points(**{"実際に何が起きたか": "", "わたしが何をしたか": "", "そのあと何が変わったか": ""})
        self.r.material_start("G2c", "X", "MATERIAL", "原文テキスト", points)
        result = self.r.material_answer("G2c", {"実際に何が起きたか": "", "わたしが何をしたか": "", "そのあと何が変わったか": ""})
        self.assertTrue(result.get("escalated"))
        self.assertEqual(self.r.case("G2c")["status"], "停止中")
        queue_payload = self.w.desk()["queue"][0]["payload"]
        self.assertEqual(queue_payload["停止工程"], "素材取材")
        self.assertIn("実際に何が起きたか", queue_payload["不足・不明点"])

    def test_G2e_escalated_case_is_not_double_shown_in_pending(self):
        points = self.full_points(**{"実際に何が起きたか": ""})
        self.r.material_start("G2e", "X", "MATERIAL", "原文テキスト", points)
        self.r.material_answer("G2e", {"実際に何が起きたか": ""})
        pending_ids = [row["case_id"] for row in self.r.material_pending("X")]
        self.assertNotIn("G2e", pending_ids)

    def test_G2d_two_rounds_unresolved_on_other_points_does_not_escalate(self):
        # 1・3・6以外（ここでは4・9）が埋まらないままでも、2回目で課長へは渡さない。
        points = self.full_points(**{"わたしが何をしなかったか": "", "まだ決まっていないこと": ""})
        self.r.material_start("G2d", "X", "MATERIAL", "原文テキスト", points)
        result = self.r.material_answer("G2d", {"わたしが何をしなかったか": "", "まだ決まっていないこと": ""})
        self.assertNotIn("escalated", result)
        self.assertEqual(self.r.case("G2d")["status"], "稼働中")

    def test_G3_draft_shape_and_count_are_validated(self):
        self.r.material_start("G3", "X", "MATERIAL", "原文テキスト", self.full_points())
        with self.assertRaises(Exception):
            self.r.material_propose("G3", [{"場面": "x"}])
        with self.assertRaises(Exception):
            self.r.material_propose("G3", [
                {"軸": f"軸{i}", "場面": "場面", "わたしがしたこと": "行動", "そのあと起きたこと": "結果"}
                for i in range(4)
            ])
        # 3案に足りなくてもよい（2案）。「この案で足りない問い」は任意。
        drafts = [
            {"軸": "軸1", "場面": "場面", "わたしがしたこと": "行動", "そのあと起きたこと": "結果"},
            {"軸": "軸2", "場面": "場面", "わたしがしたこと": "行動", "そのあと起きたこと": "結果",
             "この案で足りない問い": "数字がまだない"},
        ]
        result = self.r.material_propose("G3", drafts)
        self.assertEqual(len(result["drafts"]), 2)
        self.assertIn("素材案提示", self.actions("G3"))

    def test_G4_selection_and_addendum_are_recorded(self):
        self.r.material_start("G4", "X", "MATERIAL", "原文テキスト", self.full_points())
        with self.assertRaises(Exception):
            self.r.material_select("G4", "D")
        result = self.r.material_select("G4", "B", addendum="追記事実")
        self.assertTrue(result["has_addendum"])
        summary = self.r.material_summary("G4")
        self.assertEqual(summary["selected_option"], "B")
        self.assertEqual(summary["has_addendum"], 1)

    def test_G5_finalize_incomplete_stays_in_material_interview(self):
        self.r.material_start("G5", "X", "MATERIAL", "原文テキスト", self.full_points())
        # 「日付」は取材社員に求めない（システム側で入る）ので、ここでは渡さない。
        result = self.r.material_finalize("G5", {"場面": "場面のみ"})
        self.assertFalse(result["complete"])
        self.assertIn("媒体と置き換え先", result["missing"])
        self.assertIn("【必ず残す事実】3点", result["missing"])
        self.assertIn("対応表", result["missing"])
        self.assertEqual(self.r.case("G5")["stage"], "素材取材")
        self.assertIn("工程未完了", self.actions("G5"))

    def test_G6_finalize_complete_hands_off_to_post_owner_and_flags_smell_words(self):
        self.r.material_start("G6", "Threads", "MATERIAL", "原文テキスト", self.full_points())
        public_material = {
            # 「日付」を渡さなくても、システム側（material_interviews.at）で揃う。
            "媒体と置き換え先": "Threads・お相手さまへ置き換え済み",
            "場面": "常連のお客様が来店した", "わたしがしたこと": "謝った",
            "そのあと起きたこと": "忘れないと言われた",
            "【必ず残す事実】3点": ["足が遠のいた", "すぐに謝った", "忘れないと言われた"],
            "対応表": ["お客様 => お相手さま", "来店した => 会ってくれた"],
            "原文": "原文そのまま",
        }
        result = self.r.material_finalize("G6", public_material, next_employee="T01")
        self.assertTrue(result["complete"])
        self.assertEqual(result["public_material"]["日付"], self.r.material_entered_date("G6"))
        self.assertIn("場面", result["smell_flags"])
        self.assertEqual(set(result["smell_flags"]["場面"]), {"常連", "お客様", "客様", "来店"})
        case = self.r.case("G6")
        self.assertEqual(case["stage"], "①")
        self.assertEqual(case["employee"], "T01")
        self.assertIn("公開用素材完成", self.actions("G6"))

    def test_G6b_finalize_overrides_date_with_system_entered_date(self):
        # 「日付」はCocoが原文を打った日時（material_start時点）をシステム側で入れる。
        # AI・Cocoの入力が食い違っていても、確定時に必ず上書きされる（2026-10-10 Coco決定）。
        self.r.material_start("G6b", "X", "MATERIAL", "原文テキスト", self.full_points())
        public_material = {
            "日付": "9999-01-01",  # 取材社員やCocoが誤って入れても無視される値
            "媒体と置き換え先": "X・仕事のまま", "場面": "場面", "わたしがしたこと": "行動",
            "そのあと起きたこと": "結果", "【必ず残す事実】3点": ["事実1"], "対応表": ["語 => 語"],
            "原文": "原文そのまま",
        }
        result = self.r.material_finalize("G6b", public_material)
        self.assertTrue(result["complete"])
        entered_date = self.r.material_entered_date("G6b")
        self.assertEqual(result["public_material"]["日付"], entered_date)
        self.assertNotEqual(result["public_material"]["日付"], "9999-01-01")

    def test_G6c_time_expression_field_is_optional_and_outside_the_gate(self):
        # 原文中の時期の表現（別枠）が空でも、形式ゲートの完了を妨げない。
        self.r.material_start("G6c", "X", "MATERIAL", "原文テキスト", self.full_points())
        public_material = {
            "媒体と置き換え先": "X・仕事のまま", "場面": "場面", "わたしがしたこと": "行動",
            "そのあと起きたこと": "結果", "【必ず残す事実】3点": ["事実1"], "対応表": ["語 => 語"],
            "原文": "原文そのまま",
        }
        result = self.r.material_finalize("G6c", public_material)
        self.assertTrue(result["complete"])
        self.assertNotIn(RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD, result["missing"] if not result["complete"] else [])
        # 別枠として渡せば、そのまま保存される（確定ゲートの対象外として）。
        self.r.material_start("G6d", "X", "MATERIAL", "原文テキスト2", self.full_points())
        public_material2 = {**public_material, RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD: "先週の火曜日"}
        result2 = self.r.material_finalize("G6d", public_material2)
        self.assertTrue(result2["complete"])
        self.assertEqual(result2["public_material"][RoutingEngine.MATERIAL_TIME_EXPRESSION_FIELD], "先週の火曜日")

    def test_G7_audit_counts_follow_up_selection_and_addendum(self):
        self.r.material_start("G7a", "X", "MATERIAL", "原文", self.full_points(**{"何回あったか": ""}))
        self.r.material_answer("G7a", {"何回あったか": "2回"})
        self.r.material_select("G7a", "A")
        self.r.material_start("G7b", "X", "MATERIAL", "原文", self.full_points())
        self.r.material_select("G7b", "案なし・自分で書く", addendum="追記")
        rows = {row["case_id"]: row for row in self.r.material_audit("X")}
        self.assertEqual(rows["G7a"]["follow_up_count"], 1)
        self.assertEqual(rows["G7a"]["selected_option"], "A")
        self.assertEqual(rows["G7a"]["has_addendum"], 0)
        self.assertEqual(rows["G7b"]["follow_up_count"], 0)
        self.assertEqual(rows["G7b"]["selected_option"], "案なし・自分で書く")
        self.assertEqual(rows["G7b"]["has_addendum"], 1)


if __name__ == "__main__":
    unittest.main()

# Fixed-response simulation only; provider execution is intentionally absent.
