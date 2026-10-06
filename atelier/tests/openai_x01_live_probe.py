"""Live OpenAI X01 probe: P2 stop -> Coco answer -> resume -> complete.

Requires OPENAI_API_KEY and ATELIER_OPENAI_LIVE=1.
No publish/x_06/E567 code is called. Generated prose is never printed.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

from atelier.server.server import Workspace
from atelier.server.ai_runtime import AIRuntime
from atelier.server.routing import RoutingEngine


def require_live_env():
    if os.environ.get("ATELIER_OPENAI_LIVE")!="1":
        raise SystemExit("ATELIER_OPENAI_LIVE=1 is required for the live X01 probe")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing; live X01 probe did not run")


tmp=tempfile.TemporaryDirectory()
root=Path(tmp.name)
for folder in ["posts","notes","atelier/config","atelier/canon"]:
    (root/folder).mkdir(parents=True,exist_ok=True)
for copy_path in [
    "atelier/config/employees.json",
    "atelier/config/workflow.json",
    "atelier/canon/x_post.md",
]:
    target=root/copy_path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((ROOT/copy_path).read_bytes())

base_material="店長が「この判断は自分で決めたい」と言ったあと、「どうしましょう」と最後の判断をこちらに戻してきた。私は条件と予算だけ伝え、最後の判断を店長に任せた。そのあと、店長から「この案で進めます」と返事があった。日付は素材に書かれていない。"
answer_date="2026年10月3日"

fixtures=[
    {
        "id":"P2",
        "platform":"X",
        "content":"",
        "quote":"",
        "theme":"現場の判断",
        "axis":"仕事・現場の「ん？」",
        "_probe_required_facts":["日付","誰が何を言ったか","わたしがしたこと","そのあと現場で起きたこと"],
        "material":base_material,
    },
]
(root/"posts/index.json").write_text(json.dumps({"weeks":["probe.json"]}))
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-x01-probe","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)


def key_at(i):
    return f"posts/probe.json#{i}"


def init_case(i):
    key=key_at(i)
    routing.register_case(key,"X","X01","素材確認・事実固定")
    state=workspace.get(key)
    if not state["theme"] or not state["axis"]:
        workspace.mutate(key,state["revision"],"basis",{"theme":fixtures[i]["theme"],"axis":fixtures[i]["axis"]})
    return key


def route_stop(key,result):
    six={
        "部門":"X",
        "投稿番号":"P2",
        "停止工程":result.get("stop_stage") or "素材確認・事実固定",
        "不足・不明点":result.get("missing_or_unknown") or "不足・不明点あり",
        "現在確認できる事実":result.get("confirmed_facts") or "素材内の明示事実のみ",
        "Cocoへの質問":result.get("question_for_coco") or "日付を教えてください",
    }
    return routing.stop(key,result.get("stop_reason") or "事実不明",six), six


def execute_current(key):
    state=workspace.get(key)
    return runtime.execute(key,"A","X01",state["revision"],state["candidates"]["A"]["revision"])


require_live_env()
key=init_case(0)

# First pass: P2 must stop for missing date.
first=execute_current(key)
if first["kind"]!="stop":
    raise AssertionError("P2 missing date was completed instead of stopped")
if first["stop_reason"] not in {"素材不足","事実不明"}:
    raise AssertionError(f"P2 unexpected stop reason: {first['stop_reason']}")
q,six=route_stop(key,first)

desk=workspace.desk()
if not desk["queue"] or desk["queue"][0]["id"]!=q["id"] or desk["queue"][0]["kind"]!="停止案件":
    raise AssertionError("P2 stop is not at the top of president desk")
payload=desk["queue"][0]["payload"]
required={"投稿番号","停止工程","不足・不明点","現在確認できる事実","Cocoへの質問"}
if not required<=set(payload) or not all(str(payload[k]).strip() for k in required):
    raise AssertionError("P2 manager six fields are incomplete")
if "日付" not in payload["Cocoへの質問"]:
    raise AssertionError("P2 Coco question does not ask for the missing date")

# Coco answers via the stop route, then the same X01 resumes at the saved stage.
routing.resume(key,q["id"],answer_date)

# Feed only Coco's answered fact back into this test case's explicit material.
# This does not alter canon/rules; it represents the resolved missing source fact.
fixtures[0]["material"]=answer_date+"。"+base_material.replace("日付は素材に書かれていない。","")
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-x01-probe","posts":fixtures},ensure_ascii=False))

resumed_case=routing.case(key)
if resumed_case["employee"]!="X01" or resumed_case["stage"]!="素材確認・事実固定" or resumed_case["status"]!="稼働中":
    raise AssertionError(f"P2 did not resume same X01 at stop stage: {resumed_case}")

events_before_complete=routing.events(key)
actions=[e["action"] for e in events_before_complete]
if "停止地点から再開" not in actions:
    raise AssertionError("P2 workflow_events missing stop-point resume event")

# Second pass: same X01 must now complete.
second=execute_current(key)
if second["kind"]!="complete":
    raise AssertionError(f"P2 did not complete after Coco answer: {second.get('kind')} / {second.get('stop_reason')}")

# Date must be reflected in used facts or final post content.
state_after=second["state"]
candidate=state_after["candidates"]["A"]
content=candidate["fields"].get("content","")
facts_used=second.get("facts_used",[])
date_reflected=(answer_date in content) or any(answer_date in str(x) for x in facts_used)
if not date_reflected:
    raise AssertionError("P2 answered date was not reflected in facts_used or final content")

# Normal route: completed -> VP 3-point gate -> president desk completed section.
routing.complete(key)
routing.vp_gate(key,None)
events=routing.events(key)
desk=workspace.desk()
if not any(x.get("key")==key and x.get("department")=="X" for x in desk["completed"]):
    raise AssertionError("P2 resumed post did not appear in president desk completed posts")
if [e["action"] for e in events][-2:]!=["完成","3点確認OK"]:
    raise AssertionError("P2 resumed route did not pass completion -> VP gate")

# No publish/send side effects before, during, or after resume.
with workspace.transaction() as db:
    exec_codes=[row["code"] for row in db.execute("SELECT code FROM executions ORDER BY id")]
for forbidden in {"PUBLISH","X_06","E567"}:
    if forbidden in exec_codes:
        raise AssertionError(f"Forbidden operation was recorded: {forbidden}")

print(json.dumps({
    "P2":"passed",
    "same_employee":"X01",
    "resume_stage":"素材確認・事実固定",
    "date_reflected":True,
    "vp_gate":"passed",
    "president_desk":"completed",
    "publish":"not called",
    "x_06":"not called",
    "E567":"not called",
},ensure_ascii=False))
tmp.cleanup()
