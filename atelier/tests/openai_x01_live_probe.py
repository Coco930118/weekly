"""Live OpenAI X01 probe: close P3 with 'このまま進める'.

The missing customer statement must not be invented. The same X01 resumes at
the saved stop stage and completes without using that missing fact.
No publish/x_06/E567 code is called.
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

material=(
    "2026年10月3日、お客様に何かを言われた。"
    "ただし、何を言われたかは素材に書かれていない。"
    "私は条件と予算だけ伝え、最後の判断を店長に任せた。"
    "そのあと、店長から「この案で進めます」と返事があった。"
)

fixtures=[{
    "id":"P3",
    "platform":"X",
    "content":"",
    "quote":"",
    "theme":"現場の判断",
    "axis":"仕事・現場の「ん？」",
    "_probe_required_facts":["日付","誰が何を言ったか","わたしがしたこと","そのあと現場で起きたこと"],
    "material":material,
}]
(root/"posts/index.json").write_text(json.dumps({"weeks":["probe.json"]}))
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-x01-probe","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)


def init_case():
    key="posts/probe.json#0"
    routing.register_case(key,"X","X01","素材確認・事実固定")
    state=workspace.get(key)
    if not state["theme"] or not state["axis"]:
        workspace.mutate(key,state["revision"],"basis",{"theme":fixtures[0]["theme"],"axis":fixtures[0]["axis"]})
    return key


def execute_current(key):
    state=workspace.get(key)
    return runtime.execute(key,"A","X01",state["revision"],state["candidates"]["A"]["revision"])


def route_stop(key,result):
    six={
        "部門":"X",
        "投稿番号":"P3",
        "停止工程":result.get("stop_stage") or "素材確認・事実固定",
        "不足・不明点":result.get("missing_or_unknown") or "お客様に何を言われたか",
        "現在確認できる事実":result.get("confirmed_facts") or "素材内の明示事実のみ",
        "Cocoへの質問":result.get("question_for_coco") or "お客様に何を言われたか教えてください",
    }
    return routing.stop(key,result.get("stop_reason") or "事実不明",six)


require_live_env()
key=init_case()

first=execute_current(key)
if first["kind"]!="stop":
    raise AssertionError("P3 precondition failed: X01 did not stop")
q=route_stop(key,first)

# Use the exact UI operation: resolve the stop with 'このまま進める'.
workspace.resolve_secretary(q["id"],"このまま進める")

case=routing.case(key)
if case["status"]!="稼働中" or case["employee"]!="X01" or case["stage"]!="素材確認・事実固定":
    raise AssertionError(f"P3 proceed did not resume same X01 at stop stage: {case}")

events=routing.events(key)
if not any(e["action"]=="このまま進める" for e in events):
    raise AssertionError("P3 workflow_events missing Coco proceed action")
if not any(e["action"]=="停止地点から再開" and e["target"]=="X01" for e in events):
    raise AssertionError("P3 workflow_events missing same-X01 resume")

second=execute_current(key)
if second["kind"]!="complete":
    raise AssertionError(f"P3 did not complete after proceed: {second.get('kind')} / {second.get('stop_reason')}")

state=second["state"]
content=state["candidates"]["A"]["fields"].get("content","")
facts_used=second.get("facts_used",[])

# The missing statement must not have been fabricated into facts_used.
for fact in facts_used:
    if "お客様" in str(fact) and "何かを言われた" not in str(fact) and "相談" not in str(fact):
        raise AssertionError(f"P3 may have invented customer-statement detail: {fact}")

routing.complete(key)
routing.vp_gate(key,None)
desk=workspace.desk()
if not any(x.get("key")==key and x.get("department")=="X" for x in desk["completed"]):
    raise AssertionError("P3 proceeded post did not reach completed section")

with workspace.transaction() as db:
    exec_codes=[row["code"] for row in db.execute("SELECT code FROM executions ORDER BY id")]
for forbidden in {"PUBLISH","X_06","E567"}:
    if forbidden in exec_codes:
        raise AssertionError(f"Forbidden operation was recorded: {forbidden}")

print(json.dumps({
    "P3_close":"passed",
    "action":"このまま進める",
    "same_employee":"X01",
    "resume_stage":"素材確認・事実固定",
    "completed":True,
    "publish":"not called",
    "x_06":"not called",
    "E567":"not called",
},ensure_ascii=False))
tmp.cleanup()
