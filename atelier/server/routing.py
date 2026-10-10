"""Deterministic routing harness for Coco Atelier.

No AI/provider calls live here. It accepts fixed test outcomes and exercises only
routing, authority boundaries, queue ownership, and audit records.
"""
import json


class RoutingError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class RoutingEngine:
    STOP_REASONS = {"素材不足", "事実不明", "指示外"}
    VP_FINDINGS = {
        "事実が曲がった": "素材確認・事実固定",
        "声が混ざった": "本文作成・整合性確認",
        "工程に戻っていない": None,
    }
    # atelier/canon/interview.md「2. 9問を埋める」。ここに条文を復唱しない——
    # キー名とインデックスだけがコードの都合で必要（インデックス0・2・5＝原文の1・3・6）。
    MATERIAL_POINTS = (
        "実際に何が起きたか", "誰が何と言ったか", "わたしが何をしたか", "わたしが何をしなかったか",
        "その前に何があったか", "そのあと何が変わったか", "何回あったか",
        "数字（人数・時間・金額など、原文にあるものだけ）", "まだ決まっていないこと",
    )
    MATERIAL_POINTS_MUST_FILL = (MATERIAL_POINTS[0], MATERIAL_POINTS[2], MATERIAL_POINTS[5])
    MATERIAL_ASK_BATCH = 3
    MATERIAL_ESCALATE_AFTER_ROUNDS = 2
    MATERIAL_DRAFT_FIELDS = {"軸", "場面", "わたしがしたこと", "そのあと起きたこと"}
    MATERIAL_MAX_DRAFTS = 3
    MATERIAL_GATE_FIELDS = (
        "日付", "媒体と置き換え先", "場面", "わたしがしたこと", "そのあと起きたこと",
        "【必ず残す事実】3点", "対応表", "原文",
    )
    MATERIAL_SELECTIONS = {"A", "B", "C", "案なし・自分で書く"}
    MATERIAL_SMELL_WORDS = ("来店", "常連", "お客様", "客様", "スタッフ")

    def __init__(self, workspace):
        self.workspace = workspace
        with self.workspace.transaction() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS workflow_cases (
              case_id TEXT PRIMARY KEY,
              department TEXT NOT NULL,
              employee TEXT NOT NULL,
              stage TEXT NOT NULL,
              status TEXT NOT NULL,
              resume_stage TEXT,
              resume_employee TEXT,
              rule_version INTEGER NOT NULL DEFAULT 0,
              at TEXT DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS workflow_events (
              id INTEGER PRIMARY KEY,
              case_id TEXT NOT NULL,
              actor TEXT NOT NULL,
              action TEXT NOT NULL,
              target TEXT,
              detail TEXT NOT NULL,
              at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS improvement_flags (
              id INTEGER PRIMARY KEY,
              department TEXT NOT NULL,
              reason TEXT NOT NULL,
              count INTEGER NOT NULL,
              source TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT '副社長整理待ち',
              at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS rule_versions (
              id INTEGER PRIMARY KEY,
              department TEXT NOT NULL,
              rule_key TEXT NOT NULL,
              old_rule TEXT NOT NULL,
              new_rule TEXT NOT NULL,
              reason TEXT NOT NULL,
              decision TEXT NOT NULL,
              effective_from TEXT NOT NULL,
              at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS material_interviews (
              case_id TEXT PRIMARY KEY,
              department TEXT NOT NULL,
              employee TEXT NOT NULL,
              raw_material TEXT NOT NULL,
              organized_material TEXT NOT NULL,
              missing_points TEXT NOT NULL,
              follow_up_count INTEGER NOT NULL DEFAULT 0,
              drafts TEXT,
              selected_option TEXT,
              addendum TEXT,
              has_addendum INTEGER NOT NULL DEFAULT 0,
              public_material TEXT,
              smell_flags TEXT,
              escalated INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL DEFAULT '進行中',
              at TEXT DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)

    def _event(self, db, case_id, actor, action, target=None, **detail):
        db.execute(
            "INSERT INTO workflow_events(case_id,actor,action,target,detail) VALUES (?,?,?,?,?)",
            (case_id, actor, action, target, json.dumps(detail, ensure_ascii=False)),
        )

    def events(self, case_id):
        with self.workspace.transaction() as db:
            rows = db.execute(
                "SELECT actor,action,target,detail FROM workflow_events WHERE case_id=? ORDER BY id",
                (case_id,),
            ).fetchall()
        return [
            {**dict(row), "detail": json.loads(row["detail"])}
            for row in rows
        ]

    def case(self, case_id):
        with self.workspace.transaction() as db:
            row = db.execute("SELECT * FROM workflow_cases WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            raise RoutingError("NOT_FOUND", "案件が見つかりません")
        return dict(row)

    def _current_rule_version(self, db, department):
        row = db.execute(
            "SELECT MAX(id) AS id FROM rule_versions WHERE department=? AND decision='承認'",
            (department,),
        ).fetchone()
        return int(row["id"] or 0)

    def register_case(self, case_id, department, employee, stage="素材確認"):
        with self.workspace.transaction() as db:
            version = self._current_rule_version(db, department)
            db.execute(
                "INSERT INTO workflow_cases(case_id,department,employee,stage,status,rule_version) VALUES (?,?,?,?,?,?)",
                (case_id, department, employee, stage, "稼働中", version),
            )
            self._event(db, case_id, employee, "案件開始", employee, stage=stage, rule_version=version)
        return self.case(case_id)

    def stop(self, case_id, reason, six):
        if reason not in self.STOP_REASONS:
            raise RoutingError("STOP_REASON", "停止理由が全社共通ルール外です")
        required = {"部門", "投稿番号", "停止工程", "不足・不明点", "現在確認できる事実", "Cocoへの質問"}
        if set(six) != required or not all(str(six[k]).strip() for k in required):
            raise RoutingError("STOP_FIELDS", "停止案件の6項目が揃っていません")
        current = self.case(case_id)
        payload = {
            "投稿番号": six["投稿番号"],
            "停止工程": six["停止工程"],
            "不足・不明点": six["不足・不明点"],
            "現在確認できる事実": six["現在確認できる事実"],
            "Cocoへの質問": six["Cocoへの質問"],
        }
        queued = self.workspace.enqueue_secretary(
            "停止案件", "課長", six["部門"], payload, key=case_id, stage=six["停止工程"]
        )
        with self.workspace.transaction() as db:
            db.execute(
                """UPDATE workflow_cases SET status='停止中',resume_stage=?,resume_employee=?,
                   updated_at=CURRENT_TIMESTAMP WHERE case_id=?""",
                (current["stage"], current["employee"], case_id),
            )
            self._event(db, case_id, current["employee"], "停止", "課長", reason=reason)
            self._event(db, case_id, "課長", "6項目整理", "秘書", queue_id=queued["id"], **six)
            self._event(db, case_id, "秘書", "社長の机へ配置", "Coco", queue_id=queued["id"])
        return queued

    def resume(self, case_id, queue_id, response):
        current = self.case(case_id)
        if current["status"] != "停止中":
            raise RoutingError("NOT_STOPPED", "停止案件ではありません")
        self.workspace.resolve_secretary(queue_id, response)
        with self.workspace.transaction() as db:
            db.execute(
                """UPDATE workflow_cases SET status='稼働中',stage=?,employee=?,
                   updated_at=CURRENT_TIMESTAMP WHERE case_id=?""",
                (current["resume_stage"], current["resume_employee"], case_id),
            )
            self._event(db, case_id, "Coco", "回答", "秘書", queue_id=queue_id)
            self._event(db, case_id, "秘書", "回答返却", "課長", queue_id=queue_id)
            self._event(db, case_id, "課長", "停止地点から再開", current["resume_employee"],
                        stage=current["resume_stage"])
        return self.case(case_id)

    def direct_stop_fix(self, case_id, queue_id, department, before="停止中", after="Coco直接修正"):
        self.workspace.resolve_secretary(queue_id, "Cocoが直接修正して通過")
        with self.workspace.transaction() as db:
            db.execute(
                "INSERT INTO corrections(key,department,reason,diff) VALUES (?,?,?,?)",
                (case_id, department, "停止中の直接修正",
                 json.dumps({"content": {"before": before, "after": after}}, ensure_ascii=False)),
            )
            db.execute(
                "UPDATE workflow_cases SET status='副社長確認待ち',updated_at=CURRENT_TIMESTAMP WHERE case_id=?",
                (case_id,),
            )
            self._event(db, case_id, "Coco", "停止中の直接修正", "副社長", queue_id=queue_id)
        self._threshold(department, "停止中の直接修正", case_id)
        return self.case(case_id)

    def request_board(self, case_id, reason="指示内の迷い"):
        current = self.case(case_id)
        with self.workspace.transaction() as db:
            db.execute(
                "UPDATE workflow_cases SET status='取締役会判断中',updated_at=CURRENT_TIMESTAMP WHERE case_id=?",
                (case_id,),
            )
            self._event(db, case_id, current["employee"], "取締役会依頼", "取締役会", reason=reason)

    def board_select(self, case_id, selection, has_new_fact=False):
        current = self.case(case_id)
        if current["status"] != "取締役会判断中":
            raise RoutingError("BOARD_STATE", "取締役会判断中ではありません")
        if has_new_fact:
            six = {
                "部門": current["department"], "投稿番号": case_id,
                "停止工程": current["stage"], "不足・不明点": "取締役会案に素材にない事実がある",
                "現在確認できる事実": "素材内の事実のみ", "Cocoへの質問": "追加された事実は実際に起きましたか？",
            }
            return self.stop(case_id, "事実不明", six)
        with self.workspace.transaction() as db:
            db.execute(
                "UPDATE workflow_cases SET status='稼働中',updated_at=CURRENT_TIMESTAMP WHERE case_id=?",
                (case_id,),
            )
            self._event(db, case_id, "取締役会", "1案選択", current["employee"], selection=selection)
        return self.case(case_id)

    def complete(self, case_id):
        current = self.case(case_id)
        with self.workspace.transaction() as db:
            db.execute(
                "UPDATE workflow_cases SET status='副社長確認待ち',updated_at=CURRENT_TIMESTAMP WHERE case_id=?",
                (case_id,),
            )
            self._event(db, case_id, current["employee"], "完成", "副社長")
        return self.case(case_id)

    def vp_gate(self, case_id, finding=None, return_stage=None):
        current = self.case(case_id)
        if finding not in self.VP_FINDINGS and finding is not None:
            with self.workspace.transaction() as db:
                db.execute(
                    "UPDATE workflow_cases SET status='Coco確認待ち',updated_at=CURRENT_TIMESTAMP WHERE case_id=?",
                    (case_id,),
                )
                self._event(db, case_id, "副社長", "3点外なので通過", "Coco", ignored=finding)
            return self.case(case_id)
        if finding is None:
            with self.workspace.transaction() as db:
                db.execute(
                    "UPDATE workflow_cases SET status='Coco確認待ち',updated_at=CURRENT_TIMESTAMP WHERE case_id=?",
                    (case_id,),
                )
                self._event(db, case_id, "副社長", "3点確認OK", "Coco")
            return self.case(case_id)

        stage = self.VP_FINDINGS[finding] or return_stage or current["stage"]
        with self.workspace.transaction() as db:
            if finding == "工程に戻っていない":
                self._event(db, case_id, "副社長", "監査記録要求", "監査委員会", finding=finding)
                self._event(db, case_id, "監査委員会", "記録", "副社長", finding=finding)
            db.execute(
                "UPDATE workflow_cases SET status='稼働中',stage=?,updated_at=CURRENT_TIMESTAMP WHERE case_id=?",
                (stage, case_id),
            )
            self._event(db, case_id, "副社長", "工程へ戻す", current["employee"],
                        finding=finding, stage=stage)
        return self.case(case_id)

    def unauthorized_change(self, case_id, actor, change_kind, department, suggestion=""):
        if actor == "Coco":
            raise RoutingError("USE_APPROVAL", "Coco変更は承認フローを使用してください")
        with self.workspace.transaction() as db:
            self._event(db, case_id, actor, "権限外変更拒否", None, change_kind=change_kind)
            if change_kind == "ルール変更" and actor not in {"副社長", "監査委員会"}:
                db.execute(
                    "INSERT INTO improvement_flags(department,reason,count,source,status) VALUES (?,?,?,?,?)",
                    (department, suggestion or "ルール変更提案", 1, actor, "副社長整理待ち"),
                )
                self._event(db, case_id, actor, "変更提案へ変換", "副社長",
                            suggestion=suggestion or "ルール変更提案")
        return {"accepted": False}

    def direct_rule_write(self, case_id, actor, approved=False):
        if actor != "Coco" or not approved:
            with self.workspace.transaction() as db:
                self._event(db, case_id, actor, "ルール直接書込拒否", None, approved=approved)
            return {"accepted": False}
        return {"accepted": True}

    def record_correction(self, case_id, department, reason):
        with self.workspace.transaction() as db:
            db.execute(
                "INSERT INTO corrections(key,department,reason,diff) VALUES (?,?,?,?)",
                (case_id, department, reason, "{}"),
            )
            self._event(db, case_id, "監査委員会", "修正記録", None,
                        department=department, reason=reason)
        return self._threshold(department, reason, case_id)

    def _threshold(self, department, reason, case_id):
        with self.workspace.transaction() as db:
            row = db.execute(
                "SELECT COUNT(*) AS n FROM corrections WHERE department=? AND reason=?",
                (department, reason),
            ).fetchone()
            count = int(row["n"])
            existing = db.execute(
                """SELECT id FROM improvement_flags
                   WHERE department=? AND reason=? AND source='修正3回'""",
                (department, reason),
            ).fetchone()
            flag_id = existing["id"] if existing else None
            if count >= 3 and not existing:
                cur = db.execute(
                    "INSERT INTO improvement_flags(department,reason,count,source,status) VALUES (?,?,?,?,?)",
                    (department, reason, count, "修正3回", "副社長整理待ち"),
                )
                flag_id = cur.lastrowid
                self._event(db, case_id, "監査委員会", "同種3回検知", "副社長",
                            department=department, reason=reason, count=count, flag_id=flag_id)
        return {"count": count, "flag_id": flag_id if count >= 3 else None}

    def flags(self, department=None):
        with self.workspace.transaction() as db:
            if department:
                rows = db.execute(
                    "SELECT * FROM improvement_flags WHERE department=? ORDER BY id", (department,)
                ).fetchall()
            else:
                rows = db.execute("SELECT * FROM improvement_flags ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def vp_prepare_proposal(self, flag_id, case_id, cause_stage, proposal, impact):
        with self.workspace.transaction() as db:
            flag = db.execute("SELECT * FROM improvement_flags WHERE id=?", (flag_id,)).fetchone()
            if not flag or flag["status"] != "副社長整理待ち":
                raise RoutingError("FLAG", "副社長整理待ちの候補がありません")
        payload = {
            "現象": flag["reason"], "回数": flag["count"], "原因工程": cause_stage,
            "変更案": proposal, "影響範囲": impact,
        }
        q = self.workspace.enqueue_secretary("仕組み提案", "副社長", flag["department"], payload)
        with self.workspace.transaction() as db:
            db.execute("UPDATE improvement_flags SET status='Coco確認待ち' WHERE id=?", (flag_id,))
            self._event(db, case_id, "副社長", "5項目整理", "秘書", queue_id=q["id"], **payload)
            self._event(db, case_id, "秘書", "社長の机へ配置", "Coco", queue_id=q["id"])
        return q

    def decide_proposal(self, case_id, queue_id, decision, rule_key="default",
                        old_rule="旧ルール", new_rule="新ルール", reason="同種3回"):
        if decision not in {"承認", "却下"}:
            raise RoutingError("DECISION", "承認か却下を指定してください")
        with self.workspace.transaction() as db:
            row = db.execute(
                "SELECT department,payload,status FROM secretary_queue WHERE id=? AND kind='仕組み提案'",
                (queue_id,),
            ).fetchone()
            if not row or row["status"] != "Coco確認待ち":
                raise RoutingError("QUEUE", "確認待ちの仕組み提案がありません")
            department = row["department"]
        self.workspace.resolve_secretary(queue_id, decision)
        with self.workspace.transaction() as db:
            self._event(db, case_id, "Coco", f"仕組み提案{decision}", "秘書", queue_id=queue_id)
            effective = "次の新規案件" if decision == "承認" else "適用なし"
            cur = db.execute(
                """INSERT INTO rule_versions(department,rule_key,old_rule,new_rule,reason,decision,effective_from)
                   VALUES (?,?,?,?,?,?,?)""",
                (department, rule_key, old_rule, new_rule, reason, decision, effective),
            )
            if decision == "承認":
                self._event(db, case_id, "秘書", "承認返却", "副社長", rule_version=cur.lastrowid)
            else:
                self._event(db, case_id, "秘書", "却下返却", "副社長", decision_record=cur.lastrowid)
        return {"decision": decision, "history_id": cur.lastrowid}

    def record_exception(self, case_id, department, direction):
        with self.workspace.transaction() as db:
            db.execute("INSERT INTO exceptions(key,department,note) VALUES (?,?,?)",
                       (case_id, department, direction))
            self._event(db, case_id, "監査委員会", "例外通過記録", None,
                        department=department, direction=direction)
            row = db.execute(
                "SELECT COUNT(*) AS n FROM exceptions WHERE department=? AND note=?",
                (department, direction),
            ).fetchone()
            count = int(row["n"])
            existing = db.execute(
                """SELECT id FROM improvement_flags
                   WHERE department=? AND reason=? AND source='例外3回'""",
                (department, direction),
            ).fetchone()
            flag_id = existing["id"] if existing else None
            if count >= 3 and not existing:
                cur = db.execute(
                    "INSERT INTO improvement_flags(department,reason,count,source,status) VALUES (?,?,?,?,?)",
                    (department, direction, count, "例外3回", "副社長整理待ち"),
                )
                flag_id = cur.lastrowid
                self._event(db, case_id, "監査委員会", "同方向例外3回検知", "副社長",
                            department=department, direction=direction, count=count, flag_id=flag_id)
        return {"count": count, "flag_id": flag_id if count >= 3 else None}

    def vp_exception_check(self, case_id, direction, coco_passed):
        current = self.case(case_id)
        with self.workspace.transaction() as db:
            self._event(db, case_id, "副社長", "過去判断との矛盾確認", "Coco", direction=direction)
        if coco_passed:
            with self.workspace.transaction() as db:
                self._event(db, case_id, "Coco", "矛盾確認後も通過", "監査委員会", direction=direction)
            return self.record_exception(case_id, current["department"], direction)
        with self.workspace.transaction() as db:
            self._event(db, case_id, "Coco", "矛盾判断を不通過", "副社長", direction=direction)
        return {"count": 0, "flag_id": None}

    def validate_xshort(self, case_id, source_complete, has_fourth_line, fixed_response_valid):
        current = self.case(case_id)
        if not source_complete or not has_fourth_line:
            six = {
                "部門": "X短文", "投稿番号": case_id, "停止工程": current["stage"],
                "不足・不明点": "直後のX本文4行目が完成していない",
                "現在確認できる事実": "X短文の材料は直後のX本文4行目のみ",
                "Cocoへの質問": "直後のX本文4行目を確定してください",
            }
            return self.stop(case_id, "素材不足", six)
        if not fixed_response_valid:
            with self.workspace.transaction() as db:
                self._event(db, case_id, current["employee"], "X短文候補拒否", current["employee"],
                            reason="言い換え・素材追加")
            return {"accepted": False}
        return {"accepted": True}

    # --- 素材取材（atelier/canon/interview.md） ---

    @staticmethod
    def _missing_points(points):
        return [k for k in RoutingEngine.MATERIAL_POINTS if not str(points.get(k) or "").strip()]

    @staticmethod
    def _load_json_fields(row, fields):
        data = dict(row)
        for field in fields:
            if data.get(field):
                data[field] = json.loads(data[field])
        return data

    @classmethod
    def _ask_batch(cls, missing):
        """atelier/canon/interview.md「一度に聞くのは3問まで」。全件はDBに持つが、
        Cocoに見せる・ログに残す聞き返しは先頭3件だけ。"""
        return missing[:cls.MATERIAL_ASK_BATCH]

    @classmethod
    def _must_fill_still_missing(cls, missing):
        return [k for k in cls.MATERIAL_POINTS_MUST_FILL if k in missing]

    def material_start(self, case_id, department, employee, raw_material, points):
        if not isinstance(raw_material, str) or not raw_material.strip():
            raise RoutingError("MATERIAL_RAW", "原文が必要です")
        if set(points) != set(self.MATERIAL_POINTS):
            raise RoutingError("MATERIAL_POINTS", "9問の項目が揃っていません")
        missing = self._missing_points(points)
        ask = self._ask_batch(missing)
        follow_up_count = 1 if missing else 0
        with self.workspace.transaction() as db:
            version = self._current_rule_version(db, department)
            db.execute(
                "INSERT INTO workflow_cases(case_id,department,employee,stage,status,rule_version) VALUES (?,?,?,?,?,?)",
                (case_id, department, employee, "素材取材", "稼働中", version),
            )
            db.execute(
                """INSERT INTO material_interviews
                   (case_id,department,employee,raw_material,organized_material,missing_points,follow_up_count,status)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (case_id, department, employee, raw_material, json.dumps(points, ensure_ascii=False),
                 json.dumps(missing, ensure_ascii=False), follow_up_count, "進行中"),
            )
            self._event(db, case_id, employee, "素材受領", employee, missing=ask)
            if ask:
                self._event(db, case_id, employee, "聞き返し", "Coco", missing=ask)
        # follow_up_countは起点でしかないため、ここで2回目のしきい値に達することはない
        # （material_answerの応答後にだけ起こる）。
        return {"case_id": case_id, "missing": ask}

    def material_answer(self, case_id, answers):
        with self.workspace.transaction() as db:
            row = db.execute(
                "SELECT department,organized_material FROM material_interviews WHERE case_id=?", (case_id,)
            ).fetchone()
            if not row:
                raise RoutingError("NOT_FOUND", "取材案件が見つかりません")
            department = row["department"]
            points = json.loads(row["organized_material"])
            points.update({k: v for k, v in answers.items() if k in self.MATERIAL_POINTS})
            missing = self._missing_points(points)
            ask = self._ask_batch(missing)
            db.execute(
                """UPDATE material_interviews SET organized_material=?,missing_points=?,
                   follow_up_count=follow_up_count+?,updated_at=CURRENT_TIMESTAMP WHERE case_id=?""",
                (json.dumps(points, ensure_ascii=False), json.dumps(missing, ensure_ascii=False),
                 1 if missing else 0, case_id),
            )
            new_count = db.execute(
                "SELECT follow_up_count FROM material_interviews WHERE case_id=?", (case_id,)
            ).fetchone()["follow_up_count"]
            self._event(db, case_id, "Coco", "聞き返しに回答", "取材社員", answers=list(answers))
            if ask:
                self._event(db, case_id, "取材社員", "聞き返し", "Coco", missing=ask)
        must_fill_missing = self._must_fill_still_missing(missing)
        if new_count >= self.MATERIAL_ESCALATE_AFTER_ROUNDS and must_fill_missing:
            return self._escalate_material_shortage(case_id, department, missing)
        return {"missing": ask}

    def _escalate_material_shortage(self, case_id, department, missing):
        """atelier/canon/interview.md「2回聞いても 1・3・6 が埋まらなければ、課長へ（素材不足）」。"""
        must_fill_missing = self._must_fill_still_missing(missing)
        six = {
            "部門": department, "投稿番号": case_id, "停止工程": "素材取材",
            "不足・不明点": "・".join(must_fill_missing),
            "現在確認できる事実": "・".join(k for k in self.MATERIAL_POINTS if k not in missing) or "なし",
            "Cocoへの質問": "2回聞いても埋まらない項目です。" + "／".join(must_fill_missing),
        }
        with self.workspace.transaction() as db:
            db.execute("UPDATE material_interviews SET escalated=1,updated_at=CURRENT_TIMESTAMP WHERE case_id=?", (case_id,))
        queued = self.stop(case_id, "素材不足", six)
        return {"case_id": case_id, "missing": missing, "escalated": True, "queue": queued}

    def material_propose(self, case_id, drafts):
        if not isinstance(drafts, list) or not drafts:
            raise RoutingError("MATERIAL_DRAFTS", "素材案がありません")
        if len(drafts) > self.MATERIAL_MAX_DRAFTS:
            raise RoutingError("MATERIAL_DRAFTS", "素材案は3つを超えて出さない")
        for draft in drafts:
            if not isinstance(draft, dict) or not self.MATERIAL_DRAFT_FIELDS <= set(draft):
                raise RoutingError("MATERIAL_DRAFTS", "素材案の形式が不正です")
        with self.workspace.transaction() as db:
            row = db.execute("SELECT case_id FROM material_interviews WHERE case_id=?", (case_id,)).fetchone()
            if not row:
                raise RoutingError("NOT_FOUND", "取材案件が見つかりません")
            db.execute(
                "UPDATE material_interviews SET drafts=?,updated_at=CURRENT_TIMESTAMP WHERE case_id=?",
                (json.dumps(drafts, ensure_ascii=False), case_id),
            )
            self._event(db, case_id, "取材社員", "素材案提示", "Coco", count=len(drafts))
        return {"case_id": case_id, "drafts": drafts}

    def material_select(self, case_id, selection, addendum=None):
        if selection not in self.MATERIAL_SELECTIONS:
            raise RoutingError("MATERIAL_SELECTION", "素材案の選択が不正です")
        has_addendum = bool(addendum and str(addendum).strip())
        with self.workspace.transaction() as db:
            row = db.execute("SELECT case_id FROM material_interviews WHERE case_id=?", (case_id,)).fetchone()
            if not row:
                raise RoutingError("NOT_FOUND", "取材案件が見つかりません")
            db.execute(
                """UPDATE material_interviews SET selected_option=?,addendum=?,has_addendum=?,
                   updated_at=CURRENT_TIMESTAMP WHERE case_id=?""",
                (selection, addendum or "", 1 if has_addendum else 0, case_id),
            )
            self._event(db, case_id, "Coco", "素材案選択", "取材社員", selection=selection, has_addendum=has_addendum)
        return {"case_id": case_id, "selection": selection, "has_addendum": has_addendum}

    @staticmethod
    def _gate_field_present(value):
        if isinstance(value, (list, tuple)):
            return any(str(v).strip() for v in value)
        return bool(str(value or "").strip())

    def material_finalize(self, case_id, public_material, next_employee=None):
        if not isinstance(public_material, dict):
            raise RoutingError("MATERIAL_FINALIZE", "公開用素材の形式が不正です")
        missing = [f for f in self.MATERIAL_GATE_FIELDS if not self._gate_field_present(public_material.get(f))]
        with self.workspace.transaction() as db:
            row = db.execute("SELECT case_id FROM material_interviews WHERE case_id=?", (case_id,)).fetchone()
            if not row:
                raise RoutingError("NOT_FOUND", "取材案件が見つかりません")
            if missing:
                db.execute(
                    "UPDATE material_interviews SET status='工程未完了',updated_at=CURRENT_TIMESTAMP WHERE case_id=?",
                    (case_id,),
                )
                self._event(db, case_id, "取材社員", "工程未完了", "取材社員", missing=missing)
                return {"complete": False, "missing": missing}
            smell_flags = {
                f: [w for w in self.MATERIAL_SMELL_WORDS if w in str(public_material.get(f, ""))]
                for f in self.MATERIAL_GATE_FIELDS
            }
            smell_flags = {f: ws for f, ws in smell_flags.items() if ws}
            db.execute(
                """UPDATE material_interviews SET public_material=?,smell_flags=?,status='完了',
                   updated_at=CURRENT_TIMESTAMP WHERE case_id=?""",
                (json.dumps(public_material, ensure_ascii=False), json.dumps(smell_flags, ensure_ascii=False), case_id),
            )
            current = db.execute(
                "SELECT employee FROM workflow_cases WHERE case_id=?", (case_id,)
            ).fetchone()
            target_employee = next_employee or (current["employee"] if current else None)
            db.execute(
                "UPDATE workflow_cases SET status='稼働中',stage='①',employee=?,updated_at=CURRENT_TIMESTAMP WHERE case_id=?",
                (target_employee, case_id),
            )
            self._event(db, case_id, "取材社員", "公開用素材完成", target_employee, smell_flags=smell_flags)
        return {"complete": True, "smell_flags": smell_flags, "public_material": public_material}

    def material_summary(self, case_id):
        with self.workspace.transaction() as db:
            row = db.execute("SELECT * FROM material_interviews WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            raise RoutingError("NOT_FOUND", "取材案件が見つかりません")
        return self._load_json_fields(
            row, ("organized_material", "missing_points", "drafts", "public_material", "smell_flags")
        )

    def material_pending(self, department=None):
        # 停止中（課長へ渡した案件）は社長の机の「停止中」段がすでに持つ。
        # ここに二重表示しない。
        base = """SELECT mi.* FROM material_interviews mi
                  LEFT JOIN workflow_cases wc ON wc.case_id = mi.case_id
                  WHERE mi.status!='完了' AND (wc.status IS NULL OR wc.status!='停止中')"""
        with self.workspace.transaction() as db:
            if department:
                rows = db.execute(base + " AND mi.department=? ORDER BY mi.case_id", (department,)).fetchall()
            else:
                rows = db.execute(base + " ORDER BY mi.case_id").fetchall()
        return [
            self._load_json_fields(row, ("organized_material", "missing_points", "drafts", "public_material", "smell_flags"))
            for row in rows
        ]

    def material_audit(self, department=None):
        with self.workspace.transaction() as db:
            if department:
                rows = db.execute(
                    """SELECT case_id,follow_up_count,selected_option,has_addendum,escalated
                       FROM material_interviews WHERE department=? ORDER BY case_id""",
                    (department,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT case_id,follow_up_count,selected_option,has_addendum,escalated FROM material_interviews ORDER BY case_id"
                ).fetchall()
        return [dict(r) for r in rows]
